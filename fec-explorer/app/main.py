import csv
import os
import re
import threading
from decimal import Decimal
from typing import Any, Dict, List

import psycopg2
import psycopg2.extras
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.fec_parser import parse_multiple_fec
from app.core.indicators import calculate_indicators

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
    threading.Thread(target=_recalcul_anciennete, daemon=True).start()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ── Schémas ───────────────────────────────────────────────────────────────────

class FolderRequest(BaseModel):
    folder_path: str

class UpdateRequest(BaseModel):
    siret: str
    field: str
    value: object


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


_BOOL_TRUE     = {"oui", "true", "1", "yes"}
_BOOL_FALSE    = {"non", "false", "0", "no"}
_BOOL_STRS     = _BOOL_TRUE | _BOOL_FALSE
_NUMERIC_TYPES = ("numeric", "integer", "bigint", "smallint", "real", "double", "decimal", "money")
_DATE_TYPES    = ("date", "timestamp")


def _coerce_import_value(val: Any, data_type: str) -> Any:
    """
    Convertit val selon le type PostgreSQL de la colonne cible.
    Retourne None pour les valeurs vides ou non convertibles
    (le champ sera alors exclu de l'UPSERT).
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    dt = data_type.lower()

    # Date / timestamp : DD/MM/YYYY → ISO YYYY-MM-DD
    if any(t in dt for t in _DATE_TYPES):
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return s  # déjà ISO ou autre format → PostgreSQL gère

    # Boolean
    if dt == "boolean":
        v = s.lower()
        if v in _BOOL_TRUE:
            return True
        if v in _BOOL_FALSE:
            return False
        return None  # valeur non reconnue → NULL (champ ignoré)

    # Numeric
    if any(t in dt for t in _NUMERIC_TYPES):
        if s.lower() in _BOOL_STRS:
            return None  # "oui"/"non" dans un champ numérique → NULL
        try:
            return float(s.replace(",", ".").replace(" ", "").replace(" ", ""))
        except ValueError:
            return None

    # Texte et autres types : inchangé
    return s


# ── Routes API ────────────────────────────────────────────────────────────────

@app.get("/api/clients", summary="Liste tous les clients depuis PostgreSQL")
def get_clients():
    conn = _get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM clients ORDER BY siret")
            rows = [
                {k: _serialize(v) for k, v in row.items()}
                for row in cur.fetchall()
            ]
        return rows
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

    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            # Le nom de colonne est entre guillemets doubles (identifiant SQL)
            cur.execute(
                f'UPDATE clients SET "{field}" = %s WHERE siret = %s',
                (value, siret),
            )
            if cur.rowcount == 0:
                return {"error": f"Aucun client trouvé avec siret={siret!r}"}
        conn.commit()
        return {"success": True}
    except psycopg2.Error as e:
        conn.rollback()
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


@app.post("/api/clients/import", summary="UPSERT en masse d'une liste de clients JSON")
def import_clients(body: List[Dict[str, Any]] = Body(...)):
    if not body:
        raise HTTPException(status_code=400, detail="Liste vide.")

    conn = _get_db_conn()
    upserted = 0
    errors: List[str] = []

    try:
        # Récupère colonnes + types PostgreSQL une seule fois
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'clients'"
            )
            col_types = {row[0]: row[1] for row in cur.fetchall()}

        for i, item in enumerate(body):
            if not isinstance(item, dict):
                continue
            siret = str(item.get("siret", "")).strip()
            if not siret:
                errors.append(f"Ligne {i + 1} : siret manquant")
                continue

            # Filtre + conversion typée : seules les colonnes réelles sont conservées
            fields = {}
            for k, v in item.items():
                if not (_COL_RE.match(str(k)) and k in col_types):
                    continue
                coerced = _coerce_import_value(v, col_types[k])
                if coerced is not None:
                    fields[k] = coerced

            if not fields:
                errors.append(f"Ligne {i + 1} ({siret}) : aucun champ valide")
                continue

            cols         = ", ".join(f'"{k}"' for k in fields)
            placeholders = ", ".join("%s" for _ in fields)
            updates      = ", ".join(
                f'"{k}" = EXCLUDED."{k}"' for k in fields if k != "siret"
            )
            values = list(fields.values())

            try:
                with conn.cursor() as cur:
                    if updates:
                        cur.execute(
                            f"INSERT INTO clients ({cols}) VALUES ({placeholders}) "
                            f"ON CONFLICT (siret) DO UPDATE SET {updates}",
                            values,
                        )
                    else:
                        cur.execute(
                            f"INSERT INTO clients ({cols}) VALUES ({placeholders}) "
                            f"ON CONFLICT (siret) DO NOTHING",
                            values,
                        )
                conn.commit()
                upserted += 1
            except psycopg2.Error as e:
                conn.rollback()
                errors.append(f"{siret} : {e.pgerror or str(e)}")

        return {"success": True, "upserted": upserted, "errors": errors}
    finally:
        conn.close()


@app.post("/api/fec/upload", summary="Parse un dossier FEC et retourne les indicateurs")
def upload_fec(body: FolderRequest):
    folder = body.folder_path

    if not os.path.isdir(folder):
        raise HTTPException(
            status_code=400,
            detail=f"Dossier introuvable ou inaccessible : {folder}",
        )

    rows = parse_multiple_fec(folder)

    if not rows:
        raise HTTPException(
            status_code=422,
            detail="Aucun fichier FEC valide trouvé dans ce dossier (pattern attendu : 9chiffres+FEC+8chiffres.txt).",
        )

    indicateurs = calculate_indicators(rows)

    return {
        "folder":      folder,
        "nb_entites":  len(indicateurs),
        "indicateurs": indicateurs,
    }


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


@app.get("/api/migrate/naf", summary="Crée la table NAF et importe libelle_naf.csv")
def migrate_naf():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "libelle_naf.csv")
    if not os.path.isfile(csv_path):
        raise HTTPException(status_code=404, detail=f"Fichier libelle_naf.csv introuvable : {csv_path}")

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
            with open(csv_path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    code = (row.get("Code") or "").strip()
                    libelle = (row.get("Libellé") or "").strip()
                    if not code or not libelle:
                        continue
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
    finally:
        conn.close()


# ── Static files ──────────────────────────────────────────────────────────────
# Monté en dernier pour ne pas masquer les routes API.

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
