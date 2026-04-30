const API_URL = "https://projet-crm-m0o3.onrender.com";

let dataGlobal = [];

async function fetchClients() {
    const res = await fetch(API_URL + "/clients");
    return res.json();
}

function esc(str) {
    if (str == null) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function bindFilterInputs(selector, event = "input") {
    document.querySelectorAll(selector).forEach(el =>
        el.addEventListener(event, applyFilters)
    );
}

function formatDate(dateStr) {
    if (!dateStr) return "";
    return dateStr.substring(0, 10);
}
async function updateAirtable(data) {

    const url = "https://api.airtable.com/v0/TON_BASE_ID/TON_TABLE";

    await fetch(url, {
        method: "POST",
        headers: {
            "Authorization": "Bearer TON_API_KEY",
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            fields: {
                "Code": data.code,
                "Nom": data.nom,
                "Assistant": data.assistant,
                "Collaborateur": data.collaborateur,
                "Année": data.annee,
                "Cloture": data.cloture,
                "Temps passé": data.temps_passe,
                "Honoraires cpta": data.honoraires,
                "Resultat R": data.resultat,
                "Ancienneté": data.anciennete
            }
        })
    });
}
async function updateField(id, field, value, el) {
    if (el) el.style.background = "#fff3cd";
    try {
        await fetch(API_URL + "/update-airtable", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, field, value })
        });
        if (el) el.style.background = "#d4edda";
    } catch (error) {
        if (el) el.style.background = "#f8d7da";
    }
}
