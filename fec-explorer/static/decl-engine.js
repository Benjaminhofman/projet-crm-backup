// Moteur partagé pour toutes les pages de suivi déclaratif.
// Chaque page appelle initDeclaratifPage(config) avec sa configuration unique.

const MOIS_LABELS = {
    '01':'Janvier','02':'Février','03':'Mars','04':'Avril',
    '05':'Mai','06':'Juin','07':'Juillet','08':'Août',
    '09':'Septembre','10':'Octobre','11':'Novembre','12':'Décembre'
};

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

    bindFilterInputs(".filters-top input:not(#search)");

    const filterTop = document.querySelector('.filters-top');
    if (filterTop) {
        // Champ recherche nom client (inséré en premier)
        const srchDl  = document.createElement('datalist');
        srchDl.id = 'dl-search';
        const srchInp = document.createElement('input');
        srchInp.type = 'text';
        srchInp.id   = 'search';
        srchInp.setAttribute('list', 'dl-search');
        srchInp.placeholder = '🔍 Nom client…';
        srchInp.setAttribute('autocomplete', 'off');
        filterTop.insertBefore(srchDl,  filterTop.firstChild);
        filterTop.insertBefore(srchInp, srchDl);
        let _st;
        srchInp.addEventListener('input', () => { clearTimeout(_st); _st = setTimeout(applyFilters, 300); });

        // Bouton Réinitialiser
        const btn = document.createElement('button');
        btn.textContent = '🔄 Réinitialiser';
        btn.style.cssText = 'background:#95a5a6;color:white;padding:6px 12px;border-radius:6px;border:none;cursor:pointer;';
        btn.onclick = function () {
            filterTop.querySelectorAll('input, select').forEach(el => { el.value = ''; });
            applyFilters();
        };
        filterTop.appendChild(btn);
    }

    populateSelects();
    loadPage(1);
}

async function populateSelects() {
    try {
        const res = await fetch('/api/clients/filters');
        const f = await res.json();
        const fill = (id, vals, labelFn) => {
            const dl = document.getElementById(id);
            if (!dl) return;
            vals.forEach(v => {
                if (!v) return;
                const opt = document.createElement('option');
                opt.value = labelFn ? labelFn(v) : v;
                dl.appendChild(opt);
            });
        };
        fill('dl-search',    f.noms,           null);
        fill('dl-assistant', f.assistants,     null);
        fill('dl-collab',    f.collaborateurs,  null);
        fill('dl-annee',     f.annees,         null);
        fill('dl-cloture',   f.mois_cloture,   v => `${MOIS_LABELS[v] || v} (${v})`);
    } catch {}
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

            } else if (col.type === 'readonly') {
                // Colonne lecture seule — affiche une valeur formatée sans input
                const span = document.createElement('span');
                span.textContent = col.formatFn ? col.formatFn(c[col.field], c) : (c[col.field] ?? '—');
                span.style.cssText = 'font-size:13px;color:#555;';
                td.appendChild(span);

            } else {
                // Type texte par défaut
                const inp = document.createElement('input');
                inp.type = 'text';
                inp.value = c[col.field] || '';
                if (col.disabledFn && col.disabledFn(c)) {
                    inp.disabled = true;
                    inp.style.background = '#f0f0f0';
                    // Tooltip sur le TD (les inputs disabled n'affichent pas toujours le title)
                    if (col.tooltipFn) td.title = col.tooltipFn(c);
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
    const search = get("search");
    if (search) params.set("search", search);
    if (assistant)     params.set("assistant_exact",     assistant);
    if (collaborateur) params.set("collaborateur_exact", collaborateur);
    if (annee)         params.set("annee",               annee);
    if (cloture) {
        const mm = cloture.match(/\((\d{2})\)$/)?.[1] || cloture;
        params.set("cloture", "-" + mm + "-");
    }

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
