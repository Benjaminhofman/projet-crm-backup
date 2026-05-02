from collections import defaultdict


def _commence_par(compte: str, *prefixes: str) -> bool:
    return any(compte.startswith(p) for p in prefixes)


def calculate_indicators(rows: list) -> list:
    """
    Calcule les indicateurs financiers clés par SIRET à partir des lignes
    retournées par parse_multiple_fec.

    Règles de signe (convention FEC créditeur = produit) :
      - ca             : comptes 70   → solde × -1
      - charges        : comptes 6    → solde (positif = charge)
      - produits       : comptes 7 hors 791 → solde × -1
      - tresorerie     : comptes 5    → solde
      - emprunt        : comptes 16   → solde
      - masse_salariale: comptes 64   → solde
      - resultat       : produits - charges

    Retourne :
      [{"siret": str, "ca": float, "charges": float, "produits": float,
        "tresorerie": float, "emprunt": float, "masse_salariale": float,
        "resultat": float}, ...]
    """
    # Accumulation par SIRET
    acc = defaultdict(lambda: {
        "ca":              0.0,
        "charges":         0.0,
        "produits":        0.0,
        "tresorerie":      0.0,
        "emprunt":         0.0,
        "masse_salariale": 0.0,
    })

    for r in rows:
        siret  = r["siret"]
        compte = r["compte"]
        solde  = r["solde"]

        # Chiffre d'affaires — comptes 70
        if _commence_par(compte, "70"):
            acc[siret]["ca"] += solde * -1

        # Charges — comptes 6
        if _commence_par(compte, "6"):
            acc[siret]["charges"] += solde

            # Masse salariale — comptes 64 (sous-ensemble de 6)
            if _commence_par(compte, "64"):
                acc[siret]["masse_salariale"] += solde

        # Produits — comptes 7 sauf 791
        if _commence_par(compte, "7") and not _commence_par(compte, "791"):
            acc[siret]["produits"] += solde * -1

        # Trésorerie — comptes 5
        if _commence_par(compte, "5"):
            acc[siret]["tresorerie"] += solde

        # Emprunts — comptes 16
        if _commence_par(compte, "16"):
            acc[siret]["emprunt"] += solde

    # Mise en forme finale avec calcul du résultat
    resultat = []
    for siret, vals in sorted(acc.items()):
        resultat.append({
            "siret":           siret,
            "ca":              round(vals["ca"],              2),
            "charges":         round(vals["charges"],         2),
            "produits":        round(vals["produits"],        2),
            "tresorerie":      round(vals["tresorerie"],      2),
            "emprunt":         round(vals["emprunt"],         2),
            "masse_salariale": round(vals["masse_salariale"], 2),
            "resultat":        round(vals["produits"] - vals["charges"], 2),
        })

    return resultat
