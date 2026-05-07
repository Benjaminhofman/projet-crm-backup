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
                    v_honos      NUMERIC;
                    v_temps      NUMERIC;
                    v_taux       NUMERIC;
                    v_anciennete NUMERIC;
                    v_ca         NUMERIC;
                    v_resultat   NUMERIC;
                    v_score      NUMERIC := 0;
                    v_pts_taux   NUMERIC := 0;
                BEGIN
                    SELECT
                        COALESCE(honoraires_cpta, 0),
                        COALESCE(temps_passe, 0),
                        COALESCE(anciennete, 0),
                        COALESCE(ca_r, 0),
                        COALESCE(resultat_r, 0)
                    INTO v_honos, v_temps, v_anciennete, v_ca, v_resultat
                    FROM clients WHERE siret = p_siret;

                    -- Taux horaire (50 pts) — linéaire par tranche
                    -- <50€=0 | 50-80€=0→25 linéaire | 80-120€=25→50 linéaire | >120€=50
                    IF v_temps > 0 THEN
                        v_taux := v_honos / v_temps;
                        IF v_taux >= 120 THEN
                            v_pts_taux := 50;
                        ELSIF v_taux >= 80 THEN
                            v_pts_taux := 25 + (v_taux - 80) * 25 / 40;
                        ELSIF v_taux >= 50 THEN
                            v_pts_taux := (v_taux - 50) * 25 / 30;
                        ELSE
                            v_pts_taux := 0;
                        END IF;
                    END IF;
                    v_score := v_score + v_pts_taux;

                    -- Ancienneté (20 pts)
                    -- <2ans=0 | 2-5=10 | 5-10=15 | >10=20
                    IF    v_anciennete > 10 THEN v_score := v_score + 20;
                    ELSIF v_anciennete >= 5 THEN v_score := v_score + 15;
                    ELSIF v_anciennete >= 2 THEN v_score := v_score + 10;
                    END IF;

                    -- CA_r (15 pts)
                    -- <100k=0 | 100-500k=7 | 500k-2M=12 | >2M=15
                    IF    v_ca >= 2000000 THEN v_score := v_score + 15;
                    ELSIF v_ca >= 500000  THEN v_score := v_score + 12;
                    ELSIF v_ca >= 100000  THEN v_score := v_score + 7;
                    END IF;

                    -- Résultat_r (15 pts)
                    -- <0=0 | 0-50k=7 | 50k-200k=12 | >200k=15
                    IF    v_resultat >= 200000 THEN v_score := v_score + 15;
                    ELSIF v_resultat >= 50000  THEN v_score := v_score + 12;
                    ELSIF v_resultat >= 0      THEN v_score := v_score + 7;
                    END IF;

                    RETURN ROUND(LEAST(v_score, 100), 0);
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


# ── Static files ──────────────────────────────────────────────────────────────
# Monté en dernier pour ne pas masquer les routes API.

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")

@app.get("/index.html")
async def serve_index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
