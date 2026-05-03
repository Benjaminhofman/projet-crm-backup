"""
check_fields.py
1. Compare champs Airtable vs schéma indicateurs FEC (diff bidirectionnel)
2. Génère schema.sql — CREATE TABLE clients — avec TOUS les champs Airtable
   + indicateurs FEC calculés manquants

Usage :
    AIRTABLE_TOKEN=xxx python check_fields.py
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

from app.core.airtable_sync import BASE_ID, TABLE_ID, FIELD_MAPPING

# ── Schéma FEC attendu (toutes les clés de calculate_indicators) ───────────────
SCHEMA_POSTGRES = {
    "siret",
    "ca", "charges", "produits", "tresorerie", "emprunt", "masse_salariale",
    "assurance", "deplacement", "loyer", "cfe", "tns", "publicite",
    "honoraires", "banque",
    "compte_791", "produits_financiers", "produits_exceptionnels",
    "placements", "capital", "reserves", "report_a_nouveau",
    "compte_exploitant", "compte_courant_associe",
    "charges_financieres", "charges_exceptionnelles",
    "achats_non_stockes", "sous_traitance", "entretien_reparation",
    "personnel_exterieur", "frais_telecom", "impots_taxes",
    "dotations_amortissements", "impot_societes",
    "materiel_transport", "fond_commerce", "constructions",
    "materiel_informatique", "mobilier",
    "stocks", "clients", "fournisseurs",
    "achats_marchandises", "variation_stocks", "achats_matieres",
    "prestation", "multitva",
    "resultat", "marge_brute", "valeur_ajoutee", "ebe", "rex",
    "resultat_financier", "resultat_exceptionnel", "caf",
    "productivite", "capacite_remboursement", "liquidite_generale",
    "delai_client", "ratio_endettement",
}

# Noms Airtable attendus
EXPECTED_AIRTABLE = set(FIELD_MAPPING.values()) | {"siret", "prestation", "multitva"}

# Champs FEC dont le type SQL est TEXT (les autres sont NUMERIC)
FEC_TEXT_FIELDS = {"siret", "prestation", "multitva"}

# ── Mapping type Airtable → type SQL ──────────────────────────────────────────
_AIRTABLE_SQL = {
    "number":     "NUMERIC",
    "currency":   "NUMERIC",
    "percent":    "NUMERIC",
    "rating":     "NUMERIC",
    "duration":   "NUMERIC",
    "autoNumber": "SERIAL",
    "checkbox":   "BOOLEAN",
    "date":       "DATE",
    "dateTime":   "TIMESTAMP",
}

# Heuristiques sur le nom (utilisées si le type Airtable n'est pas dans _AIRTABLE_SQL)
_RE_DATE = re.compile(r"date", re.I)
_RE_BOOL = re.compile(
    r"(liasse|juridique|tvs|ca12|déclaré|déposé|signé|envoyé|validé|actif|clôturé)",
    re.I,
)
_RE_NUM = re.compile(
    r"(honoraire|temps\s*pass|dividende|montant|solde|tarif|taux|budget|"
    r"provision|cotis|retraite|prévoyance|nb\s|nombre|duree|durée|"
    r"mai\s*is|is\s+\d|\bIS\b| r$)",
    re.I,
)


def _sql_type(name: str, airtable_type: str) -> str:
    """Détermine le type SQL à partir du type Airtable puis du nom du champ."""
    if airtable_type in _AIRTABLE_SQL:
        return _AIRTABLE_SQL[airtable_type]
    if _RE_DATE.search(name):
        return "DATE"
    if _RE_BOOL.search(name):
        return "BOOLEAN"
    if _RE_NUM.search(name):
        return "NUMERIC"
    return "TEXT"


def _col(name: str) -> str:
    """Convertit un nom Airtable en identifiant SQL snake_case sans espaces."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower().strip())
    return s.strip("_")


# ── Fetch Airtable ─────────────────────────────────────────────────────────────

def fetch_airtable_fields() -> list:
    """Retourne la liste des objets champ [{id, name, type, ...}] depuis l'API Airtable."""
    token = os.environ.get("AIRTABLE_TOKEN")
    if not token:
        print("Erreur : variable d'environnement AIRTABLE_TOKEN non définie.")
        sys.exit(1)

    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Erreur HTTP {e.code} : {e.reason}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Erreur réseau : {e.reason}")
        sys.exit(1)

    table = next((t for t in data.get("tables", []) if t["id"] == TABLE_ID), None)
    if not table:
        print(f"Table {TABLE_ID} introuvable.")
        sys.exit(1)

    return table.get("fields", [])


# ── Génération SQL ─────────────────────────────────────────────────────────────

def generate_sql(airtable_fields: list, fec_extra: list) -> str:
    """
    Construit le DDL CREATE TABLE clients.
    airtable_fields : [{name, type, ...}]  — tous les champs Airtable
    fec_extra       : [(col_name, sql_type)] — indicateurs FEC sans équivalent Airtable
    """
    lines = []
    seen  = set()

    def add_col(col: str, sql_t: str, comment: str = ""):
        if col in seen:
            return
        seen.add(col)
        suffix = f"  -- {comment}" if comment else ""
        lines.append(f"    {col:<46}{sql_t}{suffix}")

    # siret en premier — clé primaire
    add_col("siret", "TEXT  PRIMARY KEY NOT NULL", "identifiant SIRET")

    # Tous les champs Airtable (triés par nom)
    for f in sorted(airtable_fields, key=lambda x: x["name"].lower()):
        col   = _col(f["name"])
        sql_t = _sql_type(f["name"], f.get("type", ""))
        if col == "siret":
            continue
        add_col(col, sql_t, f["name"])

    # Indicateurs FEC calculés absents d'Airtable
    if fec_extra:
        lines.append("")
        lines.append("    -- Indicateurs FEC calculés (absents d'Airtable)")
        for col, sql_t in sorted(fec_extra):
            add_col(col, sql_t)

    body = ",\n".join(lines)
    nb   = len(seen)
    return (
        "-- Généré automatiquement par check_fields.py\n"
        f"-- {nb} colonnes : champs Airtable + indicateurs FEC calculés\n\n"
        "CREATE TABLE IF NOT EXISTS clients (\n"
        f"{body}\n"
        ");\n"
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Récupération des champs Airtable ({TABLE_ID})...\n")
    fields = fetch_airtable_fields()
    airtable_names = {f["name"] for f in fields}

    # ── 1. Diff Airtable ↔ schéma attendu ────────────────────────────────────
    extra   = sorted(airtable_names - EXPECTED_AIRTABLE)
    missing = sorted(EXPECTED_AIRTABLE - airtable_names)

    print(f"Champs Airtable trouvés  : {len(airtable_names)}")
    print(f"Champs attendus (schéma) : {len(EXPECTED_AIRTABLE)}\n")

    print("=" * 58)
    print(f"Dans Airtable mais ABSENTS du schéma ({len(extra)}) :")
    print("=" * 58)
    for n in (extra or ["(aucun)"]):
        print(f"  + {n}")

    print()
    print("=" * 58)
    print(f"Attendus mais ABSENTS d'Airtable ({len(missing)}) :")
    print("=" * 58)
    for n in (missing or ["(aucun)"]):
        py_key = next((k for k, v in FIELD_MAPPING.items() if v == n), n)
        suffix = f"  (clé Python : {py_key})" if py_key != n else ""
        print(f"  - {n}{suffix}")

    # ── 2. Champs FEC non couverts par Airtable ───────────────────────────────
    # Un champ Python est couvert si : son nom direct OU sa valeur FIELD_MAPPING
    # correspond à un champ Airtable existant.
    covered = set(airtable_names)  # noms directs
    reverse_map = {v: k for k, v in FIELD_MAPPING.items()}
    covered.update(reverse_map[n] for n in airtable_names if n in reverse_map)

    fec_extra = [
        (_col(key), "TEXT" if key in FEC_TEXT_FIELDS else "NUMERIC")
        for key in SCHEMA_POSTGRES
        if key not in covered
    ]

    if fec_extra:
        print()
        print("=" * 58)
        print(f"Indicateurs FEC sans équivalent Airtable ({len(fec_extra)}) :")
        print("=" * 58)
        for col, sql_t in sorted(fec_extra):
            print(f"  ? {col}  ({sql_t})")

    # ── 3. Génération schema.sql ─────────────────────────────────────────────
    sql      = generate_sql(fields, fec_extra)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(sql)

    total = len(airtable_names) + len(fec_extra)
    print(f"\nschema.sql sauvegardé : {total} colonnes")
    print(f"  {out_path}")


if __name__ == "__main__":
    main()
