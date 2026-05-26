// Module partagé : gestion de l'« espace collaborateur » transmis via ?collab.
// Inclus sur index.html (propagation), et sur les pages de suivi
// (decl-engine, missions, opportunites, commercial, rendement).
//
// Au chargement de la page, si le paramètre ?collab=X est présent :
//   1. injecte X dans l'input collaborateur existant (filter-collab / f-collab)
//      → repris en collaborateur_exact par loadPage()
//   2. affiche un badge « 🏢 Espace : X » (lien retour vers index.html?collab=X)
//
// L'appel à loadPage(1) / applyFilters() reste de la responsabilité de la page,
// après injection de la valeur.

function injectEspaceCollab() {
    const collab = new URLSearchParams(location.search).get("collab");
    if (!collab) return; // pas de param → comportement normal

    // 1. Injecter dans l'input collaborateur existant (selon la page)
    const inp = document.getElementById("filter-collab")
             || document.getElementById("f-collab");
    if (inp) inp.value = collab;

    // Expose la valeur globalement : loadPage() peut filtrer même si l'input
    // n'est pas encore rempli (ordre de chargement des scripts).
    window._espaceCollab = collab;

    // 2. Badge « Espace : X » — lien retour vers l'accueil de cet espace
    const badge = document.createElement("a");
    badge.href = "index.html?collab=" + encodeURIComponent(collab);
    badge.textContent = "🏢 Espace : " + collab;
    badge.title = "Retour à l'accueil de cet espace";
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

    // 3. Propager ?collab sur tous les liens internes vers des pages .html
    // (retour ⬅, liens de declaratif.html/missions.html vers les sous-pages
    // déclaratives, etc.). Les params existants (ex. ?siret=) sont préservés.
    propagateCollabToLinks(collab);

    // 4. Les liens vers les sous-pages sont parfois générés/injectés
    // dynamiquement APRÈS ce premier passage (rendu du tableau par
    // decl-engine.js, pagination, etc.). Un MutationObserver réapplique la
    // propagation à chaque ajout de nœud. On observe childList + subtree
    // UNIQUEMENT : propagateCollabToLinks() modifie des attributs (href/onclick)
    // via setAttribute, donc observer les attributs créerait une boucle infinie.
    if (!window._espaceObserver) {
        window._espaceObserver = new MutationObserver(() => propagateCollabToLinks(collab));
        window._espaceObserver.observe(document.body, { childList: true, subtree: true });
    }
}

// Ajoute ?collab=X à tous les liens internes vers une page .html.
// Couvre deux formes : <a href="…html"> ET onclick="location.href='…html'".
// Préserve les autres paramètres d'URL et l'éventuel ancre #hash.
function propagateCollabToLinks(collab) {
    if (!collab) return;

    // Forme 1 : ancres <a href="…html">
    document.querySelectorAll("a[href]").forEach(a => {
        const href = a.getAttribute("href");
        if (!href) return;
        if (/^https?:\/\//i.test(href) || href.startsWith("//")) return; // externe
        if (!/\.html(\?|#|$)/.test(href)) return; // uniquement pages .html
        const [pathQuery, hash] = href.split("#");
        const [base, query] = pathQuery.split("?");
        const sp = new URLSearchParams(query || "");
        if (sp.get("collab") === collab) return; // déjà à jour
        sp.set("collab", collab);
        a.setAttribute("href", base + "?" + sp.toString() + (hash ? "#" + hash : ""));
    });

    // Forme 2 : onclick="location.href='…html'" (ex. en-têtes de declaratif.html)
    document.querySelectorAll('[onclick*="location.href"]').forEach(el => {
        const oc = el.getAttribute("onclick");
        if (!oc) return;
        const newOc = oc.replace(/location\.href\s*=\s*'([^']*\.html)([^']*)'/g, (m, base, q) => {
            const sp = new URLSearchParams(q.replace(/^\?/, ""));
            sp.set("collab", collab);
            return "location.href='" + base + "?" + sp.toString() + "'";
        });
        if (newOc !== oc) el.setAttribute("onclick", newOc);
    });
}


// ── Espace collaborateur côté index.html (select + badge ✕ + nav) ─────
// index.html pilote l'espace via un <select id="mon-espace"> et un badge
// fermable, et propage ?collab sur les liens du menu Navigation.

// Alimente le <select id="mon-espace"> depuis /api/clients/filters
async function populateMonEspace() {
    const sel = document.getElementById("mon-espace");
    if (!sel) return;
    try {
        const res = await fetch("/api/clients/filters");
        if (!res.ok) return;
        const data = await res.json();
        const current = new URLSearchParams(location.search).get("collab") || "";
        (data.collaborateurs || []).forEach(c => {
            const opt = document.createElement("option");
            opt.value = c;
            opt.textContent = c;
            if (c === current) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch {}
}

// Navigation au changement du select : index.html?collab=<val> (vide = "— Tous —")
function onMonEspaceChange(val) {
    window.location.href = "index.html?collab=" + encodeURIComponent(val || "");
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
    close.onclick = () => { window.location.href = "index.html"; };
    close.style.cssText = "background:rgba(255,255,255,0.25);color:white;border:none;"
        + "width:18px;height:18px;border-radius:50%;cursor:pointer;font-size:11px;"
        + "line-height:1;display:flex;align-items:center;justify-content:center;margin-left:6px;";
    badge.appendChild(close);
}

// Propage ?collab=X sur tous les liens du menu Navigation (si présent)
function propagateCollabToNav(collab) {
    if (!collab) return; // pas de param → liens normaux
    document.querySelectorAll("#nav-menu a").forEach(a => {
        const base = a.getAttribute("href").split("?")[0];
        a.setAttribute("href", base + "?collab=" + encodeURIComponent(collab));
    });
}

// Initialise l'espace collaborateur sur index.html (à appeler au démarrage)
function initEspaceIndex() {
    const collab = new URLSearchParams(location.search).get("collab") || "";
    if (collab) {
        const sel = document.getElementById("mon-espace");
        if (sel) sel.value = collab; // pré-remplissage immédiat
        renderEspaceBadge(collab);
        propagateCollabToNav(collab);
    }
    // collaborateur_exact est injecté dans loadPage() via le param ?collab
}
