import os
from decimal import Decimal

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
