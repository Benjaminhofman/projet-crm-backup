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
    renderEspaceBadge();                               // badges à jour (collab + assistant)
    if (typeof loadPage === "function") loadPage(1);   // recharge la liste filtrée
    if (typeof loadDashboardExtra === "function") loadDashboardExtra(); // dashboard filtré
}

// Changement du select assistant : écrit l'espace assistant en sessionStorage
// puis recharge la liste SANS rechargement complet.
function onMonAssistantChange(val) {
    if (val) sessionStorage.setItem("espaceAssistant", val);
    else sessionStorage.removeItem("espaceAssistant");
    renderEspaceBadge();                               // badges à jour (collab + assistant)
    if (typeof loadPage === "function") loadPage(1);
    if (typeof loadDashboardExtra === "function") loadDashboardExtra(); // dashboard (portefeuille)
}

// Badges du header index : « Espace : X » (collaborateur) et
// « 🏠 Assistant : X » (assistant), chacun avec son bouton ✕. Lit directement
// sessionStorage (espaceCollab / espaceAssistant), aucun argument requis.
function renderEspaceBadge() {
    const badge = document.getElementById("espace-badge");
    if (!badge) return;
    const collab    = sessionStorage.getItem("espaceCollab");
    const assistant = sessionStorage.getItem("espaceAssistant");

    if (!collab && !assistant) { badge.style.display = "none"; badge.textContent = ""; return; }

    // Conteneur transparent : on empile des pills individuelles
    badge.style.display = "inline-flex";
    badge.style.background = "transparent";
    badge.style.padding = "0";
    badge.style.gap = "8px";
    badge.textContent = "";

    if (collab)    badge.appendChild(makeEspacePill("👤 Espace : " + collab, "espaceCollab", "mon-espace"));
    if (assistant) badge.appendChild(makeEspacePill("🏠 Assistant : " + assistant, "espaceAssistant", "mon-assistant"));
}

// Construit une pill « label ✕ » ; le ✕ efface la clé sessionStorage, remet
// le select associé sur l'option vide et recharge la liste + le dashboard.
function makeEspacePill(label, storageKey, selectId) {
    const pill = document.createElement("span");
    pill.style.cssText = "display:inline-flex;align-items:center;gap:6px;"
        + "background:rgba(255,255,255,0.2);color:white;padding:5px 6px 5px 12px;"
        + "border-radius:16px;font-size:13px;font-weight:600;";
    pill.textContent = label + " "; // textContent → anti-XSS
    const close = document.createElement("button");
    close.textContent = "✕";
    close.title = "Retirer ce filtre";
    close.onclick = () => {
        sessionStorage.removeItem(storageKey);
        const sel = document.getElementById(selectId);
        if (sel) sel.value = "";
        renderEspaceBadge();
        if (typeof loadPage === "function") loadPage(1);
        if (typeof loadDashboardExtra === "function") loadDashboardExtra();
    };
    close.style.cssText = "background:rgba(255,255,255,0.25);color:white;border:none;"
        + "width:18px;height:18px;border-radius:50%;cursor:pointer;font-size:11px;"
        + "line-height:1;display:flex;align-items:center;justify-content:center;";
    pill.appendChild(close);
    return pill;
}

// Initialise l'espace collaborateur sur index.html (à appeler au démarrage)
function initEspaceIndex() {
    const collab = sessionStorage.getItem("espaceCollab") || "";
    const sel = document.getElementById("mon-espace");
    if (sel && collab) sel.value = collab; // pré-remplissage (aussi fait par populateMonEspace)
    renderEspaceBadge(); // affiche les badges collab + assistant présents
    // collaborateur_exact / assistant_exact posés dans loadPage() via sessionStorage
}
