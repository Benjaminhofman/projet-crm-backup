const API_URL = "https://projet-crm-m0o3.onrender.com";

let dataGlobal = [];

async function fetchClients() {
    const res = await fetch(API_URL + "/clients");
    return res.json();
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
