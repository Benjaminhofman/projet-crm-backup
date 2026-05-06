#!/usr/bin/env python3
"""
sync_html.py — Synchronise les fichiers HTML/JS de la racine du projet
vers fec-explorer/static/.

Transformations appliquées :
  • Remplace data["champ avec espaces"] → data.champ_snake_case
  • Remplace c.id / c["id"] / updateXxx(c.id, ...) → siret
  • Remplace client.html?id= → client.html?siret=
  • Inline utils.js dans les HTML avec API_URL="/api"
  • Valide les noms de colonnes contre PostgreSQL si DATABASE_URL est définie
"""

import os
import re
import unicodedata
import psycopg2

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR   = os.path.dirname(_THIS_DIR)
STATIC_DIR = os.path.join(_THIS_DIR, "static")

# Jamais copiés dans static/ (utils.js est inliné ; index.html géré manuellement)
SKIP_FILES = {"utils.js", "index.html"}

# Fichiers exclus du sync racine → static/ (gérés manuellement dans static/)
EXCLUDED = ["index.html"]

# Fichiers de sauvegarde à ignorer
_RE_BACKUP = re.compile(r"sauv|SAUVE", re.IGNORECASE)

# Champs jamais remplacés (conservés en notation bracket pour usage intentionnel)
PROTECTED = {"anniversaire", "ancienneté", "rentabilite"}


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Même logique que import_csv.py : accents, minuscules, espaces→underscore."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name


# ── PostgreSQL ────────────────────────────────────────────────────────────────

def get_pg_columns() -> set:
    """Récupère les colonnes de la table clients depuis PostgreSQL."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("[WARN] DATABASE_URL non definie -- mode heuristique (toutes les normalisations appliquees).")
        return set()
    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'clients' ORDER BY ordinal_position"
            )
            cols = {row[0] for row in cur.fetchall()}
        conn.close()
        print(f"[OK] {len(cols)} colonnes PostgreSQL recuperees.")
        return cols
    except Exception as e:
        print(f"[WARN] Connexion PostgreSQL impossible : {e}\n    -> mode heuristique active.")
        return set()


# ── Remplacement des noms de champs ──────────────────────────────────────────

def _make_replacer(pg_cols: set):
    """Retourne une fonction de remplacement pour re.sub."""
    def _sub(m):
        obj = m.group(1)          # data, c, a, row…
        raw = m.group(2)          # contenu brut entre guillemets
        if raw in PROTECTED:
            return m.group(0)
        norm = normalize(raw)
        # En mode PG : on ne remplace que si la colonne existe
        if pg_cols and norm not in pg_cols:
            return m.group(0)
        return f"{obj}.{norm}"
    return _sub


def replace_field_access(content: str, pg_cols: set) -> str:
    """obj["field"] → obj.snake_case   (guillemets doubles et simples)."""
    sub = _make_replacer(pg_cols)
    content = re.sub(r'\b(data|c|a|row)\["([^"]+)"\]', sub, content)
    content = re.sub(r"\b(data|c|a|row)\['([^']+)'\]", sub, content)
    return content


def replace_field_config(content: str, pg_cols: set) -> str:
    """
    field: "Champ avec espaces"  →  field: "champ_snake_case"
    (dans filtersConfig, columns, exportCSV, etc.)
    """
    def _sub(m):
        raw = m.group(1)
        if raw in PROTECTED:
            return m.group(0)
        norm = normalize(raw)
        if pg_cols and norm not in pg_cols:
            return m.group(0)
        return f'field: "{norm}"'

    return re.sub(r'field:\s*"([^"]+)"', _sub, content)


def replace_id_refs(content: str) -> str:
    """Remplace toutes les références à .id par .siret."""
    # Accès objet
    content = re.sub(r'\b(c|data|a|row)\.id\b', r'\1.siret', content)
    content = re.sub(r'\b(c|data|a|row)\["id"\]', r'\1.siret', content)
    content = re.sub(r"\b(c|data|a|row)\['id'\]", r'\1.siret', content)

    # Paramètre URL
    content = content.replace('params.get("id")', 'params.get("siret")')
    content = content.replace("params.get('id')", "params.get('siret')")

    # Lien fiche client
    content = content.replace('client.html?id=', 'client.html?siret=')

    # Appels aux fonctions update (premier argument = identifiant)
    # updateField(c.id, ...) → déjà géré par le remplacement c.id ci-dessus
    return content


# ── utils.js inline ──────────────────────────────────────────────────────────

def get_utils_inline() -> str:
    """Lit utils.js, remplace API_URL par '/api', retourne le contenu."""
    utils_path = os.path.join(ROOT_DIR, "utils.js")
    if not os.path.exists(utils_path):
        return 'const API_URL = "/api";'
    content = open(utils_path, encoding="utf-8").read()
    content = re.sub(
        r'const API_URL\s*=\s*"[^"]*"',
        'const API_URL = "/api"',
        content
    )
    return content.strip()


# ── Traitement par type de fichier ────────────────────────────────────────────

def process_html(content: str, pg_cols: set, utils_inline: str) -> str:
    content = replace_field_access(content, pg_cols)
    content = replace_field_config(content, pg_cols)
    content = replace_id_refs(content)
    content = content.replace(
        '<script src="utils.js"></script>',
        f'<script>\n{utils_inline}\n</script>'
    )
    return content


def process_js(content: str, pg_cols: set) -> str:
    content = replace_field_access(content, pg_cols)
    content = replace_field_config(content, pg_cols)
    content = replace_id_refs(content)
    content = re.sub(
        r'const API_URL\s*=\s*"[^"]*"',
        'const API_URL = "/api"',
        content
    )
    return content


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pg_cols    = get_pg_columns()
    utils_inline = get_utils_inline()

    files = sorted(
        f for f in os.listdir(ROOT_DIR)
        if f.endswith((".html", ".js"))
        and f not in SKIP_FILES
        and not _RE_BACKUP.search(f)
        and os.path.isfile(os.path.join(ROOT_DIR, f))
    )

    print(f"\n[INFO] {len(files)} fichiers a synchroniser :")
    for f in files:
        print(f"   {f}")

    os.makedirs(STATIC_DIR, exist_ok=True)

    ok = errors = 0
    for filename in files:
        src = os.path.join(ROOT_DIR, filename)
        dst = os.path.join(STATIC_DIR, filename)
        try:
            content = open(src, encoding="utf-8").read()
            if filename.endswith(".html"):
                processed = process_html(content, pg_cols, utils_inline)
            else:
                processed = process_js(content, pg_cols)
            with open(dst, "w", encoding="utf-8", newline="\n") as f:
                f.write(processed)
            print(f"  OK  {filename}")
            ok += 1
        except Exception as e:
            print(f"  ERR {filename} : {e}")
            errors += 1

    print(f"\n[DONE] {ok} fichier(s) copies, {errors} erreur(s).")
    print(f"[DIR]  {STATIC_DIR}")


if __name__ == "__main__":
    main()
