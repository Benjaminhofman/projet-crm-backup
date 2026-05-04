"""
import_csv.py
Importe Base_clients-table_principale.csv vers PostgreSQL via UPSERT sur siret.

Usage :
    DATABASE_URL=postgresql://user:pass@host:5432/db python import_csv.py [chemin_csv]
"""
import os
import re
import sys
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("Erreur : pandas non installé. Lance : pip install pandas")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("Erreur : psycopg2 non installé. Lance : pip install psycopg2-binary")
    sys.exit(1)

DEFAULT_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "Base clients-table principale.csv",
)

# ── Normalisation des noms de colonnes ────────────────────────────────────────

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
    s = name.strip().translate(_ACCENT_MAP).lower()
    s = s.replace("'", "_").replace("-", "_").replace(" ", "_")
    s = _RE_SPECIAL.sub("_", s)
    return _RE_MULTI_.sub("_", s).strip("_")


# ── Colonnes à ignorer (comparaison sur noms normalisés) ──────────────────────

COLS_A_IGNORER = frozenset(normalize_field_name(n) for n in [
    "Lien modification",
    "Créer client",
    "age",
    "ancienneté",
    "souhait anniversaire",
    "rentabilite",
    "mission retraite",
    "mission patrimoniale",
    "mission placement",
    "franchise TVA prest",
    "franchise TVA achrevente",
    "op Prevoyance",
    "arbitrage rémunération dirigeant",
])

# ── Identifiants SQL nécessitant des guillemets doubles ───────────────────────

_RE_DIGIT = re.compile(r"^\d")
_RESERVED = {"is", "order", "table", "user", "type", "end", "start", "check", "index"}


def _qi(col: str) -> str:
    if _RE_DIGIT.match(col) or col in _RESERVED:
        return f'"{col}"'
    return col


# ── Conversion de valeurs ───────────────────────────────────────────────────

_DATE_COL     = re.compile(r"^date|anniversaire")
_FR_DATE_FMTS = ("%d/%m/%Y", "%d/%m/%y", "%d/%m/%Y %H:%M", "%Y-%m-%d")

# Colonnes dont on attend un booléen (nom normalisé)
_BOOL_COL = re.compile(r"mandat|mission|assujetti|redevable|actif|valide|certifie")

# Colonnes dont on attend un nombre (nom normalisé)
_NUM_COL = re.compile(r"montant|chiffre|ca|honoraire|revenu|capital|effectif|taux|solde")

# Valeurs booléennes reconnues
_BOOL_VALS: dict = {
    "checked": True,
    "true":    True,
    "oui":     True,
    "false":   False,
    "non":     False,
}

# Nombre décimal français : "1 234,56" ou "1234,56" (espace ordinaire ou insécable)
_FR_NUM = re.compile(r"^-?[\d  ]+,\d+$")


def parse_french_date(val: str):
    for fmt in _FR_DATE_FMTS:
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val


def clean_value(val, col: str):
    """
    Convertit une valeur CSV vers un type Python adapté à psycopg2 :
      - NaN / vide                 → None
      - colonne booléenne            → True/False, ou None si valeur non reconnue
      - oui/non/checked/true/false → True/False (toutes colonnes)
      - colonne date + slash       → ISO "YYYY-MM-DD"
      - "1 234,56"                 → float, ou None si non convertible
      - colonne numérique          → float, ou None si non convertible
      - sinon                      → chaîne brute
    """
    if pd.isna(val):
        return None

    if not isinstance(val, str):
        return val

    val = val.strip()
    if not val:
        return None

    v = val.lower()

    # Colonnes booléennes : strict — None si valeur non reconnue
    if _BOOL_COL.search(col):
        return _BOOL_VALS.get(v)

    # Valeurs booléennes universelles (oui/non, checked, true/false)
    if v in _BOOL_VALS:
        return _BOOL_VALS[v]

    # Date française → ISO
    if _DATE_COL.search(col) and "/" in val:
        return parse_french_date(val)

    # Nombre décimal français "1 234,56" → float (None si non convertible)
    if _FR_NUM.match(val):
        try:
            return float(val.replace(" ", "").replace(" ", "").replace(",", "."))
        except ValueError:
            return None

    # Colonnes numériques : float ou None si non convertible
    if _NUM_COL.search(col):
        try:
            return float(val.replace(",", "."))
        except ValueError:
            return None

    return val


# ── UPSERT PostgreSQL ─────────────────────────────────────────────────────────

def upsert_row(cur, row_dict: dict) -> bool:
    """
    Exécute un UPSERT pour une ligne du CSV.
    Retourne False si le champ siret est absent ou vide.
    """
    siret = str(row_dict.get("siret", "")).strip()
    if not siret:
        return False
    row_dict["siret"] = siret

    cols   = list(row_dict.keys())
    q_cols = [_qi(c) for c in cols]
    vals   = [row_dict[c] for c in cols]

    update_parts = [
        f"{_qi(c)} = EXCLUDED.{_qi(c)}"
        for c in cols if c != "siret"
    ]
    on_conflict = f"DO UPDATE SET {', '.join(update_parts)}" if update_parts else "DO NOTHING"

    sql = (
        f"INSERT INTO clients ({', '.join(q_cols)}) "
        f"VALUES ({', '.join(['%s'] * len(cols))}) "
        f"ON CONFLICT (siret) {on_conflict}"
    )
    cur.execute(sql, vals)
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Erreur : variable d'environnement DATABASE_URL non définie.")
        print("Exemple : DATABASE_URL=postgresql://user:password@localhost:5432/crm")
        sys.exit(1)

    if not os.path.exists(csv_path):
        print(f"Erreur : fichier introuvable → {csv_path}")
        sys.exit(1)

    # ── Lecture CSV ───────────────────────────────────────────────────────────
    # Auto-détecte le séparateur (virgule ou point-virgule)
    with open(csv_path, encoding="utf-8-sig") as f:
        first_line = f.readline()
    sep = ";" if first_line.count(";") > first_line.count(",") else ","

    print(f"Lecture de {os.path.basename(csv_path)} (séparateur : '{sep}')...")
    df = pd.read_csv(csv_path, encoding="utf-8-sig", sep=sep, dtype=str)
    print(f"{len(df)} ligne(s) lue(s), {len(df.columns)} colonne(s).\n")

    # ── Normalisation des colonnes ────────────────────────────────────────────
    df.columns = [normalize_field_name(c) for c in df.columns]

    # Colonnes ignorées présentes dans le CSV
    ignored_present = [c for c in df.columns if c in COLS_A_IGNORER]
    if ignored_present:
        print(f"Colonnes ignorées ({len(ignored_present)}) : {', '.join(ignored_present)}")
    df = df.drop(columns=ignored_present)
    print(f"Colonnes retenues : {len(df.columns)}\n")

    # ── Import PostgreSQL ─────────────────────────────────────────────────────
    print("Import vers PostgreSQL...")
    inserted = 0
    skipped  = 0
    errors   = 0

    conn = None
    try:
        conn = psycopg2.connect(database_url)
        cur  = conn.cursor()

        for _, row in df.iterrows():
            row_dict = {}
            for col in df.columns:
                val = clean_value(row[col], col)
                if val is not None:
                    row_dict[col] = val

            try:
                ok = upsert_row(cur, row_dict)
                if ok:
                    inserted += 1
                else:
                    skipped += 1
            except psycopg2.Error as e:
                conn.rollback()
                print(f"  Avertissement ligne {inserted + skipped + errors + 1} : {e}")
                errors += 1
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
    print(f"\n{inserted} ligne(s) importée(s).")
    if skipped:
        print(f"{skipped} ligne(s) ignorée(s) (sans SIRET).")
    if errors:
        print(f"{errors} ligne(s) en erreur (colonne inconnue ou type incompatible).")


if __name__ == "__main__":
    main()
