import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.core.fec_parser    import parse_multiple_fec
from app.core.indicators    import calculate_indicators
from app.core.airtable_sync import sync_all

dossier = os.path.join(os.path.dirname(__file__), "exemples-fec")

print(f"Parsing : {os.path.abspath(dossier)}")
rows        = parse_multiple_fec(dossier)
indicateurs = calculate_indicators(rows)
print(f"{len(indicateurs)} indicateur(s) calculé(s)\n")

print("Synchronisation Airtable...")
res = sync_all(indicateurs)

print(f"\n{res['updated']} client(s) mis à jour, {len(res['not_found'])} non trouvé(s), {res['errors']} erreur(s)")

if res["not_found"]:
    print("\nSIRET non trouvés dans Airtable :")
    for siret in res["not_found"]:
        print(f"  - {siret}")
