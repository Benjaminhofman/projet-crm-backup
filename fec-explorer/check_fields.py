"""
Compare les champs présents dans Airtable avec le schéma attendu
(dérivé des clés produites par calculate_indicators + FIELD_MAPPING).

Usage :
    AIRTABLE_TOKEN=xxx python check_fields.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

from app.core.airtable_sync import BASE_ID, TABLE_ID, FIELD_MAPPING

# ── Schéma PostgreSQL attendu (toutes les clés produites par calculate_indicators) ──
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

# Noms Airtable attendus = valeurs de FIELD_MAPPING + champs non mappés mais attendus
EXPECTED_AIRTABLE = set(FIELD_MAPPING.values()) | {"siret", "prestation", "multitva"}


def fetch_airtable_fields() -> set:
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

    return {f["name"] for f in table.get("fields", [])}


def main():
    print(f"Récupération des champs Airtable (table {TABLE_ID})...\n")
    airtable_fields = fetch_airtable_fields()

    print(f"Champs Airtable trouvés     : {len(airtable_fields)}")
    print(f"Champs attendus (schéma)    : {len(EXPECTED_AIRTABLE)}")
    print(f"Clés Python (indicateurs)   : {len(SCHEMA_POSTGRES)}\n")

    # ── 1. Champs dans Airtable mais absents du schéma attendu ──
    extra = sorted(airtable_fields - EXPECTED_AIRTABLE)
    print(f"{'=' * 55}")
    print(f"Champs DANS Airtable mais ABSENTS du schéma ({len(extra)}) :")
    print(f"{'=' * 55}")
    if extra:
        for name in extra:
            print(f"  + {name}")
    else:
        print("  (aucun)")

    # ── 2. Champs attendus mais absents d'Airtable ──
    missing = sorted(EXPECTED_AIRTABLE - airtable_fields)
    print()
    print(f"{'=' * 55}")
    print(f"Champs ATTENDUS mais ABSENTS d'Airtable ({len(missing)}) :")
    print(f"{'=' * 55}")
    if missing:
        for name in missing:
            # Indique la clé Python correspondante si différente
            py_key = next((k for k, v in FIELD_MAPPING.items() if v == name), name)
            suffix = f"  (clé Python : {py_key})" if py_key != name else ""
            print(f"  - {name}{suffix}")
    else:
        print("  (aucun)")

    # ── 3. Clés Python sans mapping Airtable (non synchronisées) ──
    unmapped = sorted(SCHEMA_POSTGRES - set(FIELD_MAPPING.keys()) - {"siret", "prestation", "multitva"})
    if unmapped:
        print()
        print(f"{'=' * 55}")
        print(f"Clés Python SANS mapping Airtable ({len(unmapped)}) :")
        print(f"{'=' * 55}")
        for name in unmapped:
            print(f"  ? {name}")


if __name__ == "__main__":
    main()
