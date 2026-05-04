const API_URL = "https://projet-crm-m0o3.onrender.com";

// Variable globale partagée entre toutes les pages déclaratives
let dataGlobal = [];

// Échappement HTML pour prévenir les injections XSS
function esc(val) {
    const div = document.createElement('div');
    div.textContent = val ?? '';
    return div.innerHTML;
}

// Formatage date ISO → YYYY-MM-DD
function formatDate(dateStr) {
    if (!dateStr) return "";
    return dateStr.substring(0, 10);
}

// Score de rentabilité (retourne la valeur numérique brute)
function getRentabiliteScore(val) {
    return parseFloat(val) || 0;
}

// Chargement des clients depuis l'API avec gestion d'erreur
async function fetchClients() {
    try {
        const res = await fetch(API_URL + "/clients");
        if (!res.ok) throw new Error("Erreur HTTP " + res.status);
        return await res.json();
    } catch (err) {
        console.error("Erreur fetchClients:", err);
        return [];
    }
}

// Attache applyFilters() sur tous les inputs correspondant au sélecteur CSS
function bindFilterInputs(selector) {
    document.querySelectorAll(selector).forEach(el => {
        el.addEventListener("input", applyFilters);
    });
}

// Mise à jour d'un champ texte/date/nombre dans PostgreSQL
async function updateField(siret, field, value, el) {
    if (el) el.style.background = "#fff3cd";
    try {
        const res = await fetch(API_URL + "/update-airtable", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ siret, field, value })
        });
        if (!res.ok) throw new Error();
        if (el) el.style.background = "#d4edda";
        setTimeout(() => { if (el) el.style.background = ""; }, 2000);
    } catch {
        if (el) el.style.background = "#f8d7da";
    }
}

// Mise à jour d'une case à cocher dans PostgreSQL
async function updateCheckbox(siret, field, value, el) {
    if (el) el.style.outline = "2px solid orange";
    try {
        const res = await fetch(API_URL + "/update-airtable", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ siret, field, value })
        });
        if (!res.ok) throw new Error();
        if (el) el.style.outline = "2px solid green";
        setTimeout(() => { if (el) el.style.outline = ""; }, 2000);
    } catch {
        if (el) el.style.outline = "2px solid red";
    }
}

// Mise à jour d'un select dans PostgreSQL
async function updateSelect(siret, field, value, el) {
    if (el) el.style.outline = "2px solid orange";
    try {
        const res = await fetch(API_URL + "/update-airtable", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ siret, field, value })
        });
        if (!res.ok) throw new Error();
        if (el) el.style.outline = "2px solid green";
        setTimeout(() => { if (el) el.style.outline = ""; }, 2000);
    } catch {
        if (el) el.style.outline = "2px solid red";
    }
}

// Export CSV — séparateur point-virgule, BOM UTF-8 pour compatibilité Excel
// columns (optionnel) : [{label, field}, ...] — si absent, exporte toutes les clés
function exportCSV(data, filename, columns) {
    if (!data || !data.length) {
        alert("Aucune donnée à exporter.");
        return;
    }

    let headers, rows;

    if (columns) {
        headers = columns.map(c => c.label);
        rows = data.map(row =>
            columns.map(c => '"' + String(row[c.field] ?? '').replace(/"/g, '""') + '"').join(';')
        );
    } else {
        const keys = [...new Set(data.flatMap(r => Object.keys(r)))].filter(k => k !== 'id');
        headers = keys;
        rows = data.map(row =>
            keys.map(k => '"' + String(row[k] ?? '').replace(/"/g, '""') + '"').join(';')
        );
    }

    const csv = '﻿' + [
        headers.map(h => '"' + h.replace(/"/g, '""') + '"').join(';'),
        ...rows
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'export.csv';
    a.click();
    URL.revokeObjectURL(url);
}
