import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

BASE_ID    = "appcYhoQfSuz8ozil"
TABLE_NAME = "Base clients"
SIRET_FIELD = "SIRET"          # nom exact du champ SIRET dans Airtable


def _get_token() -> str:
    token = os.environ.get("AIRTABLE_TOKEN", "")
    if not token:
        raise EnvironmentError("Variable d'environnement AIRTABLE_TOKEN non définie.")
    return token


def _request(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Airtable HTTP {e.code} : {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Airtable réseau : {e.reason}") from e


def get_all_records() -> dict:
    """
    Récupère tous les enregistrements de la table Airtable 'Base clients'
    et retourne un dict {siret: record_id}.

    Gère la pagination automatiquement via le paramètre offset.
    Les enregistrements sans champ SIRET valide sont ignorés.
    """
    token     = _get_token()
    table_url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE_NAME)}"
    result    = {}
    offset    = None

    while True:
        params = {"fields[]": SIRET_FIELD, "pageSize": "100"}
        if offset:
            params["offset"] = offset

        url  = f"{table_url}?{urllib.parse.urlencode(params)}"
        data = _request(url, token)

        for record in data.get("records", []):
            siret = record.get("fields", {}).get(SIRET_FIELD, "")
            if siret:
                result[str(siret).strip()] = record["id"]
            else:
                logging.debug("Enregistrement %s sans champ %s — ignoré.", record["id"], SIRET_FIELD)

        offset = data.get("offset")
        if not offset:
            break

    return result
