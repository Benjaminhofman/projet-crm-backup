import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_ID     = "appcYhoQfSuz8ozil"
TABLE_NAME  = "Base clients"
SIRET_FIELD = "SIRET"          # nom exact du champ SIRET dans Airtable

# Correspondance clé Python → nom du champ Airtable
FIELD_MAPPING = {
    # Champs avec noms différents dans Airtable
    "ca":                    "CA R",
    "assurance":             "assurance R",
    "deplacement":           "deplacement R",
    "loyer":                 "loyer R",
    "cfe":                   "CFE R",
    "publicite":             "publicite R",
    "honoraires":            "honoraires R",
    "banque":                "banque R",
    "emprunt":               "emprunt R",
    "masse_salariale":       "m_salariale R",
    "produits":              "produit R",
    "charges":               "charge R",
    "tresorerie":            "tresorerie R",
    "resultat":              "resultat R",
    # Champs dont le nom Airtable = nom du code
    "marge_brute":           "marge_brute",
    "valeur_ajoutee":        "valeur_ajoutee",
    "ebe":                   "ebe",
    "rex":                   "rex",
    "caf":                   "caf",
    "bfr":                   "bfr",
    "frng":                  "frng",
    "tresorerie_nette":      "tresorerie_nette",
    "productivite":          "productivite",
    "capacite_remboursement":"capacite_remboursement",
    "liquidite_generale":    "liquidite_generale",
    "delai_client":          "delai_client",
    "delai_fournisseur":     "delai_fournisseur",
    "ratio_endettement":     "ratio_endettement",
    "resultat_financier":    "resultat_financier",
    "resultat_exceptionnel": "resultat_exceptionnel",
}


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


def update_record(record_id: str, indicateur: dict) -> dict:
    """
    Envoie un PATCH Airtable pour mettre à jour un enregistrement.

    Construit le payload en appliquant FIELD_MAPPING sur l'indicateur.
    Les clés absentes du mapping ou dont la valeur est None sont ignorées.
    Respecte la limite 5 req/sec via time.sleep(0.2).

    Retourne la réponse JSON d'Airtable.
    """
    fields = {
        airtable_name: indicateur[code_key]
        for code_key, airtable_name in FIELD_MAPPING.items()
        if code_key in indicateur and indicateur[code_key] is not None
    }

    if not fields:
        logging.warning("update_record %s : aucun champ à mettre à jour.", record_id)
        return {}

    token   = _get_token()
    url     = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE_NAME)}/{record_id}"
    payload = json.dumps({"fields": fields}).encode()

    req = urllib.request.Request(
        url,
        data    = payload,
        method  = "PATCH",
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
        logging.info("update_record %s : %d champ(s) mis à jour.", record_id, len(fields))
        return result
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Airtable PATCH {record_id} — HTTP {e.code} : {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Airtable PATCH {record_id} — réseau : {e.reason}") from e
    finally:
        time.sleep(0.2)  # respecte la limite 5 req/sec


def sync_all(indicateurs: list) -> dict:
    """
    Synchronise une liste d'indicateurs (issue de calculate_indicators)
    vers Airtable en mettant à jour chaque enregistrement trouvé par SIRET.

    Retourne :
      {
        "updated":   int,                # nombre de mises à jour réussies
        "not_found": [siret, ...],       # SIRET présents dans le FEC mais absents d'Airtable
        "errors":    int,                # nombre d'erreurs lors des PATCH
      }
    """
    records   = get_all_records()
    updated   = 0
    not_found = []
    errors    = 0

    for ind in indicateurs:
        siret = str(ind.get("siret", "")).strip()

        if not siret:
            logging.warning("sync_all : indicateur sans SIRET — ignoré.")
            continue

        record_id = records.get(siret)

        if not record_id:
            logging.warning("sync_all : SIRET %s absent d'Airtable.", siret)
            not_found.append(siret)
            continue

        try:
            update_record(record_id, ind)
            updated += 1
        except RuntimeError as e:
            logging.error("sync_all : échec PATCH SIRET %s — %s", siret, e)
            errors += 1

    logging.info("sync_all terminé : %d mis à jour, %d introuvables, %d erreurs.", updated, len(not_found), errors)
    return {"updated": updated, "not_found": not_found, "errors": errors}
