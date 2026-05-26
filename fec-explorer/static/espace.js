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
}
