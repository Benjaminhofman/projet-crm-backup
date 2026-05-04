import os
from decimal import Decimal

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.fec_parser import parse_multiple_fec
from app.core.indicators import calculate_indicators

app = FastAPI(
    title="FEC Explorer API",
    description="Parse des fichiers FEC et calcule les indicateurs financiers par SIRET.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
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
    import re
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


# ── Static files ──────────────────────────────────────────────────────────────
# Monté en dernier pour ne pas masquer les routes API.

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
