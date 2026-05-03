import os
import sys
import urllib.request
import urllib.error
import json

BASE_ID  = "appcYhoQfSuz8ozil"
TABLE_ID = "tblm1aQ4OJ9W1hwm8"

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

# Recherche de la table par ID
table = next((t for t in data.get("tables", []) if t["id"] == TABLE_ID), None)
if not table:
    print(f"Table {TABLE_ID} introuvable dans la base {BASE_ID}.")
    print("Tables disponibles :")
    for t in data.get("tables", []):
        print(f"  {t['id']}  {t['name']}")
    sys.exit(1)

fields = table.get("fields", [])
print(f"Table : {table['name']}  ({TABLE_ID})")
print(f"{len(fields)} champ(s) trouvé(s)\n")

col = "{:<36} {:<20} {}"
print(col.format("ID", "Type", "Nom"))
print("-" * 80)
for f in fields:
    print(col.format(f.get("id", ""), f.get("type", ""), f.get("name", "")))
