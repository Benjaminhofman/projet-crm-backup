// Moteur partagé pour toutes les pages de suivi déclaratif.
// Chaque page appelle initDeclaratifPage(config) avec sa configuration unique.

let _pageConfig = null;
let _currentData = [];
let _currentPage = 1;
const _LIMIT = 50;

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

    bindFilterInputs(".filters-top input");

    // Labels des selects filtres (title + première option)
    const filterLabels = {
        'filter-assistant': 'Assistant',
        'filter-collab':    'Collaborateur',
        'filter-annee':     'Année',
        'filter-cloture':   'Clôture'
    };
    Object.entries(filterLabels).forEach(([id, label]) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.title = label;
        if (el.tagName === 'SELECT' && el.options[0] && el.options[0].value === '') {
            el.options[0].textContent = label + '...';
        } else if (el.tagName === 'INPUT' && !el.placeholder) {
            el.placeholder = label + '...';
        }
    });

    loadPage(1);
}

function display(data) {
    _currentData = data;

    const table = document.getElementById("table");
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
            <td>${(v => { if (!v) return ''; const p = v.split('-'); return p[2]+'/'+p[1]; })(c.date_de_cloture)}</td>
        `;

        // Colonnes dynamiques définies par la config de la page
        _pageConfig.columns.forEach(col => {
            const td = document.createElement('td');

            if (col.type === 'checkbox') {
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                const isTruthy = v => v===true||v==='t'||v==='true'||v===1||v==='1';
                cb.checked = isTruthy(c[col.field]);
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
                if (col.disabledFn && col.disabledFn(c)) {
                    inp.disabled = true;
                    inp.style.background = '#f0f0f0';
                }
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

function renderPagination(page, pages, total) {
    let pag = document.getElementById('pagination');
    if (!pag) {
        pag = document.createElement('div');
        pag.id = 'pagination';
        pag.style.cssText = 'display:flex;align-items:center;gap:12px;margin-top:10px;font-size:14px;';
        document.querySelector('table').after(pag);
    }
    document.getElementById("counter").textContent = '';
    pag.innerHTML = `
        <button onclick="loadPage(${page - 1})" ${page <= 1 ? 'disabled' : ''}
            style="padding:5px 12px;border-radius:6px;border:1px solid #ccc;cursor:pointer;background:white;">
            ◀ Précédent
        </button>
        <span>Page ${page}/${pages} — ${total} dossier${total > 1 ? 's' : ''}</span>
        <button onclick="loadPage(${page + 1})" ${page >= pages ? 'disabled' : ''}
            style="padding:5px 12px;border-radius:6px;border:1px solid #ccc;cursor:pointer;background:white;">
            Suivant ▶
        </button>
    `;
}

async function loadPage(page = 1) {
    _currentPage = page;

    // Skeleton loader
    const colCount = 6 + (_pageConfig.columns ? _pageConfig.columns.length : 0);
    document.getElementById("table").innerHTML = Array.from({ length: 8 }, () => `
        <tr class="skeleton-row">
            ${Array.from({ length: colCount }, () => `<td><span class="skeleton"></span></td>`).join('')}
        </tr>
    `).join('');

    // Construction des paramètres de requête
    const get = id => (document.getElementById(id) || { value: "" }).value.trim();
    const assistant     = get("filter-assistant") || get("f-assistant");
    const collaborateur = get("filter-collab")    || get("f-collab");
    const annee         = get("filter-annee")     || get("f-annee");
    const cloture       = get("filter-cloture")   || get("f-cloture");

    const params = new URLSearchParams({ page, limit: _LIMIT });
    const ff = String(_pageConfig?.filterField || '');
    if (ff) params.append('filterField', ff);
    if (ff) params.append('filterValue', 'true');
    if (assistant)     params.set("assistant_exact",     assistant);
    if (collaborateur) params.set("collaborateur_exact", collaborateur);
    if (annee)         params.set("annee",               annee);
    if (cloture)       params.set("cloture", "-" + cloture + "-");

    try {
        const res = await fetch(`/api/clients?${params}`);
        if (!res.ok) throw new Error("Erreur HTTP " + res.status);
        const response = await res.json();
        display(response.data ?? []);
        renderPagination(response.page, response.pages, response.total);
    } catch (err) {
        console.error("Erreur loadPage:", err);
        document.getElementById("table").innerHTML =
            `<tr><td colspan="20" style="color:#e74c3c;padding:20px;">Erreur de chargement</td></tr>`;
    }
}

function applyFilters() {
    loadPage(1);
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
