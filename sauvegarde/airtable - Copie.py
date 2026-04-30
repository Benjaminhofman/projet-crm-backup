import requests
import os

# 🔐 Variables d'environnement (sécurisé)
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")

BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_TOKEN}",
    "Content-Type": "application/json"
}


# 🔹 Récupération avec pagination
def get_records(view=None, formula=None, max_records=1000):
    all_records = []
    offset = None

    while True:
        params = {"pageSize": 100}

        if view:
            params["view"] = view

        if formula:
            params["filterByFormula"] = formula

        if offset:
            params["offset"] = offset

        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        data = response.json()

        # 🔥 sécurité
        if "error" in data:
            return data

        records = data.get("records", [])
        all_records.extend(records)

        if "offset" in data and len(all_records) < max_records:
            offset = data["offset"]
        else:
            break

    return all_records


# 🔹 Récupérer 1 record
def get_record(record_id):
    url = f"{BASE_URL}/{record_id}"
    response = requests.get(url, headers=HEADERS)
    return response.json()


# 🔹 Créer
def create_record(data):
    response = requests.post(
        BASE_URL,
        headers=HEADERS,
        json={"fields": data}
    )
    return response.json()


# 🔹 Modifier
def update_record(record_id, data):
    url = f"{BASE_URL}/{record_id}"
    response = requests.patch(
        url,
        headers=HEADERS,
        json={"fields": data}
    )
    return response.json()