from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from airtable import get_records, get_record, create_record, update_record
import requests
import os

app = Flask(__name__, static_folder=".")
CORS(app)

# =========================================
# 🔹 CONFIG
# =========================================
AIRTABLE_API_KEY = os.getenv("AIRTABLE_TOKEN")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")


# =========================================
# 🔹 UTIL
# =========================================
def clean_records(records):
    return [
        {
            "id": r.get("id"),
            **r.get("fields", {})
        }
        for r in records if "id" in r
    ]


# =========================================
# 🔹 API
# =========================================
@app.route("/api")
def api_home():
    return {"message": "API Airtable OK"}


@app.route("/clients", methods=["GET"])
def clients():
    records = get_records()

    if isinstance(records, dict) and "error" in records:
        return jsonify(records), 400

    return jsonify(clean_records(records))


@app.route("/client/<record_id>", methods=["GET"])
def client_detail(record_id):
    record = get_record(record_id)

    if "id" not in record:
        return jsonify({"error": "Record not found"}), 404

    return jsonify({
        "id": record["id"],
        **record.get("fields", {})
    })


@app.route("/client", methods=["POST"])
def add_client():
    data = request.json
    result = create_record(data)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


@app.route("/client/<record_id>", methods=["PATCH"])
def update_client(record_id):
    data = request.json
    result = update_record(record_id, data)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# =========================================
# 🔥 UPDATE AIRTABLE (VERSION AUTOMATIQUE)
# =========================================
@app.route("/update-airtable", methods=["POST"])
def update_airtable():

    data = request.json

    record_id = data.get("id")
    field = data.get("field")
    value = data.get("value")

    print("\n===== UPDATE DEMANDÉ =====")
    print("ID :", record_id)
    print("FIELD :", field)
    print("VALUE BRUT :", value)

    # 🔥 conversion automatique intelligente
# 🔥 gestion intelligente des types
    if value == "" or value is None:
        value = None

    elif isinstance(value, bool):
        # 🔥 checkbox → on garde tel quel
        print("BOOLEAN DETECTÉ :", value)

    else:
        try:
            value = float(value)
            print("FLOAT DETECTÉ :", value)
        except:
            print("TEXTE CONSERVÉ :", value)

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}/{record_id}"

    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "fields": {
            field: value
        }
    }

    print("PAYLOAD :", payload)

    try:
        response = requests.patch(url, json=payload, headers=headers)

        print("STATUS CODE :", response.status_code)
        print("RESPONSE JSON :", response.json())

        return jsonify({
            "status": "ok",
            "airtable_response": response.json()
        })

    except Exception as e:
        print("ERREUR :", str(e))
        return jsonify({
            "status": "error",
            "message": str(e)
        })


# =========================================
# 🔹 SERVIR LES PAGES HTML
# =========================================
@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")


@app.route("/index.html")
def index_html():
    return send_from_directory(".", "index.html")


@app.route("/declaratif.html")
def declaratif_html():
    return send_from_directory(".", "declaratif.html")


@app.route("/ca12.html")
def ca12_html():
    return send_from_directory(".", "ca12.html")


@app.route("/tvs.html")
def tvs_html():
    return send_from_directory(".", "tvs.html")


@app.route("/cvae.html")
def cvae_html():
    return send_from_directory(".", "cvae.html")


@app.route("/ir.html")
def ir_html():
    return send_from_directory(".", "ir.html")


@app.route("/is.html")
def is_html():
    return send_from_directory(".", "is.html")

@app.route("/liasse.html")
def liasse_html():
    return send_from_directory(".", "liasse.html")

@app.route("/cfe.html")
def cfe_html():
    return send_from_directory(".", "cfe.html")

@app.route("/juridique.html")
def juridique_html():
    return send_from_directory(".", "juridique.html")

@app.route("/situation.html")
def situation_html():
    return send_from_directory(".", "situation.html")

@app.route("/tbb.html")
def tbb_html():
    return send_from_directory(".", "tbb.html")

@app.route("/missions.html")
def missions_html():
    return send_from_directory(".", "missions.html")

@app.route("/dividendes.html")
def dividendes_html():
    return send_from_directory(".", "dividendes.html")

@app.route("/opportunites.html")
def opportunites_html():
    return send_from_directory(".", "opportunites.html")

@app.route("/commercial.html")
def commercial_html():
    return send_from_directory(".", "commercial.html")
    
# =========================================
# 🔥 ROUTE GENERIQUE (TOUJOURS EN DERNIER)
# =========================================
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(".", filename)


# =========================================
# 🔹 RUN
# =========================================
if __name__ == "__main__":
    app.run(debug=True)