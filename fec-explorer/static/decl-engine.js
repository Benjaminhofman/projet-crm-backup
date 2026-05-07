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

        // Colonnes fixes — le nom est un lien vers la fiche client
        tr.innerHTML = `
            <td>${esc(c.code_client)}</td>
            <td class="name"><a href="client.html?siret=${c.siret}" class="client-link">${esc(c.nom_client)}</a></td>
            <td>${esc(c.assistant)}</td>
            <td>${esc(c.collaborateur)}</td>
            <td>${esc(c.annee)}</td>
            <td>${esc(c.date_de_cloture)}</td>
        `;

        // Colonnes dynamiques définies par la config de la page
        _pageConfig.columns.forEach(col => {
            const td = document.createElement('td');

            if (col.type === 'checkbox') {
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = !!c[col.field];
                cb.onchange = function () { updateCheckbox(c.siret, col.field, this.checked, this); };
                td.appendChild(cb);

            } else if (col.type === 'select') {
                const sel = document.createElement('select');
                sel.innerHTML = '<option value="">--</option>' +
                    col.options.map(o =>
                        `<option value="${o.value}" ${c[col.field] === o.value ? 'selected' : ''}>${o.label}</option>`
                    ).join('');
                sel.onchange = function () { updateSelect(c.siret, col.field, this.value, this); };
                td.appendChild(sel);

            } else if (col.type === 'date') {
                const inp = document.createElement('input');
                inp.type = 'date';
                inp.value = formatDate(c[col.field]);
                inp.onchange = function () { updateField(c.siret, col.field, this.value, this); };
                td.appendChild(inp);

            } else {
                // Type texte par défaut
                const inp = document.createElement('input');
                inp.type = 'text';
                inp.value = c[col.field] || '';
                inp.onchange = function () { updateField(c.siret, col.field, this.value, this); };
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
        if (assistant && !(c.assistant       || "").toLowerCase().includes(assistant)) return false;
        if (collab    && !(c.collaborateur   || "").toLowerCase().includes(collab))    return false;
        if (annee     && !(String(c.annee    || "")).includes(annee))                  return false;
        if (cloture   && !(c.date_de_cloture || "").toLowerCase().includes(cloture))   return false;
        return true;
    });

    display(filtered);
}

async function load() {
    // Skeleton loader : nombre de colonnes = 6 fixes + colonnes spécifiques à la page
    const colCount = 6 + (_pageConfig.columns ? _pageConfig.columns.length : 0);
    document.getElementById("table").innerHTML = Array.from({ length: 8 }, () => `
        <tr class="skeleton-row">
            ${Array.from({ length: colCount }, () => `<td><span class="skeleton"></span></td>`).join('')}
        </tr>
    `).join('');

    const data = await fetchClients();

    dataGlobal = _pageConfig.filterField
        ? data.filter(c => c[_pageConfig.filterField] == true || c[_pageConfig.filterField] === "true" || c[_pageConfig.filterField] === 1)
        : data;

    display(dataGlobal);
    bindFilterInputs(".filters-top input");
}

// Export CSV du tableau affiché (données filtrées)
function exportCurrentCSV() {
    const cols = [
        { label: "Code",          field: "code_client" },
        { label: "Nom",           field: "nom_client" },
        { label: "Assistant",     field: "assistant" },
        { label: "Collaborateur", field: "collaborateur" },
        { label: "Année",         field: "annee" },
        { label: "Clôture",       field: "date_de_cloture" },
        ..._pageConfig.columns.map(c => ({ label: c.header, field: c.field }))
    ];

    const safeName = _pageConfig.titre.toLowerCase().replace(/\s+/g, '_') + '.csv';
    exportCSV(_currentData, safeName, cols);
}
