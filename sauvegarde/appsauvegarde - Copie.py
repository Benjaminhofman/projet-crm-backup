from flask import Flask, request, jsonify
from flask_cors import CORS
from airtable import get_records, get_record, create_record, update_record

app = Flask(__name__)
CORS(app)


# 🔹 Nettoyage des données
def clean_records(records):
    return [
        {
            "id": r.get("id"),
            **r.get("fields", {})
        }
        for r in records if "id" in r
    ]


# =========================================
# 🔹 HOME
# =========================================
@app.route("/")
def home():
    return {"message": "API Airtable OK"}


# =========================================
# 🔹 1. LISTE CLIENTS
# =========================================
@app.route("/clients", methods=["GET"])
def clients():
    view = request.args.get("view")

    records = get_records(view=view)

    # 🔥 gestion erreur Airtable
    if isinstance(records, dict) and "error" in records:
        return jsonify(records), 400

    return jsonify(clean_records(records))


# =========================================
# 🔹 2. DETAIL CLIENT (CORRIGÉ)
# =========================================
@app.route("/client/<record_id>", methods=["GET"])
def client_detail(record_id):
    record = get_record(record_id)

    print("DEBUG RECORD:", record)  # utile si bug

    # 🔥 sécurité
    if "id" not in record:
        return jsonify({
            "error": "Record not found",
            "details": record
        }), 404

    return jsonify({
        "id": record["id"],
        **record.get("fields", {})
    })


# =========================================
# 🔹 3. AJOUT CLIENT
# =========================================
@app.route("/client", methods=["POST"])
def add_client():
    data = request.json

    result = create_record(data)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# =========================================
# 🔹 4. MODIFIER CLIENT
# =========================================
@app.route("/client/<record_id>", methods=["PATCH"])
def update_client(record_id):
    data = request.json

    result = update_record(record_id, data)

    if "error" in result:
        return jsonify(result), 400

    return jsonify(result)


# =========================================
# 🔹 5. RECHERCHE AVANCEE
# =========================================
@app.route("/search", methods=["GET"])
def search():
    nom = request.args.get("nom")
    activite = request.args.get("activite")
    statut = request.args.get("statut")

    filters = []

    if nom:
        filters.append(f"SEARCH('{nom}', {{Nom}})")
    if activite:
        filters.append(f"SEARCH('{activite}', {{activite R}})")
    if statut:
        filters.append(f"{{Statut}} = '{statut}'")

    formula = f"AND({','.join(filters)})" if filters else None

    records = get_records(formula=formula)

    if isinstance(records, dict) and "error" in records:
        return jsonify(records), 400

    return jsonify(clean_records(records))


# =========================================
# 🔹 6. FILTRE DYNAMIQUE
# =========================================
@app.route("/filter", methods=["POST"])
def dynamic_filter():
    filters = request.json  # ex: {"Nom": "Dupont"}

    formula_parts = []

    for field, value in filters.items():
        formula_parts.append(f"SEARCH('{value}', {{{field}}})")

    formula = f"AND({','.join(formula_parts)})" if formula_parts else None

    records = get_records(formula=formula)

    if isinstance(records, dict) and "error" in records:
        return jsonify(records), 400

    return jsonify(clean_records(records))


# =========================================
# 🔹 RUN
# =========================================
if __name__ == "__main__":
    app.run(debug=True)