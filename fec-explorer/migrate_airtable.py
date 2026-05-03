"""
migrate_airtable.py
Migre tous les enregistrements Airtable vers PostgreSQL via UPSERT sur le champ siret.

Usage :
    AIRTABLE_TOKEN=xxx DATABASE_URL=postgresql://user:pass@host:5432/db python migrate_airtable.py
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import psycopg2
except ImportError:
    print("Erreur : psycopg2 non installé. Lance : pip install psycopg2-binary")
    sys.exit(1)

BASE_ID  = "appcYhoQfSuz8ozil"
TABLE_ID = "tblm1aQ4OJ9W1hwm8"

# Identifiants SQL qui nécessitent des guillemets doubles
_RE_DIGIT  = re.compile(r"^\d")
_RESERVED  = {"is", "order", "table", "user", "type", "end", "start", "check", "index"}

# Champs Airtable à ne pas migrer vers PostgreSQL (noms normalisés)
CHAMPS_A_IGNORER = frozenset({
    "mission_retraite",
    "mission_patrimoniale",
    "mission_placement",
    "franchise_tva_prest",
    "franchise_tva_achrevente",
    "op_prevoyance",
    "lien_modification",
    "arbitrage_remuneration_dirigeant",
    "anciennete",
    "age",
    "souhait_anniversaire",
    "rentabilite",
    "creer_client",
})

# Table de remplacement des caractères accentués (minuscules + majuscules)
_ACCENT_MAP = str.maketrans({
    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'à': 'a', 'â': 'a', 'ä': 'a',
    'ô': 'o', 'ö': 'o',
    'û': 'u', 'ù': 'u', 'ü': 'u',
    'î': 'i', 'ï': 'i',
    'ç': 'c',
    'É': 'e', 'È': 'e', 'Ê': 'e', 'Ë': 'e',
    'À': 'a', 'Â': 'a', 'Ä': 'a',
    'Ô': 'o', 'Ö': 'o',
    'Û': 'u', 'Ù': 'u', 'Ü': 'u',
    'Î': 'i', 'Ï': 'i',
    'Ç': 'c',
})
_RE_SPECIAL = re.compile(r"[^a-z0-9_]+")
_RE_MULTI_  = re.compile(r"_+")


def normalize_field_name(name: str) -> str:
    """
    Convertit un nom de champ Airtable en identifiant SQL valide :
      1. Supprime les accents (é→e, è→e, à→a, ê→e, ô→o, û→u, î→i, ù→u, ç→c, ...)
      2. Met tout en minuscules
      3. Remplace espaces, apostrophes et tirets par _
      4. Supprime tous les caractères spéciaux restants sauf _
      5. Réduit les __ consécutifs en un seul _
    """
    s = name.strip()
    s = s.translate(_ACCENT_MAP)          # accents → ASCII
    s = s.lower()                          # minuscules
    s = s.replace("'", "_").replace("-", "_").replace(" ", "_")
    s = _RE_SPECIAL.sub("_", s)           # autres caractères spéciaux → _
    s = _RE_MULTI_.sub("_", s)            # __ → _
    return s.strip("_")


def _qi(col: str) -> str:
    """Guillemets doubles si le nom commence par un chiffre ou est un mot réservé SQL."""
    if _RE_DIGIT.match(col) or col in _RESERVED:
        return f'"{col}"'
    return col


# ── Airtable ──────────────────────────────────────────────────────────────────

def fetch_all_records(token: str) -> list:
    """Récupère tous les enregistrements Airtable avec pagination automatique."""
    url_base = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    records  = []
    offset   = None
    page     = 1

    while True:
        params = {"pageSize": "100"}
        if offset:
            params["offset"] = offset

        url = f"{url_base}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Airtable HTTP {e.code} : {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Airtable réseau : {e.reason}") from e

        batch = data.get("records", [])
        records.extend(batch)
        print(f"  page {page} : {len(batch)} enregistrement(s) récupéré(s)")

        offset = data.get("offset")
        if not offset:
            break

        page += 1
        time.sleep(0.2)  # respecte la limite 5 req/sec Airtable

    return records


# ── PostgreSQL ────────────────────────────────────────────────────────────────

def build_upsert(pg: dict) -> tuple:
    """
    Construit la requête UPSERT et la liste de valeurs pour un enregistrement.
    Retourne (sql, values).
    """
    cols   = list(pg.keys())
    q_cols = [_qi(c) for c in cols]
    vals   = [pg[c] for c in cols]

    update_parts = [
        f"{_qi(c)} = EXCLUDED.{_qi(c)}"
        for c in cols if c != "siret"
    ]

    if update_parts:
        on_conflict = f"DO UPDATE SET {', '.join(update_parts)}"
    else:
        on_conflict = "DO NOTHING"

    sql = (
        f"INSERT INTO clients ({', '.join(q_cols)}) "
        f"VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT (siret) {on_conflict}"
    )
    return sql, vals


def upsert_record(cur, fields: dict) -> bool:
    """
    Upsert un enregistrement Airtable dans PostgreSQL.
    - Mappe les noms Airtable vers colonnes SQL (snake_case).
    - Ignore les valeurs None et chaînes vides pour ne pas écraser l'existant.
    - Retourne False si le champ siret est absent ou vide.
    """
    pg = {}
    for at_name, value in fields.items():
        if value is None or value == "":
            continue
        col = normalize_field_name(at_name)
        if col and col not in CHAMPS_A_IGNORER:
            pg[col] = value

    siret = str(pg.get("siret", "")).strip()
    if not siret:
        return False
    pg["siret"] = siret

    sql, vals = build_upsert(pg)
    cur.execute(sql, vals)
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("AIRTABLE_TOKEN")
    if not token:
        print("Erreur : variable d'environnement AIRTABLE_TOKEN non définie.")
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Erreur : variable d'environnement DATABASE_URL non définie.")
        print("Exemple : DATABASE_URL=postgresql://user:password@localhost:5432/crm")
        sys.exit(1)

    # ── Récupération Airtable ─────────────────────────────────────────────────
    print(f"Récupération des enregistrements depuis Airtable ({TABLE_ID})...")
    try:
        records = fetch_all_records(token)
    except RuntimeError as e:
        print(f"Erreur Airtable : {e}")
        sys.exit(1)

    print(f"Total : {len(records)} enregistrement(s) récupéré(s).\n")

    # ── Migration PostgreSQL ──────────────────────────────────────────────────
    print("Migration vers PostgreSQL...")
    migrated = 0
    skipped  = 0
    errors   = 0

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cur:
            for rec in records:
                try:
                    ok = upsert_record(cur, rec.get("fields", {}))
                    if ok:
                        migrated += 1
                    else:
                        skipped += 1
                except psycopg2.Error as e:
                    # Colonne absente du schéma → on logue et on continue
                    conn.rollback()
                    print(f"  Avertissement (id={rec.get('id')}) : {e}")
                    errors += 1
                    # Réouvre le curseur après rollback
                    cur = conn.cursor()

        conn.commit()

    except psycopg2.Error as e:
        print(f"Erreur PostgreSQL (connexion) : {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if conn:
            conn.close()

    # ── Rapport ───────────────────────────────────────────────────────────────
    print(f"\n{migrated} ligne(s) migrée(s).")
    if skipped:
        print(f"{skipped} enregistrement(s) ignoré(s) (sans SIRET).")
    if errors:
        print(f"{errors} enregistrement(s) en erreur (colonne inconnue ou type incompatible).")


if __name__ == "__main__":
    main()
