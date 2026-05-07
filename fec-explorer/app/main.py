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
                WHERE CAST(SPLIT_PART(CAST(code_naf_r AS TEXT), '.', 1) AS INTEGER) = CAST(n.code AS INTEGER)
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


# ── Static files ──────────────────────────────────────────────────────────────
# Monté en dernier pour ne pas masquer les routes API.

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
