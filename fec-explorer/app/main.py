import csv
import io
import logging
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.fec_parser import parse_multiple_fec
from app.core.indicators import calculate_indicators
from app.core.postgres_sync import sync_all

def _recalcul_anciennete():
    """Recalcule anciennete pour tous les clients avec date_entree."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return
    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS anciennete INTEGER;")
            cur.execute("""
                UPDATE clients
                SET anciennete = EXTRACT(YEAR FROM AGE(NOW(), date_entree))
                WHERE date_entree IS NOT NULL;
            """)
        conn.commit()
        conn.close()
    except Exception:
        pass


app = FastAPI(
    title="FEC Explorer API",
    description="Parse des fichiers FEC et calcule les indicateurs financiers par SIRET.",
    version="1.0.0",
)

@app.on_event("startup")
def startup_recalcul_anciennete():
    if not os.environ.get("ADMIN_TOKEN"):
        logger.warning(
            "⚠️  ADMIN_TOKEN non défini — /api/migrate/* et /api/debug/* sont bloqués (401)."
        )
    threading.Thread(target=_recalcul_anciennete, daemon=True).start()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.middleware("http")
async def admin_token_middleware(request: Request, call_next):
    """Protège /api/debug/* par Bearer token. /api/migrate/* est public."""
    path = request.url.path
    if path.startswith("/api/debug/"):
        admin_token = os.environ.get("ADMIN_TOKEN", "")
        auth_header = request.headers.get("Authorization", "")
        if not admin_token or auth_header != f"Bearer {admin_token}":
            return JSONResponse(
                status_code=401,
                content={"detail": "Token admin invalide ou manquant. Header requis : Authorization: Bearer <ADMIN_TOKEN>"},
            )
    return await call_next(request)


# ── Schémas ───────────────────────────────────────────────────────────────────

class FolderRequest(BaseModel):
    folder_path: str

class UpdateRequest(BaseModel):
    siret: str
    field: str
    value: object

class LoginRequest(BaseModel):
    password: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_db_conn():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=500, detail="Variable DATABASE_URL non définie.")
    try:
        return psycopg2.connect(database_url)
    except psycopg2.OperationalError as e:
        raise HTTPException(status_code=500, detail=f"Connexion PostgreSQL impossible : {e}")


def _serialize(val):
    """Convertit les types PostgreSQL non JSON-sérialisables (Decimal → float)."""
    if isinstance(val, Decimal):
        return float(val)
    return val


_COL_RE = re.compile(r"^[A-Za-z0-9_ ]+$")

def _safe_fields(fields: Dict[str, Any], conn) -> Dict[str, Any]:
    """
    Filtre un dict pour ne conserver que les clés correspondant à des colonnes
    réelles de la table clients. Double sécurité : regex + information_schema.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'clients'"
        )
        valid_cols = {row[0] for row in cur.fetchall()}
    return {
        k: v for k, v in fields.items()
        if _COL_RE.match(k) and k in valid_cols
    }



# ── Auth ─────────────────────────────────────────────────────────────────────

_JWT_ALGO      = "HS256"
_MAX_ATTEMPTS  = 5
_BLOCK_MINUTES = 15

# {ip: {"count": int, "blocked_until": datetime | None}}
_login_attempts: Dict[str, Dict] = {}


@app.post("/api/auth/login", summary="Authentifie avec mot de passe, retourne un JWT valable 24h")
def auth_login(body: LoginRequest, request: Request):
    ip  = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc)

    state = _login_attempts.get(ip, {"count": 0, "blocked_until": None})

    # Vérifie si l'IP est encore bloquée
    if state["blocked_until"]:
        if now < state["blocked_until"]:
            secs      = int((state["blocked_until"] - now).total_seconds())
            remaining = max(1, (secs + 59) // 60)   # arrondi au plafond
            raise HTTPException(
                status_code=429,
                detail=f"Trop de tentatives, réessayez dans {remaining} minute{'s' if remaining > 1 else ''}.",
            )
        # Blocage expiré : repart à zéro
        state = {"count": 0, "blocked_until": None}

    crm_password = os.environ.get("CRM_PASSWORD", "")
    jwt_secret   = os.environ.get("JWT_SECRET", "")
    if not crm_password or not jwt_secret:
        raise HTTPException(status_code=500, detail="Variables CRM_PASSWORD ou JWT_SECRET non définies.")

    if body.password != crm_password:
        state["count"] += 1
        if state["count"] >= _MAX_ATTEMPTS:
            state["blocked_until"] = now + timedelta(minutes=_BLOCK_MINUTES)
            _login_attempts[ip] = state
            raise HTTPException(
                status_code=429,
                detail=f"Trop de tentatives, réessayez dans {_BLOCK_MINUTES} minutes.",
            )
        _login_attempts[ip] = state
        remaining_tries = _MAX_ATTEMPTS - state["count"]
        raise HTTPException(
            status_code=401,
            detail=f"Mot de passe incorrect. ({remaining_tries} tentative{'s' if remaining_tries > 1 else ''} restante{'s' if remaining_tries > 1 else ''})",
        )

    # Succès : reset du compteur pour cette IP
    _login_attempts.pop(ip, None)

    expiry  = now + timedelta(hours=1)
    payload = {"sub": "crm_user", "exp": expiry}
    token   = jwt.encode(payload, jwt_secret, algorithm=_JWT_ALGO)
    return {"token": token, "expiry": "1h"}


@app.get("/api/auth/verify", summary="Vérifie la validité d'un token JWT (Authorization: Bearer <token>)")
def auth_verify(authorization: str = Header(default="")):
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if not jwt_secret:
        return {"valid": False, "reason": "JWT_SECRET non défini côté serveur"}
    if not authorization.startswith("Bearer "):
        return {"valid": False, "reason": "Header Authorization manquant ou mal formé"}
    token = authorization[len("Bearer "):]
    try:
        claims     = jwt.decode(token, jwt_secret, algorithms=[_JWT_ALGO])
        exp        = claims.get("exp")
        expires_in = int(exp - datetime.now(timezone.utc).timestamp()) if exp else None
        return {"valid": True, "expires_in": expires_in}
    except JWTError:
        return {"valid": False, "reason": "Token invalide ou expiré"}


# ── Routes API ────────────────────────────────────────────────────────────────

@app.get("/api/clients", summary="Liste les clients avec pagination et filtres")
def get_clients(
    page: int = 1,
    limit: int = 50,
    search: str = "",
    collaborateur: str = "",
    assistant: str = "",
    annee: str = "",
    cloture: str = "",
    filterField: str = "",
    filterValue: str = "",
):
    conn = _get_db_conn()
    try:
        conditions = []
        params = []

        if search:
            conditions.append("(nom_client ILIKE %s OR code_client ILIKE %s OR siret ILIKE %s)")
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if collaborateur:
            conditions.append("collaborateur ILIKE %s")
            params.append(f"%{collaborateur}%")
        if assistant:
            conditions.append("assistant ILIKE %s")
            params.append(f"%{assistant}%")
        if annee:
            conditions.append("annee::text ILIKE %s")
            params.append(f"%{annee}%")
        if cloture:
            conditions.append("date_de_cloture::text ILIKE %s")
            params.append(f"%{cloture}%")
        ALLOWED = {"cvae","is","tvs","ca12","liasse","impot_sur_le_revenu","cotisation_fonciere_entreprise","dividendes","situation","tbb","juridique"}
        if filterField and filterField in ALLOWED and filterValue == "true":
            conditions.append(f'"{filterField}" = TRUE')

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if limit == 0:
                cur.execute(f"SELECT * FROM clients {where} ORDER BY nom_client", params)
                rows = [{k: _serialize(v) for k, v in row.items()} for row in cur.fetchall()]
                return {"data": rows, "total": len(rows), "page": 1, "pages": 1}

            cur.execute(f"SELECT COUNT(*) FROM clients {where}", params)
            total = cur.fetchone()["count"]

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM clients {where} ORDER BY nom_client LIMIT %s OFFSET %s",
                params + [limit, offset],
            )
            rows = [
                {k: _serialize(v) for k, v in row.items()}
                for row in cur.fetchall()
            ]

        import math
        pages = math.ceil(total / limit) if limit else 1
        return {"data": rows, "total": total, "page": page, "pages": pages}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/calendrier/fiscal", summary="Retourne les échéances fiscales de tous les clients")
def get_calendrier_fiscal():
    conn = _get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT siret, nom_client, date_de_cloture,
                       is, cvae, tvs, ca12, liasse, dividendes, ca_r,
                       cotisation_fonciere_entreprise, cfe_r,
                       collaborateur, assistant
                FROM clients
                ORDER BY nom_client
            """)
            rows = [
                {k: _serialize(v) for k, v in row.items()}
                for row in cur.fetchall()
            ]
        return {"clients": rows}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/clients/columns", summary="Liste les colonnes et types PostgreSQL de la table clients")
def get_clients_columns():
    conn = _get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_name = 'clients' "
                "ORDER BY ordinal_position"
            )
            return [dict(row) for row in cur.fetchall()]
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/clients/stats", summary="Total et honoraires moyen sur tous les clients (avec filtres)")
def get_clients_stats(
    search: str = "",
    collaborateur: str = "",
    assistant: str = "",
    annee: str = "",
    cloture: str = "",
    filterField: str = "",
    filterValue: str = "",
):
    conn = _get_db_conn()
    try:
        conditions = []
        params = []

        if search:
            conditions.append("(nom_client ILIKE %s OR code_client ILIKE %s OR siret ILIKE %s)")
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        if collaborateur:
            conditions.append("collaborateur ILIKE %s")
            params.append(f"%{collaborateur}%")
        if assistant:
            conditions.append("assistant ILIKE %s")
            params.append(f"%{assistant}%")
        if annee:
            conditions.append("annee::text ILIKE %s")
            params.append(f"%{annee}%")
        if cloture:
            conditions.append("date_de_cloture::text ILIKE %s")
            params.append(f"%{cloture}%")
        ALLOWED = {"cvae","is","tvs","ca12","liasse","impot_sur_le_revenu","cotisation_fonciere_entreprise","dividendes","situation","tbb","juridique"}
        if filterField and filterField in ALLOWED and filterValue == "true":
            conditions.append(f'"{filterField}" = TRUE')

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT COUNT(*) AS total, AVG(honoraires_cpta) AS honoraires_moyen FROM clients {where}",
                params,
            )
            row = cur.fetchone()
        return {
            "total": int(row["total"]),
            "honoraires_moyen": float(row["honoraires_moyen"]) if row["honoraires_moyen"] else 0.0,
        }
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/clients/distinct", summary="Valeurs distinctes d'une colonne (whitelist)")
def get_clients_distinct(field: str):
    ALLOWED = {"collaborateur", "assistant", "structure", "activite_r"}
    if field not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Champ non autorisé : {field}")
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT DISTINCT "{field}" FROM clients '
                f'WHERE "{field}" IS NOT NULL AND "{field}" <> \'\' '
                f'ORDER BY "{field}"'
            )
            return [row[0] for row in cur.fetchall()]
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/clients/template-csv", summary="CSV vide avec les en-têtes de la table clients")
def get_clients_template():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'clients' ORDER BY ordinal_position"
            )
            columns = [row[0] for row in cur.fetchall()]
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

    csv_content = ",".join(columns) + "\n"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_clients.csv"},
    )


@app.get("/api/client/{siret}", summary="Récupère un client par SIRET depuis PostgreSQL")
def get_client(siret: str):
    conn = _get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM clients WHERE siret = %s", (siret,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Client introuvable : {siret!r}")
            return {k: _serialize(v) for k, v in row.items()}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/update-airtable", summary="Met à jour un champ client dans PostgreSQL (compatibilité ancienne route)")
def update_client_field(body: UpdateRequest):
    siret = body.siret.strip()
    field = body.field.strip()
    value = body.value

    if not siret:
        return {"error": "siret manquant"}
    if not field:
        return {"error": "field manquant"}

    # Valide que le nom de colonne ne contient que des caractères sûrs
    # (lettres, chiffres, underscore, espace, majuscules) — bloque l'injection SQL
    if not re.fullmatch(r"[A-Za-z0-9_ ]+", field):
        return {"error": f"Nom de colonne invalide : {field!r}"}

    print(f"UPDATE: siret={siret}, field={field}, value={value}")
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            # Vérifie le type de la colonne dans information_schema
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'clients' AND column_name = %s
                LIMIT 1;
            """, (field,))
            row = cur.fetchone()
            col_type = row[0] if row else None
            print(f"UPDATE col_type: {col_type}")

            # Si la colonne est numeric mais la valeur est du texte,
            # on convertit la colonne en TEXT
            if col_type in ("numeric", "integer", "bigint", "double precision", "real") and isinstance(value, str) and not value.replace(".", "").replace("-", "").isdigit():
                print(f"UPDATE: conversion {field} numeric→TEXT")
                cur.execute(f'ALTER TABLE clients ALTER COLUMN "{field}" TYPE TEXT USING "{field}"::TEXT;')

            # Migrations des colonnes suivi_mission_* en TEXT si besoin
            for col in ("suivi_mission_retraite", "suivi_mission_patrimoniale", "suivi_mission_placement", "suivi_mission_prevoyance"):
                cur.execute("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = 'clients' AND column_name = %s LIMIT 1;
                """, (col,))
                r = cur.fetchone()
                if r and r[0] not in ("text", "character varying"):
                    print(f"UPDATE: migration {col} → TEXT")
                    cur.execute(f'ALTER TABLE clients ALTER COLUMN "{col}" TYPE TEXT USING "{col}"::TEXT;')

            cur.execute(
                f'UPDATE clients SET "{field}" = %s WHERE siret = %s',
                (str(value) if value is not None else None, siret),
            )
            print(f"UPDATE rowcount: {cur.rowcount}")
            if cur.rowcount == 0:
                return {"error": f"Aucun client trouvé avec siret={siret!r}"}
        conn.commit()
        return {"success": True}
    except psycopg2.Error as e:
        conn.rollback()
        print(f"UPDATE erreur: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/api/client/create", summary="Crée un nouveau client dans PostgreSQL")
def create_client(body: Dict[str, Any] = Body(...)):
    siret = str(body.get("siret", "")).strip()
    if not siret:
        raise HTTPException(status_code=400, detail="Le champ 'siret' est obligatoire.")

    conn = _get_db_conn()
    try:
        fields = _safe_fields(body, conn)
        if not fields:
            raise HTTPException(status_code=400, detail="Aucun champ valide reçu.")

        cols         = ", ".join(f'"{k}"' for k in fields)
        placeholders = ", ".join("%s" for _ in fields)
        values       = list(fields.values())

        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO clients ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT (siret) DO NOTHING",
                values,
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=409, detail=f"Un client avec siret={siret!r} existe déjà.")
        conn.commit()
        return {"success": True, "siret": siret}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/client/update", summary="Met à jour plusieurs champs d'un client")
def update_client(body: Dict[str, Any] = Body(...)):
    siret = str(body.get("siret", "")).strip()
    if not siret:
        raise HTTPException(status_code=400, detail="Le champ 'siret' est obligatoire.")

    conn = _get_db_conn()
    try:
        to_update = {k: v for k, v in body.items() if k != "siret"}
        fields = _safe_fields(to_update, conn)
        if not fields:
            raise HTTPException(status_code=400, detail="Aucun champ valide à mettre à jour.")

        set_clause = ", ".join(f'"{k}" = %s' for k in fields)
        values     = list(fields.values()) + [siret]

        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE clients SET {set_clause} WHERE siret = %s",
                values,
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Client introuvable : {siret!r}")
        conn.commit()
        return {"success": True, "updated": list(fields.keys())}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.patch("/api/client/{siret}", summary="Met à jour un ou plusieurs champs d'un client (PATCH)")
def patch_client(siret: str, body: Dict[str, Any] = Body(...)):
    conn = _get_db_conn()
    try:
        fields = _safe_fields(body, conn)
        if not fields:
            raise HTTPException(status_code=400, detail="Aucun champ valide à mettre à jour.")
        set_clause = ", ".join(f'"{k}" = %s' for k in fields)
        values     = list(fields.values()) + [siret]
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE clients SET {set_clause} WHERE siret = %s",
                values,
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Client introuvable : {siret!r}")
        conn.commit()
        return {"success": True, "updated": list(fields.keys())}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.delete("/api/client/{siret}", summary="Supprime un client par SIRET")
def delete_client(siret: str):
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clients WHERE siret = %s", (siret,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Client introuvable : {siret!r}")
        conn.commit()
        return {"success": True, "deleted": siret}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



@app.post("/api/clients/import", summary="Import CSV → UPSERT clients")
async def import_clients_csv(file: UploadFile = File(...)):
    raw = await file.read()
    text = raw.decode("utf-8-sig")  # gère le BOM éventuel

    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type "
                "FROM information_schema.columns WHERE table_name='clients'"
            )
            col_types = {row[0]: row[1] for row in cur.fetchall()}

        reader = csv.DictReader(io.StringIO(text))
        upserted = 0
        errors: List[str] = []

        for i, row in enumerate(reader):
            siret = str(row.get("siret", "")).strip()
            if not siret:
                errors.append(f"Ligne {i + 2} : siret manquant")
                continue

            updates: Dict[str, Any] = {}
            for col, val in row.items():
                if col == "siret" or col not in col_types:
                    continue
                if val == "":
                    updates[col] = None
                else:
                    if "date" in col_types[col] and "/" in val:
                        parts = val.split("/")
                        if len(parts) == 3:
                            val = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    elif col_types[col] == "boolean":
                        if val.lower() in ("oui", "true", "1", "yes"):
                            val = True
                        elif val.lower() in ("non", "false", "0", "no"):
                            val = False
                        else:
                            val = None
                    updates[col] = val

            cols   = ["siret"] + list(updates.keys())
            vals   = [siret]   + list(updates.values())
            params = ", ".join(["%s"] * len(cols))
            set_clause = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in updates)

            sql = (
                f'INSERT INTO clients ({", ".join(f"{chr(34)}{c}{chr(34)}" for c in cols)}) '
                f"VALUES ({params}) "
                f'ON CONFLICT (siret) DO UPDATE SET {set_clause}'
            )

            try:
                with conn.cursor() as cur:
                    cur.execute(sql, vals)
                conn.commit()
                upserted += 1
            except psycopg2.Error as e:
                conn.rollback()
                errors.append(f"{siret} : {e.pgerror or str(e)}")

        return {"success": True, "upserted": upserted, "errors": errors}
    finally:
        conn.close()


_PATTERN_FEC_NAME = re.compile(r"^(\d{9})FEC\d{8}\.txt$", re.IGNORECASE)


@app.post("/api/fec/upload", summary="Import FEC multi-fichiers depuis le navigateur")
async def upload_fec(files: List[UploadFile] = File(...)):
    """
    Accepte plusieurs fichiers FEC (multipart).
    - Extrait le SIRET depuis le nom de chaque fichier (pattern SIREN+FEC+DATE.txt)
    - Parse via parse_multiple_fec(), calcule les indicateurs, synchronise en PostgreSQL
    - Retourne {results: [{siret, status, indicators_updated}]} pour chaque fichier
    """
    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        valid_files: list[tuple[str, str]] = []  # (filename, siret)

        for f in files:
            filename = f.filename or ""
            match = _PATTERN_FEC_NAME.match(filename)
            if not match:
                results.append({
                    "siret": None,
                    "status": "error",
                    "indicators_updated": 0,
                    "message": f"Nom invalide : '{filename}' (attendu : SIREN+FEC+DATE.txt)",
                })
                continue

            siret = match.group(1)
            content = await f.read()
            with open(os.path.join(tmpdir, filename), "wb") as fout:
                fout.write(content)
            valid_files.append((filename, siret))

        if not valid_files:
            return {"results": results}

        try:
            rows = parse_multiple_fec(tmpdir)
        except Exception as e:
            for _, siret in valid_files:
                results.append({"siret": siret, "status": "error", "indicators_updated": 0, "message": f"Erreur parsing : {e}"})
            return {"results": results}

        if not rows:
            for _, siret in valid_files:
                results.append({"siret": siret, "status": "error", "indicators_updated": 0, "message": "Aucune écriture FEC trouvée"})
            return {"results": results}

        indicateurs = calculate_indicators(rows)
        siret_to_ind = {str(ind.get("siret", "")): ind for ind in indicateurs}

        for _, siret in valid_files:
            ind = siret_to_ind.get(siret)
            if not ind:
                results.append({"siret": siret, "status": "error", "indicators_updated": 0, "message": "Aucun indicateur calculé"})
                continue

            indicators_updated = sum(1 for k, v in ind.items() if k != "siret" and v is not None)
            try:
                sync_result = sync_all([ind])
                status = "ok" if sync_result["errors"] == 0 else "warning"
                msg = "" if sync_result["errors"] == 0 else f"{sync_result['errors']} erreur(s) sync PostgreSQL"
            except Exception as e:
                status = "error"
                msg = f"Erreur sync : {e}"
                indicators_updated = 0

            results.append({"siret": siret, "status": status, "indicators_updated": indicators_updated, "message": msg})

    return {"results": results}


@app.get("/api/migrate/mai_cvae_setup", summary="Ajoute la colonne mai_cvae NUMERIC si absente")
def migrate_mai_cvae_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS mai_cvae NUMERIC")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/migrate/anciennete", summary="Ajoute la colonne anciennete et la calcule depuis date_entree")
def migrate_anciennete():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS anciennete INTEGER;")
            cur.execute("""
                UPDATE clients
                SET anciennete = EXTRACT(YEAR FROM AGE(NOW(), date_entree))
                WHERE date_entree IS NOT NULL;
            """)
            cur.execute("SELECT COUNT(*) FROM clients WHERE anciennete IS NOT NULL;")
            updated = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    finally:
        conn.close()


@app.get("/api/migrate/anciennete/refresh", summary="Recalcule l'ancienneté de tous les clients")
def refresh_anciennete():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clients
                SET anciennete = EXTRACT(YEAR FROM AGE(NOW(), date_entree))
                WHERE date_entree IS NOT NULL;
            """)
            cur.execute("SELECT COUNT(*) FROM clients WHERE anciennete IS NOT NULL;")
            updated = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_anciennete", summary="Installe le trigger trg_anciennete sur date_entree")
def install_trigger_anciennete():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_anciennete ON clients;")
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_anciennete_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.anciennete := EXTRACT(YEAR FROM AGE(NOW(), NEW.date_entree));
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_anciennete
                BEFORE INSERT OR UPDATE OF date_entree
                ON clients
                FOR EACH ROW
                EXECUTE FUNCTION update_anciennete_trigger();
            """)
        conn.commit()
        return {"status": "ok", "message": "Trigger trg_anciennete installé avec succès"}
    finally:
        conn.close()


_NAF_DATA = [
    ("1",  "Culture et production animale, chasse et services annexes"),
    ("2",  "Sylviculture et exploitation forestière"),
    ("3",  "Pêche et aquaculture"),
    ("5",  "Extraction de houille et de lignite"),
    ("6",  "Extraction d'hydrocarbures"),
    ("7",  "Extraction de minerais métalliques"),
    ("8",  "Autres industries extractives"),
    ("9",  "Services de soutien aux industries extractives"),
    ("10", "Industries alimentaires"),
    ("11", "Fabrication de boissons"),
    ("12", "Fabrication de produits à base de tabac"),
    ("13", "Fabrication de textiles"),
    ("14", "Industrie de l'habillement"),
    ("15", "Industrie du cuir et de la chaussure"),
    ("16", "Travail du bois et fabrication d'articles en bois et en liège, à l'exception des meubles ; fabrication d'articles en vannerie et sparterie"),
    ("17", "Industrie du papier et du carton"),
    ("18", "Imprimerie et reproduction d'enregistrements"),
    ("19", "Cokéfaction et raffinage"),
    ("20", "Industrie chimique"),
    ("21", "Industrie pharmaceutique"),
    ("22", "Fabrication de produits en caoutchouc et en plastique"),
    ("23", "Fabrication d'autres produits minéraux non métalliques"),
    ("24", "Métallurgie"),
    ("25", "Fabrication de produits métalliques, à l'exception des machines et des équipements"),
    ("26", "Fabrication de produits informatiques, électroniques et optiques"),
    ("27", "Fabrication d'équipements électriques"),
    ("28", "Fabrication de machines et équipements n.c.a."),
    ("29", "Industrie automobile"),
    ("30", "Fabrication d'autres matériels de transport"),
    ("31", "Fabrication de meubles"),
    ("32", "Autres industries manufacturières"),
    ("33", "Réparation et installation de machines et d'équipements"),
    ("35", "Production et distribution d'électricité, de gaz, de vapeur et d'air conditionné"),
    ("36", "Captage, traitement et distribution d'eau"),
    ("37", "Collecte et traitement des eaux usées"),
    ("38", "Collecte, traitement et élimination des déchets ; récupération"),
    ("39", "Dépollution et autres services de gestion des déchets"),
    ("41", "Construction de bâtiments"),
    ("42", "Génie civil"),
    ("43", "Travaux de construction spécialisés"),
    ("45", "Commerce et réparation d'automobiles et de motocycles"),
    ("46", "Commerce de gros, à l'exception des automobiles et des motocycles"),
    ("47", "Commerce de détail, à l'exception des automobiles et des motocycles"),
    ("49", "Transports terrestres et transport par conduites"),
    ("50", "Transports par eau"),
    ("51", "Transports aériens"),
    ("52", "Entreposage et services auxiliaires des transports"),
    ("53", "Activités de poste et de courrier"),
    ("55", "Hébergement"),
    ("56", "Restauration"),
    ("58", "Édition"),
    ("59", "Production de films cinématographiques, de vidéo et de programmes de télévision ; enregistrement sonore et édition musicale"),
    ("60", "Programmation et diffusion"),
    ("61", "Télécommunications"),
    ("62", "Programmation, conseil et autres activités informatiques"),
    ("63", "Services d'information"),
    ("64", "Activités des services financiers, hors assurance et caisses de retraite"),
    ("65", "Assurance"),
    ("66", "Activités auxiliaires de services financiers et d'assurance"),
    ("68", "Activités immobilières"),
    ("69", "Activités juridiques et comptables"),
    ("70", "Activités des sièges sociaux ; conseil de gestion"),
    ("71", "Activités d'architecture et d'ingénierie ; activités de contrôle et analyses techniques"),
    ("72", "Recherche-développement scientifique"),
    ("73", "Publicité et études de marché"),
    ("74", "Autres activités spécialisées, scientifiques et techniques"),
    ("75", "Activités vétérinaires"),
    ("77", "Activités de location et location-bail"),
    ("78", "Activités liées à l'emploi"),
    ("79", "Activités des agences de voyage, voyagistes, services de réservation et activités connexes"),
    ("80", "Enquêtes et sécurité"),
    ("81", "Services relatifs aux bâtiments et aménagement paysager"),
    ("82", "Activités administratives et autres activités de soutien aux entreprises"),
    ("84", "Administration publique et défense ; sécurité sociale obligatoire"),
    ("85", "Enseignement"),
    ("86", "Activités pour la santé humaine"),
    ("87", "Hébergement médico-social et social"),
    ("88", "Action sociale sans hébergement"),
    ("90", "Activités créatives, artistiques et de spectacle"),
    ("91", "Bibliothèques, archives, musées et autres activités culturelles"),
    ("92", "Organisation de jeux de hasard et d'argent"),
    ("93", "Activités sportives, récréatives et de loisirs"),
    ("94", "Activités des organisations associatives"),
    ("95", "Réparation d'ordinateurs et de biens personnels et domestiques"),
    ("96", "Autres services personnels"),
    ("97", "Activités des ménages en tant qu'employeurs de personnel domestique"),
    ("98", "Activités indifférenciées des ménages en tant que producteurs de biens et services pour usage propre"),
    ("99", "Activités des organisations et organismes extraterritoriaux"),
]


@app.get("/api/migrate/naf", summary="Crée la table NAF et insère les données hardcodées")
def migrate_naf():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS naf (
                    code VARCHAR(10) PRIMARY KEY,
                    libelle TEXT NOT NULL
                );
            """)
            count = 0
            for code, libelle in _NAF_DATA:
                cur.execute(
                    """
                    INSERT INTO naf (code, libelle) VALUES (%s, %s)
                    ON CONFLICT (code) DO UPDATE SET libelle = EXCLUDED.libelle;
                    """,
                    (code, libelle),
                )
                count += 1
        conn.commit()
        return {"imported": count}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/activite", summary="Renseigne activite_r depuis code_naf_r via la table naf")
def migrate_activite():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            # Vérifie que la table naf existe et contient des données
            try:
                cur.execute("SELECT COUNT(*) FROM naf;")
                naf_count = cur.fetchone()[0]
            except Exception as e:
                conn.rollback()
                return {"error": "table naf vide ou inexistante", "detail": str(e)}

            if naf_count == 0:
                return {"error": "table naf vide ou inexistante"}

            cur.execute("""
                UPDATE clients SET activite_r = n.libelle
                FROM naf n
                WHERE SPLIT_PART(code_naf_r::text, '.', 1) = n.code::text
                AND code_naf_r IS NOT NULL AND code_naf_r != '';
            """)
            updated = cur.rowcount
        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/trigger-activite", summary="Crée le trigger PostgreSQL qui maintient activite_r à jour")
def migrate_trigger_activite():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            # Fonction trigger
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_activite_r()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF (TG_OP = 'INSERT' OR NEW.code_naf_r IS DISTINCT FROM OLD.code_naf_r) THEN
                        SELECT libelle INTO NEW.activite_r
                        FROM naf
                        WHERE code = SPLIT_PART(NEW.code_naf_r::text, '.', 1);
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            # Supprime le trigger s'il existe déjà
            cur.execute("DROP TRIGGER IF EXISTS trigger_activite_r ON clients;")
            # Crée le trigger BEFORE INSERT OR UPDATE
            cur.execute("""
                CREATE TRIGGER trigger_activite_r
                BEFORE INSERT OR UPDATE OF code_naf_r ON clients
                FOR EACH ROW EXECUTE FUNCTION update_activite_r();
            """)
        conn.commit()
        return {"status": "ok", "trigger": "trigger_activite_r", "fonction": "update_activite_r"}
    finally:
        conn.close()




@app.get("/api/migrate/fix_juridique_exceptionnel", summary="Convertit juridique_exceptionnel en TEXT")
def fix_juridique_exceptionnel():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE clients
                ALTER COLUMN juridique_exceptionnel TYPE TEXT
                USING juridique_exceptionnel::text;
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/rendement_detail/{siret}", summary="Détail du calcul de rendement pour un client")
def rendement_detail(siret: str):
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT honoraires_cpta, temps_passe, anciennete, ca_r, resultat_r
                FROM clients WHERE siret = %s
            """, (siret,))
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Client {siret} introuvable")
    finally:
        conn.close()

    honos, temps, anciennete, ca, resultat = row

    facteurs = {}

    # — Taux horaire (poids 50) —
    taux_renseigne = (temps is not None and temps > 0 and honos is not None and honos > 0)
    if taux_renseigne:
        taux = float(honos) / float(temps)
        if   taux >= 120: pts_taux = 50; libelle_taux = ">120€ Plafond"
        elif taux >= 80:  pts_taux = round(25 + (taux - 80) * 25 / 40, 1); libelle_taux = "80-120€"
        elif taux >= 50:  pts_taux = round((taux - 50) * 25 / 30, 1);      libelle_taux = "50-80€"
        else:             pts_taux = 0; libelle_taux = "<50€"
        valeur_aff_taux = f"{taux:.1f} €/h"
    else:
        taux = None; pts_taux = 0; libelle_taux = "Non renseigné"; valeur_aff_taux = "—"

    facteurs["taux_horaire"] = {
        "valeur_brute":    {"honoraires_cpta": float(honos) if honos else None, "temps_passe": float(temps) if temps else None},
        "valeur_affichee": valeur_aff_taux,
        "points_obtenus":  pts_taux,
        "points_max":      50,
        "poids_pct":       50,
        "libelle_seuil":   libelle_taux,
        "renseigne":       taux_renseigne,
    }

    # — Ancienneté (poids 20) —
    anc_renseigne = (anciennete is not None and anciennete > 0)
    if anc_renseigne:
        a = float(anciennete)
        if   a > 10: pts_anc = 20; libelle_anc = ">10 ans Excellent"
        elif a >= 5: pts_anc = 15; libelle_anc = "5-10 ans"
        elif a >= 2: pts_anc = 10; libelle_anc = "2-5 ans"
        else:        pts_anc = 0;  libelle_anc = "<2 ans"
        valeur_aff_anc = f"{int(a)} an{'s' if a > 1 else ''}"
    else:
        pts_anc = 0; libelle_anc = "Non renseigné"; valeur_aff_anc = "—"

    facteurs["anciennete"] = {
        "valeur_brute":    float(anciennete) if anciennete is not None else None,
        "valeur_affichee": valeur_aff_anc,
        "points_obtenus":  pts_anc,
        "points_max":      20,
        "poids_pct":       20,
        "libelle_seuil":   libelle_anc,
        "renseigne":       anc_renseigne,
    }

    # — CA_r (poids 15) —
    ca_renseigne = (ca is not None and ca > 0)
    if ca_renseigne:
        c_val = float(ca)
        if   c_val >= 2_000_000: pts_ca = 15; libelle_ca = ">2M"
        elif c_val >= 500_000:   pts_ca = 12; libelle_ca = "500k-2M"
        elif c_val >= 100_000:   pts_ca = 7;  libelle_ca = "100-500k"
        else:                    pts_ca = 0;  libelle_ca = "<100k"
        valeur_aff_ca = f"{c_val:,.0f} €"
    else:
        pts_ca = 0; libelle_ca = "Non renseigné"; valeur_aff_ca = "—"

    facteurs["ca"] = {
        "valeur_brute":    float(ca) if ca is not None else None,
        "valeur_affichee": valeur_aff_ca,
        "points_obtenus":  pts_ca,
        "points_max":      15,
        "poids_pct":       15,
        "libelle_seuil":   libelle_ca,
        "renseigne":       ca_renseigne,
    }

    # — Résultat_r (poids 15) —
    res_renseigne = (resultat is not None)
    if res_renseigne:
        r_val = float(resultat)
        if   r_val >= 200_000: pts_res = 15; libelle_res = ">200k"
        elif r_val >= 50_000:  pts_res = 12; libelle_res = "50-200k"
        elif r_val >= 0:       pts_res = 7;  libelle_res = "0-50k"
        else:                  pts_res = 0;  libelle_res = "Négatif"
        valeur_aff_res = f"{r_val:,.0f} €"
    else:
        pts_res = 0; libelle_res = "Non renseigné"; valeur_aff_res = "—"

    facteurs["resultat"] = {
        "valeur_brute":    float(resultat) if resultat is not None else None,
        "valeur_affichee": valeur_aff_res,
        "points_obtenus":  pts_res,
        "points_max":      15,
        "poids_pct":       15,
        "libelle_seuil":   libelle_res,
        "renseigne":       res_renseigne,
    }

    # — Score global —
    nb_renseignes = sum([taux_renseigne, anc_renseigne, ca_renseigne, res_renseigne])

    if nb_renseignes < 2:
        score_brut       = None
        plafond_applique = None
        score_global     = None
    else:
        sum_pts   = pts_taux + pts_anc + pts_ca + pts_res
        sum_poids = (50 if taux_renseigne else 0) + (20 if anc_renseigne else 0) \
                  + (15 if ca_renseigne else 0)   + (15 if res_renseigne else 0)
        if sum_poids == 0:
            score_brut = plafond_applique = score_global = None
        else:
            score_brut = round(sum_pts * 100 / sum_poids, 1)
            if nb_renseignes == 2:
                plafond_applique = 70
                score_global     = round(min(score_brut, 70))
            elif nb_renseignes == 3:
                plafond_applique = 85
                score_global     = round(min(score_brut, 85))
            else:
                plafond_applique = None
                score_global     = round(score_brut)

    return {
        "siret":                   siret,
        "score_global":            score_global,
        "score_brut":              score_brut,
        "plafond_applique":        plafond_applique,
        "nb_facteurs_renseignes":  nb_renseignes,
        "facteurs":                facteurs,
    }


@app.get("/api/debug/rendement", summary="Retourne les données rendement de tous les clients triés par score DESC")
def debug_rendement():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT nom_client, ca_r, resultat_r, honoraires_cpta, temps_passe, anciennete, rendement
                FROM clients
                ORDER BY rendement DESC NULLS LAST;
            """)
            cols = ["nom_client", "ca_r", "resultat_r", "honoraires_cpta", "temps_passe", "anciennete", "rendement"]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/fix_activite_trigger", summary="Corrige update_activite_r() avec SPLIT_PART puis force recalcul")
def fix_activite_trigger():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_activite_r()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF (TG_OP = 'INSERT' OR NEW.code_naf_r IS DISTINCT FROM OLD.code_naf_r) THEN
                        SELECT libelle INTO NEW.activite_r
                        FROM naf
                        WHERE code = SPLIT_PART(NEW.code_naf_r::text, '.', 1);
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("UPDATE clients SET code_naf_r = code_naf_r;")
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "clients_recalcules": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/force_recalc_activite", summary="Recalcule activite_r depuis naf via SPLIT_PART sur code_naf_r")
def force_recalc_activite():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clients
                SET activite_r = (
                    SELECT libelle FROM naf
                    WHERE code = SPLIT_PART(code_naf_r::text, '.', 1)
                )
                WHERE code_naf_r IS NOT NULL;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/debug/naf_sample", summary="Échantillon de codes NAF pour vérifier le contenu de la table")
def debug_naf_sample():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT code, libelle FROM naf
                WHERE code IN ('5','6','56','43','85','55','45')
                ORDER BY code;
            """)
            rows = [{"code": r[0], "libelle": r[1]} for r in cur.fetchall()]
        return rows
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/debug/activite_function", summary="Retourne le code source de la fonction update_activite_r()")
def debug_activite_function():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = 'update_activite_r';")
            row = cur.fetchone()
        return {"definition": row[0] if row else None}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/debug/triggers", summary="Liste les triggers actifs sur la table clients")
def debug_triggers():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT trigger_name, event_manipulation, action_timing
                FROM information_schema.triggers
                WHERE event_object_table = 'clients'
                ORDER BY trigger_name, event_manipulation;
            """)
            cols = ["trigger_name", "event_manipulation", "action_timing"]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return rows
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/debug/colonnes_tvs_ca12", summary="Liste les colonnes TVS et CA12 de la table clients")
def debug_colonnes_tvs_ca12():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'clients'
                  AND (column_name LIKE '%tvs%' OR column_name LIKE '%ca12%')
                ORDER BY column_name
            """)
            return {"colonnes": [row[0] for row in cur.fetchall()]}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/debug/age_check/{siret}", summary="Retourne les données brutes anniversaire/age pour un client")
def debug_age_check(siret: str):
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT siret, anniversaire, age, anniversaire::text AS anniversaire_brut
                FROM clients
                WHERE siret = %s
            """, (siret,))
            row = cur.fetchone()
            if not row:
                return {"error": f"Client {siret} introuvable"}
            cols = ["siret", "anniversaire", "age", "anniversaire_brut"]
            return dict(zip(cols, row))
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_rendement", summary="Installe le trigger BEFORE qui calcule rendement depuis NEW.*")
def install_trigger_rendement():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_rendement_trigger()
                RETURNS TRIGGER AS $$
                DECLARE
                    v_pts_taux    NUMERIC := 0;
                    v_pts_anc     NUMERIC := 0;
                    v_pts_ca      NUMERIC := 0;
                    v_pts_res     NUMERIC := 0;
                    v_poids_taux  NUMERIC := 0;
                    v_poids_anc   NUMERIC := 0;
                    v_poids_ca    NUMERIC := 0;
                    v_poids_res   NUMERIC := 0;
                    v_taux        NUMERIC;
                    v_sum_pts     NUMERIC := 0;
                    v_sum_poids   NUMERIC := 0;
                    v_nb          INTEGER := 0;
                    v_score_brut  NUMERIC;
                BEGIN
                    -- Taux horaire (poids 50)
                    IF NEW.temps_passe IS NOT NULL AND NEW.temps_passe > 0
                       AND NEW.honoraires_cpta IS NOT NULL AND NEW.honoraires_cpta > 0 THEN
                        v_poids_taux := 50;
                        v_nb         := v_nb + 1;
                        v_taux := NEW.honoraires_cpta / NEW.temps_passe;
                        IF    v_taux >= 120 THEN v_pts_taux := 50;
                        ELSIF v_taux >= 80  THEN v_pts_taux := 25 + (v_taux - 80)  * 25 / 40;
                        ELSIF v_taux >= 50  THEN v_pts_taux := (v_taux - 50) * 25 / 30;
                        ELSE                     v_pts_taux := 0;
                        END IF;
                    END IF;

                    -- Ancienneté (poids 20)
                    IF NEW.anciennete IS NOT NULL AND NEW.anciennete > 0 THEN
                        v_poids_anc := 20;
                        v_nb        := v_nb + 1;
                        IF    NEW.anciennete > 10 THEN v_pts_anc := 20;
                        ELSIF NEW.anciennete >= 5 THEN v_pts_anc := 15;
                        ELSIF NEW.anciennete >= 2 THEN v_pts_anc := 10;
                        ELSE                           v_pts_anc := 0;
                        END IF;
                    END IF;

                    -- CA_r (poids 15)
                    IF NEW.ca_r IS NOT NULL AND NEW.ca_r > 0 THEN
                        v_poids_ca := 15;
                        v_nb       := v_nb + 1;
                        IF    NEW.ca_r >= 2000000 THEN v_pts_ca := 15;
                        ELSIF NEW.ca_r >= 500000  THEN v_pts_ca := 12;
                        ELSIF NEW.ca_r >= 100000  THEN v_pts_ca := 7;
                        ELSE                           v_pts_ca := 0;
                        END IF;
                    END IF;

                    -- Résultat_r (poids 15)
                    IF NEW.resultat_r IS NOT NULL THEN
                        v_poids_res := 15;
                        v_nb        := v_nb + 1;
                        IF    NEW.resultat_r >= 200000 THEN v_pts_res := 15;
                        ELSIF NEW.resultat_r >= 50000  THEN v_pts_res := 12;
                        ELSIF NEW.resultat_r >= 0      THEN v_pts_res := 7;
                        ELSE                                v_pts_res := 0;
                        END IF;
                    END IF;

                    -- Moins de 2 facteurs → NULL
                    IF v_nb < 2 THEN
                        NEW.rendement := NULL;
                        RETURN NEW;
                    END IF;

                    v_sum_pts    := v_pts_taux + v_pts_anc + v_pts_ca + v_pts_res;
                    v_sum_poids  := v_poids_taux + v_poids_anc + v_poids_ca + v_poids_res;

                    IF v_sum_poids = 0 THEN
                        NEW.rendement := NULL;
                        RETURN NEW;
                    END IF;

                    v_score_brut := v_sum_pts * 100 / v_sum_poids;

                    -- Plafond selon nombre de facteurs renseignés
                    IF    v_nb = 2 THEN NEW.rendement := ROUND(LEAST(v_score_brut, 70));
                    ELSIF v_nb = 3 THEN NEW.rendement := ROUND(LEAST(v_score_brut, 85));
                    ELSE                NEW.rendement := ROUND(v_score_brut);
                    END IF;

                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("DROP TRIGGER IF EXISTS update_rendement ON clients;")
            cur.execute("DROP TRIGGER IF EXISTS trg_rendement ON clients;")
            cur.execute("""
                CREATE TRIGGER trg_rendement
                BEFORE INSERT OR UPDATE OF honoraires_cpta, temps_passe, ca_r, resultat_r, anciennete
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_rendement_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/rendement_setup", summary="Crée la colonne rendement et la fonction calc_rendement()")
def rendement_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            # 1. Colonne rendement
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS rendement NUMERIC;")

            # 2. Fonction de calcul score 0-100
            # Taux horaire (honoraires_cpta / temps_passe) → 50 pts
            #   >= 120 €/h → 50 | >= 80 €/h → 35 | >= 50 €/h → 15 | < 50 → 0
            # Ancienneté → 20 pts
            #   >= 10 ans → 20 | >= 5 ans → 15 | >= 3 ans → 10 | >= 1 an → 5 | < 1 → 0
            # CA_r → 15 pts
            #   >= 50000 → 15 | >= 30000 → 10 | >= 15000 → 5 | < 15000 → 0
            # Résultat_r → 15 pts
            #   >= 30000 → 15 | >= 10000 → 10 | >= 0 → 5 | < 0 → 0
            cur.execute("""
                CREATE OR REPLACE FUNCTION calc_rendement(p_siret TEXT)
                RETURNS NUMERIC AS $$
                DECLARE
                    v_honos       NUMERIC;
                    v_temps       NUMERIC;
                    v_anciennete  NUMERIC;
                    v_ca          NUMERIC;
                    v_resultat    NUMERIC;
                    v_pts_taux    NUMERIC := 0;
                    v_pts_anc     NUMERIC := 0;
                    v_pts_ca      NUMERIC := 0;
                    v_pts_res     NUMERIC := 0;
                    v_poids_taux  NUMERIC := 0;
                    v_poids_anc   NUMERIC := 0;
                    v_poids_ca    NUMERIC := 0;
                    v_poids_res   NUMERIC := 0;
                    v_taux        NUMERIC;
                    v_sum_pts     NUMERIC := 0;
                    v_sum_poids   NUMERIC := 0;
                    v_nb          INTEGER := 0;
                    v_score_brut  NUMERIC;
                BEGIN
                    SELECT honoraires_cpta, temps_passe, anciennete, ca_r, resultat_r
                    INTO v_honos, v_temps, v_anciennete, v_ca, v_resultat
                    FROM clients WHERE siret = p_siret;

                    -- Taux horaire (poids 50)
                    IF v_temps IS NOT NULL AND v_temps > 0 AND v_honos IS NOT NULL AND v_honos > 0 THEN
                        v_poids_taux := 50;
                        v_nb         := v_nb + 1;
                        v_taux := v_honos / v_temps;
                        IF    v_taux >= 120 THEN v_pts_taux := 50;
                        ELSIF v_taux >= 80  THEN v_pts_taux := 25 + (v_taux - 80)  * 25 / 40;
                        ELSIF v_taux >= 50  THEN v_pts_taux := (v_taux - 50) * 25 / 30;
                        ELSE                     v_pts_taux := 0;
                        END IF;
                    END IF;

                    -- Ancienneté (poids 20)
                    IF v_anciennete IS NOT NULL AND v_anciennete > 0 THEN
                        v_poids_anc := 20;
                        v_nb        := v_nb + 1;
                        IF    v_anciennete > 10 THEN v_pts_anc := 20;
                        ELSIF v_anciennete >= 5 THEN v_pts_anc := 15;
                        ELSIF v_anciennete >= 2 THEN v_pts_anc := 10;
                        ELSE                         v_pts_anc := 0;
                        END IF;
                    END IF;

                    -- CA_r (poids 15)
                    IF v_ca IS NOT NULL AND v_ca > 0 THEN
                        v_poids_ca := 15;
                        v_nb       := v_nb + 1;
                        IF    v_ca >= 2000000 THEN v_pts_ca := 15;
                        ELSIF v_ca >= 500000  THEN v_pts_ca := 12;
                        ELSIF v_ca >= 100000  THEN v_pts_ca := 7;
                        ELSE                       v_pts_ca := 0;
                        END IF;
                    END IF;

                    -- Résultat_r (poids 15)
                    IF v_resultat IS NOT NULL THEN
                        v_poids_res := 15;
                        v_nb        := v_nb + 1;
                        IF    v_resultat >= 200000 THEN v_pts_res := 15;
                        ELSIF v_resultat >= 50000  THEN v_pts_res := 12;
                        ELSIF v_resultat >= 0      THEN v_pts_res := 7;
                        ELSE                            v_pts_res := 0;
                        END IF;
                    END IF;

                    -- Moins de 2 facteurs renseignés → NULL
                    IF v_nb < 2 THEN RETURN NULL; END IF;

                    v_sum_pts    := v_pts_taux + v_pts_anc + v_pts_ca + v_pts_res;
                    v_sum_poids  := v_poids_taux + v_poids_anc + v_poids_ca + v_poids_res;

                    IF v_sum_poids = 0 THEN RETURN NULL; END IF;

                    v_score_brut := v_sum_pts * 100 / v_sum_poids;

                    -- Plafond selon nombre de facteurs renseignés
                    IF    v_nb = 2 THEN RETURN ROUND(LEAST(v_score_brut, 70));
                    ELSIF v_nb = 3 THEN RETURN ROUND(LEAST(v_score_brut, 85));
                    ELSE                RETURN ROUND(v_score_brut);
                    END IF;
                END;
                $$ LANGUAGE plpgsql;
            """)

            # 3. Pré-calcule rendement pour tous les clients existants
            cur.execute("""
                UPDATE clients SET rendement = calc_rendement(siret);
            """)
            updated = cur.rowcount

        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/rendement_trigger", summary="Crée le trigger qui recalcule rendement automatiquement")
def rendement_trigger():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE OR REPLACE FUNCTION trigger_calc_rendement()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.rendement := calc_rendement(NEW.siret);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("DROP TRIGGER IF EXISTS update_rendement ON clients;")
            cur.execute("""
                CREATE TRIGGER update_rendement
                BEFORE INSERT OR UPDATE ON clients
                FOR EACH ROW EXECUTE FUNCTION trigger_calc_rendement();
            """)
        conn.commit()
        return {"status": "ok", "trigger": "update_rendement"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/rendement_recalc", summary="Recalcule rendement pour tous les clients")
def rendement_recalc():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE clients SET rendement = calc_rendement(siret);")
            updated = cur.rowcount
        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_franchise_tva", summary="Installe le trigger BEFORE qui calcule franchise_tva_prest depuis NEW.*")
def install_trigger_franchise_tva():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DROP FUNCTION IF EXISTS update_franchise_tva_trigger() CASCADE;
            """)
            cur.execute("""
                CREATE FUNCTION update_franchise_tva_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.ca_r IS NULL OR NEW.achat_revente IS NULL THEN
                        NEW.franchise_tva_prest := 'Données manquantes';
                    ELSIF NEW.ca_r < 37500 AND LOWER(NEW.achat_revente) = 'non' THEN
                        NEW.franchise_tva_prest := 'OUI';
                    ELSE
                        NEW.franchise_tva_prest := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("DROP TRIGGER IF EXISTS trg_franchise_tva ON clients;")
            cur.execute("""
                CREATE TRIGGER trg_franchise_tva
                BEFORE INSERT OR UPDATE OF ca_r, achat_revente
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_franchise_tva_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/arbitrage_remuneration_setup", summary="Ajoute et calcule la colonne arbitrage_remuneration_dirigeant")
def arbitrage_remuneration_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE clients
                ADD COLUMN IF NOT EXISTS arbitrage_remuneration_dirigeant TEXT;
            """)
            cur.execute("""
                UPDATE clients
                SET arbitrage_remuneration_dirigeant = CASE
                    WHEN resultat_r IS NULL THEN 'Donnée manquante'
                    WHEN resultat_r > 42500 THEN 'OUI'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/age_setup", summary="Ajoute la colonne age et calcule depuis anniversaire")
def age_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS age INTEGER;")
            cur.execute("""
                UPDATE clients
                SET age = EXTRACT(YEAR FROM AGE(NOW(), anniversaire))
                WHERE anniversaire IS NOT NULL;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/champs_libres_setup", summary="Ajoute les colonnes commentaires, code_naf_r et prevoyance si absentes")
def champs_libres_setup():
    colonnes = ["commentaires", "code_naf_r", "prevoyance"]
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS commentaires TEXT;")
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS code_naf_r TEXT;")
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS prevoyance TEXT;")
        conn.commit()
        return {"ok": True, "colonnes": colonnes}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/mission_patrimoniale_setup", summary="Calcule la colonne mission_patrimoniale depuis mai_ir")
def mission_patrimoniale_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ALTER COLUMN mission_patrimoniale TYPE TEXT;")
            cur.execute("""
                UPDATE clients
                SET mission_patrimoniale = CASE
                    WHEN mai_ir IS NULL THEN 'Données manquantes'
                    WHEN mai_ir > 8000 THEN 'OUI'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_mission_patrimoniale", summary="Installe le trigger BEFORE qui calcule mission_patrimoniale depuis mai_ir")
def install_trigger_mission_patrimoniale():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_mission_patrimoniale ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_mission_patrimoniale_trigger();")
            cur.execute("""
                CREATE FUNCTION update_mission_patrimoniale_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.mai_ir IS NULL THEN
                        NEW.mission_patrimoniale := 'Données manquantes';
                    ELSIF NEW.mai_ir > 8000 THEN
                        NEW.mission_patrimoniale := 'OUI';
                    ELSE
                        NEW.mission_patrimoniale := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_mission_patrimoniale
                BEFORE INSERT OR UPDATE OF mai_ir
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_mission_patrimoniale_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/mission_retraite_setup", summary="Calcule la colonne mission_retraite depuis age")
def mission_retraite_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ALTER COLUMN mission_retraite TYPE TEXT;")
            cur.execute("""
                UPDATE clients
                SET mission_retraite = CASE
                    WHEN age IS NULL THEN 'Données manquantes'
                    WHEN age > 50 AND age < 65 THEN 'OUI'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_mission_retraite", summary="Installe le trigger BEFORE qui calcule mission_retraite depuis age")
def install_trigger_mission_retraite():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_mission_retraite ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_mission_retraite_trigger();")
            cur.execute("""
                CREATE FUNCTION update_mission_retraite_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.age IS NULL THEN
                        NEW.mission_retraite := 'Données manquantes';
                    ELSIF NEW.age > 50 AND NEW.age < 65 THEN
                        NEW.mission_retraite := 'OUI';
                    ELSE
                        NEW.mission_retraite := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_mission_retraite
                BEFORE INSERT OR UPDATE OF age, anniversaire
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_mission_retraite_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/refresh_age", summary="Recalcule la colonne age depuis anniversaire pour tous les clients")
def refresh_age():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clients
                SET age = EXTRACT(YEAR FROM AGE(NOW(), anniversaire))
                WHERE anniversaire IS NOT NULL;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_age", summary="Installe le trigger BEFORE qui calcule age depuis anniversaire")
def install_trigger_age():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_age ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_age_trigger();")
            cur.execute("""
                CREATE FUNCTION update_age_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.age := EXTRACT(YEAR FROM AGE(NOW(), NEW.anniversaire));
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_age
                BEFORE INSERT OR UPDATE OF anniversaire
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_age_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/mission_placement_setup", summary="Calcule la colonne mission_placement depuis ca_r et tresorerie_r")
def mission_placement_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clients
                SET mission_placement = CASE
                    WHEN ca_r IS NULL OR tresorerie_r IS NULL
                        THEN 'Données manquantes'
                    WHEN ca_r > 50000
                         AND tresorerie_r > 50000
                         AND tresorerie_r * 100.0 / ca_r > 25
                        THEN 'OPPORTUNITÉ FORTE'
                    WHEN ca_r > 50000
                         AND tresorerie_r > 20000
                         AND tresorerie_r * 100.0 / ca_r > 15
                        THEN 'OPPORTUNITÉ MOYENNE'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/op_prevoyance_setup", summary="Ajoute et calcule la colonne op_prevoyance")
def op_prevoyance_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE clients
                ADD COLUMN IF NOT EXISTS op_prevoyance TEXT;
            """)
            cur.execute("""
                UPDATE clients
                SET op_prevoyance = CASE
                    WHEN prevoyance IS NULL OR structure IS NULL
                        THEN 'Donnée manquante'
                    WHEN LOWER(prevoyance) = 'non'
                         AND UPPER(structure) IN ('EI', 'SARL')
                        THEN 'OUI'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_mission_placement", summary="Installe le trigger BEFORE qui calcule mission_placement depuis NEW.*")
def install_trigger_mission_placement():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_mission_placement ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_mission_placement_trigger();")
            cur.execute("""
                CREATE FUNCTION update_mission_placement_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.ca_r IS NULL OR NEW.tresorerie_r IS NULL THEN
                        NEW.mission_placement := 'Données manquantes';
                    ELSIF NEW.ca_r > 50000
                          AND NEW.tresorerie_r > 50000
                          AND NEW.tresorerie_r * 100.0 / NEW.ca_r > 25 THEN
                        NEW.mission_placement := 'OPPORTUNITÉ FORTE';
                    ELSIF NEW.ca_r > 50000
                          AND NEW.tresorerie_r > 20000
                          AND NEW.tresorerie_r * 100.0 / NEW.ca_r > 15 THEN
                        NEW.mission_placement := 'OPPORTUNITÉ MOYENNE';
                    ELSE
                        NEW.mission_placement := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_mission_placement
                BEFORE INSERT OR UPDATE OF ca_r, tresorerie_r
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_mission_placement_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_op_prevoyance", summary="Installe le trigger BEFORE qui calcule op_prevoyance depuis NEW.*")
def install_trigger_op_prevoyance():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_op_prevoyance ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_op_prevoyance_trigger();")
            cur.execute("""
                CREATE FUNCTION update_op_prevoyance_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.prevoyance IS NULL OR NEW.structure IS NULL THEN
                        NEW.op_prevoyance := 'Donnée manquante';
                    ELSIF LOWER(NEW.prevoyance) = 'non'
                          AND UPPER(NEW.structure) IN ('EI', 'SARL') THEN
                        NEW.op_prevoyance := 'OUI';
                    ELSE
                        NEW.op_prevoyance := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_op_prevoyance
                BEFORE INSERT OR UPDATE OF prevoyance, structure
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_op_prevoyance_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_arbitrage_remuneration", summary="Installe le trigger BEFORE qui calcule arbitrage_remuneration_dirigeant depuis NEW.*")
def install_trigger_arbitrage_remuneration():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_arbitrage_remuneration ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_arbitrage_remuneration_trigger();")
            cur.execute("""
                CREATE FUNCTION update_arbitrage_remuneration_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.resultat_r IS NULL THEN
                        NEW.arbitrage_remuneration_dirigeant := 'Donnée manquante';
                    ELSIF NEW.resultat_r > 42500 THEN
                        NEW.arbitrage_remuneration_dirigeant := 'OUI';
                    ELSE
                        NEW.arbitrage_remuneration_dirigeant := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_arbitrage_remuneration
                BEFORE INSERT OR UPDATE OF resultat_r
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_arbitrage_remuneration_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/franchise_tva_achrevente_setup", summary="Ajoute et calcule la colonne franchise_tva_achrevente")
def franchise_tva_achrevente_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE clients
                ADD COLUMN IF NOT EXISTS franchise_tva_achrevente TEXT;
            """)
            cur.execute("""
                UPDATE clients
                SET franchise_tva_achrevente = CASE
                    WHEN ca_r IS NULL OR achat_revente IS NULL
                        THEN 'Données manquantes'
                    WHEN LOWER(achat_revente) = 'oui' AND ca_r BETWEEN 0 AND 85000
                        THEN 'OUI'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/install_trigger_franchise_achrevente", summary="Installe le trigger BEFORE qui calcule franchise_tva_achrevente depuis NEW.*")
def install_trigger_franchise_achrevente():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER IF EXISTS trg_franchise_achrevente ON clients;")
            cur.execute("DROP FUNCTION IF EXISTS update_franchise_achrevente_trigger();")
            cur.execute("""
                CREATE FUNCTION update_franchise_achrevente_trigger()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.ca_r IS NULL OR NEW.achat_revente IS NULL THEN
                        NEW.franchise_tva_achrevente := 'Données manquantes';
                    ELSIF LOWER(NEW.achat_revente) = 'oui' AND NEW.ca_r BETWEEN 0 AND 85000 THEN
                        NEW.franchise_tva_achrevente := 'OUI';
                    ELSE
                        NEW.franchise_tva_achrevente := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE TRIGGER trg_franchise_achrevente
                BEFORE INSERT OR UPDATE OF ca_r, achat_revente
                ON clients
                FOR EACH ROW EXECUTE FUNCTION update_franchise_achrevente_trigger();
            """)
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/franchise_tva_setup", summary="Ajoute et calcule la colonne franchise_tva_prest")
def franchise_tva_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE clients
                ADD COLUMN IF NOT EXISTS franchise_tva_prest TEXT;
            """)
            cur.execute("""
                UPDATE clients
                SET franchise_tva_prest = CASE
                    WHEN ca_r IS NULL OR achat_revente IS NULL
                        THEN 'Données manquantes'
                    WHEN ca_r < 37500 AND LOWER(achat_revente) = 'non'
                        THEN 'OUI'
                    ELSE NULL
                END;
            """)
            updated = cur.rowcount
        conn.commit()
        return {"status": "ok", "clients_mis_a_jour": updated}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


@app.get("/api/migrate/tvs_mois_setup", summary="Ajoute les colonnes mensuelles TVS et remet janvier/mai à NULL")
def migrate_tvs_mois_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cols = [
                "fevrier_tvs", "mars_tvs", "avril_tvs", "juin_tvs",
                "juillet_tvs", "aout_tvs", "septembre_tvs",
                "octobre_tvs", "novembre_tvs", "decembre_tvs",
            ]
            for col in cols:
                cur.execute(f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS {col} NUMERIC")
            cur.execute("UPDATE clients SET janvier_tvs = NULL, mai_tvs = NULL")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/migrate/drop_mai_ca12", summary="Supprime la colonne mai_ca12 de la table clients")
def migrate_drop_mai_ca12():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients DROP COLUMN IF EXISTS mai_ca12")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/migrate/ca12_solde_setup", summary="Ajoute les 12 colonnes mensuelles CA12 solde (NUMERIC)")
def migrate_ca12_solde_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cols = [
                "janvier_ca12_solde", "fevrier_ca12_solde", "mars_ca12_solde",
                "avril_ca12_solde",   "mai_ca12_solde",     "juin_ca12_solde",
                "juillet_ca12_solde", "aout_ca12_solde",    "septembre_ca12_solde",
                "octobre_ca12_solde", "novembre_ca12_solde","decembre_ca12_solde",
            ]
            for col in cols:
                cur.execute(f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS {col} NUMERIC")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/migrate/fix_mai_tvs_type", summary="Convertit mai_tvs en NUMERIC")
def migrate_fix_mai_tvs_type():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ALTER COLUMN mai_tvs TYPE NUMERIC USING mai_tvs::numeric")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/migrate/cvae_acomptes_setup", summary="Ajoute les colonnes acompte CVAE juin et septembre")
def migrate_cvae_acomptes_setup():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS acompte_cvae_juin NUMERIC")
            cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS acompte_cvae_septembre NUMERIC")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/migrate/add_indexes", summary="Crée les index PostgreSQL courants sur la table clients")
def add_indexes():
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_nom       ON clients(nom_client)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_collab    ON clients(collaborateur)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_assistant ON clients(assistant)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_annee     ON clients(annee)")
        conn.commit()
        return {"ok": True}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── Static files ──────────────────────────────────────────────────────────────
# Monté en dernier pour ne pas masquer les routes API.

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
