// Moteur partagé pour toutes les pages de suivi déclaratif.
// Chaque page appelle initDeclaratifPage(config) avec sa configuration unique.

let _pageConfig = null;
let _currentData = [];

function initDeclaratifPage(config) {
    _pageConfig = config;

    document.title = config.titre;
    document.getElementById('page-title').textContent = config.emoji + ' ' + config.titre;

    // Ajout dynamique des en-têtes de colonnes spécifiques à la page
    const theadRow = document.getElementById('table-head');
    config.columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col.header;
        theadRow.appendChild(th);
    });

    load();
}

function display(data) {
    _currentData = data;

    const table = document.getElementById("table");
    document.getElementById("counter").textContent = "Nombre de dossiers : " + data.length;

    if (!data.length) {
        table.innerHTML = `<tr class="loading-row"><td colspan="20">Aucun résultat</td></tr>`;
        return;
    }

    // DocumentFragment pour un rendu DOM en une seule opération
    const frag = document.createDocumentFragment();

    data.forEach(c => {
        const tr = document.createElement('tr');

        // Colonnes fixes communes à toutes les pages
        tr.innerHTML = `
            <td>${esc(c["code client"])}</td>
            <td class="name">${esc(c["nom client"])}</td>
            <td>${esc(c["assistant"])}</td>
            <td>${esc(c["collaborateur"])}</td>
            <td>${esc(c["année"])}</td>
            <td>${esc(c["date de cloture"])}</td>
        `;

        // Colonnes dynamiques définies par la config de la page
        _pageConfig.columns.forEach(col => {
            const td = document.createElement('td');

            if (col.type === 'checkbox') {
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = !!c[col.field];
                cb.onchange = function () { updateCheckbox(c.id, col.field, this.checked, this); };
                td.appendChild(cb);

            } else if (col.type === 'select') {
                const sel = document.createElement('select');
                sel.innerHTML = '<option value="">--</option>' +
                    col.options.map(o =>
                        `<option value="${o.value}" ${c[col.field] === o.value ? 'selected' : ''}>${o.label}</option>`
                    ).join('');
                sel.onchange = function () { updateSelect(c.id, col.field, this.value, this); };
                td.appendChild(sel);

            } else if (col.type === 'date') {
                const inp = document.createElement('input');
                inp.type = 'date';
                inp.value = formatDate(c[col.field]);
                inp.onchange = function () { updateField(c.id, col.field, this.value, this); };
                td.appendChild(inp);

            } else {
                // Type texte par défaut
                const inp = document.createElement('input');
                inp.type = 'text';
                inp.value = c[col.field] || '';
                inp.onchange = function () { updateField(c.id, col.field, this.value, this); };
                td.appendChild(inp);
            }

            tr.appendChild(td);
        });

        frag.appendChild(tr);
    });

    table.innerHTML = '';
    table.appendChild(frag);
}

function applyFilters() {
    // Support des deux conventions d'IDs de filtres
    const get = id => (document.getElementById(id) || { value: "" }).value.toLowerCase();
    const assistant = get("filter-assistant") || get("f-assistant");
    const collab    = get("filter-collab")    || get("f-collab");
    const annee     = get("filter-annee")     || get("f-annee");
    const cloture   = get("filter-cloture")   || get("f-cloture");

    const filtered = dataGlobal.filter(c => {
        // Filtre principal personnalisé (ex : dividendes > 0)
        if (_pageConfig.requireFn && !_pageConfig.requireFn(c)) return false;
        if (assistant && !(c["assistant"]       || "").toLowerCase().includes(assistant)) return false;
        if (collab    && !(c["collaborateur"]   || "").toLowerCase().includes(collab))    return false;
        if (annee     && !(String(c["année"]    || "")).includes(annee))                  return false;
        if (cloture   && !(c["date de cloture"] || "").toLowerCase().includes(cloture))   return false;
        return true;
    });

    display(filtered);
}

async function load() {
    document.getElementById("table").innerHTML =
        `<tr class="loading-row"><td colspan="20">⏳ Chargement en cours…</td></tr>`;

    const data = await fetchClients();

    dataGlobal = _pageConfig.filterField
        ? data.filter(c => c[_pageConfig.filterField] === true)
        : data;

    display(dataGlobal);
    bindFilterInputs(".filters-top input");
}

// Export CSV du tableau affiché (données filtrées)
function exportCurrentCSV() {
    const cols = [
        { label: "Code",          field: "code client" },
        { label: "Nom",           field: "nom client" },
        { label: "Assistant",     field: "assistant" },
        { label: "Collaborateur", field: "collaborateur" },
        { label: "Année",         field: "année" },
        { label: "Clôture",       field: "date de cloture" },
        ..._pageConfig.columns.map(c => ({ label: c.header, field: c.field }))
    ];

    const safeName = _pageConfig.titre.toLowerCase().replace(/\s+/g, '_') + '.csv';
    exportCSV(_currentData, safeName, cols);
}
