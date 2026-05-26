// Module partagé : gestion de l'« espace collaborateur ».
// L'espace actif est stocké dans sessionStorage sous la clé "espaceCollab"
// (état UI éphémère, effacé à la fermeture de l'onglet — comme le token JWT
// crm_token). Aucune donnée métier n'est persistée ici.
//
// - index.html : <select id="mon-espace"> écrit la clé (onMonEspaceChange) ;
//   initEspaceIndex() pré-remplit le select + badge ✕ au chargement.
// - Pages de suivi : injectEspaceCollab() lit la clé, remplit l'input
//   collaborateur, affiche un badge, et expose window._espaceCollab.
// - Chaque loadPage() lit sessionStorage pour poser collaborateur_exact.
//   Plus aucune propagation de ?collab dans les liens : sessionStorage
//   persiste entre toutes les navigations du même onglet.

function injectEspaceCollab() {
    const collab = sessionStorage.getItem("espaceCollab");
    if (!collab) return;

    // 1. Injecter dans l'input collaborateur existant (selon la page)
    const inp = document.getElementById("filter-collab")
             || document.getElementById("f-collab");
    if (inp) inp.value = collab;
    window._espaceCollab = collab;

    // 2. Badge « Espace : X » — lien retour vers l'accueil (l'espace persiste)
    const badge = document.createElement("a");
    badge.href = "index.html";
    badge.textContent = "🏢 Espace : " + collab;
    badge.title = "Retour à l'accueil";
    badge.style.cssText = "margin-left:14px;background:#fff;color:#273c75;"
        + "padding:5px 12px;border-radius:16px;font-size:13px;text-decoration:none;"
        + "font-weight:600;box-shadow:0 1px 4px rgba(0,0,0,0.15);vertical-align:middle;";

    // Emplacement : après #page-title (pages decl-engine), sinon dans .header
    const title = document.getElementById("page-title");
    if (title) {
        title.insertAdjacentElement("afterend", badge);
    } else {
        const header = document.querySelector(".header");
        if (header) header.appendChild(badge);
    }
}


// ── Espace collaborateur côté index.html (select + badge ✕) ───────────

// Alimente les selects <#mon-espace> (collaborateurs) et <#mon-assistant>
// (assistants) depuis /api/clients/filters, en un seul fetch.
async function populateMonEspace() {
    const selC = document.getElementById("mon-espace");
    const selA = document.getElementById("mon-assistant");
    if (!selC && !selA) return;
    try {
        const res = await fetch("/api/clients/filters");
        if (!res.ok) return;
        const data = await res.json();
        const fill = (sel, vals, currentKey) => {
            if (!sel) return;
            const current = sessionStorage.getItem(currentKey) || "";
            (vals || []).forEach(v => {
                const opt = document.createElement("option");
                opt.value = v;
                opt.textContent = v;
                if (v === current) opt.selected = true;
                sel.appendChild(opt);
            });
        };
        fill(selC, data.collaborateurs, "espaceCollab");
        fill(selA, data.assistants,     "espaceAssistant");
    } catch {}
}

// Changement du select collaborateur : écrit l'espace en sessionStorage puis
// ré-applique le filtre SANS rechargement complet (badge + loadPage(1)).
// "— Tous —" (val vide) → efface la clé.
function onMonEspaceChange(val) {
    if (val) sessionStorage.setItem("espaceCollab", val);
    else sessionStorage.removeItem("espaceCollab");
    renderEspaceBadge(val);                            // badge à jour (ou masqué)
    if (typeof loadPage === "function") loadPage(1);   // recharge la liste filtrée
    if (typeof loadDashboardExtra === "function") loadDashboardExtra(); // dashboard filtré
}

// Changement du select assistant : écrit l'espace assistant en sessionStorage
// puis recharge la liste SANS rechargement complet.
function onMonAssistantChange(val) {
    if (val) sessionStorage.setItem("espaceAssistant", val);
    else sessionStorage.removeItem("espaceAssistant");
    renderEspaceBadge(sessionStorage.getItem("espaceCollab")); // badge collaborateur inchangé
    if (typeof loadPage === "function") loadPage(1);
}

// Badge "Espace : X" du header index, avec bouton ✕ (quitte l'espace)
function renderEspaceBadge(collab) {
    const badge = document.getElementById("espace-badge");
    if (!badge) return;
    if (!collab) { badge.style.display = "none"; badge.textContent = ""; return; }
    badge.style.display = "inline-flex";
    badge.textContent = "Espace : " + collab + " "; // textContent → anti-XSS
    const close = document.createElement("button");
    close.textContent = "✕";
    close.title = "Quitter cet espace";
    close.onclick = () => {
        const sel = document.getElementById("mon-espace");
        if (sel) sel.value = "";        // remet le select sur « — Tous — »
        onMonEspaceChange("");          // efface l'espace + recharge sans reload
    };
    close.style.cssText = "background:rgba(255,255,255,0.25);color:white;border:none;"
        + "width:18px;height:18px;border-radius:50%;cursor:pointer;font-size:11px;"
        + "line-height:1;display:flex;align-items:center;justify-content:center;margin-left:6px;";
    badge.appendChild(close);
}

// Initialise l'espace collaborateur sur index.html (à appeler au démarrage)
function initEspaceIndex() {
    const collab = sessionStorage.getItem("espaceCollab") || "";
    if (collab) {
        const sel = document.getElementById("mon-espace");
        if (sel) sel.value = collab; // pré-remplissage du select
        renderEspaceBadge(collab);
    }
    // collaborateur_exact est posé dans loadPage() via sessionStorage
}
