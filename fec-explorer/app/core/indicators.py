from collections import defaultdict


def _commence_par(compte: str, *prefixes: str) -> bool:
    return any(compte.startswith(p) for p in prefixes)


def calculate_indicators(rows: list) -> list:
    """
    Calcule les indicateurs financiers clés par SIRET à partir des lignes
    retournées par parse_multiple_fec.

    Règles de signe (convention FEC créditeur = produit) :
      - ca             : comptes 70        → solde × -1
      - charges        : comptes 6         → solde
      - produits       : comptes 7 hors 791 → solde × -1
      - tresorerie     : comptes 5         → solde
      - emprunt        : comptes 16        → solde
      - masse_salariale: comptes 64        → solde
      - assurance      : comptes 616       → solde
      - deplacement    : comptes 625       → solde
      - loyer          : comptes 613       → solde
      - cfe            : comptes 63511     → solde
      - tns            : comptes 644       → solde
      - publicite      : comptes 623       → solde
      - honoraires     : comptes 6226      → solde
      - banque         : comptes 627       → solde
      - compte_791              : comptes 791  → solde × -1
      - produits_financiers     : comptes 76   → solde × -1  (sous-ensemble de produits)
      - produits_exceptionnels  : comptes 77   → solde × -1  (sous-ensemble de produits)
      - placements              : comptes 508  → solde × -1  (sous-ensemble de tresorerie)
      - capital                 : comptes 101  → solde × -1
      - reserves                : comptes 106  → solde × -1
      - report_a_nouveau        : comptes 11   → solde × -1
      - compte_exploitant       : comptes 108  → solde × -1
      - compte_courant_associe  : comptes 455  → solde × -1
      - charges_financieres    : comptes 66    → solde  (sous-ensemble de charges)
      - charges_exceptionnelles: comptes 67    → solde  (sous-ensemble de charges)
      - achats_non_stockes     : comptes 606   → solde  (sous-ensemble de charges)
      - sous_traitance         : comptes 611   → solde  (sous-ensemble de charges)
      - entretien_reparation   : comptes 615   → solde  (sous-ensemble de charges)
      - personnel_exterieur    : comptes 621   → solde  (sous-ensemble de charges)
      - frais_telecom          : comptes 626   → solde  (sous-ensemble de charges)
      - impots_taxes           : comptes 63    → solde  (sous-ensemble de charges, inclut cfe)
      - prestation     : "presta" si 706 présent et 707 absent
      - multitva       : "multitva" si plusieurs comptes 4457* distincts
      - resultat       : produits - charges + compte_791

    Retourne :
      [{"siret": str, "ca": float, "charges": float, "produits": float,
        "tresorerie": float, "emprunt": float, "masse_salariale": float,
        "assurance": float, "deplacement": float, "loyer": float,
        "cfe": float, "tns": float, "publicite": float, "honoraires": float,
        "banque": float, "compte_791": float,
        "produits_financiers": float, "produits_exceptionnels": float,
        "placements": float, "capital": float, "reserves": float,
        "report_a_nouveau": float, "compte_exploitant": float,
        "compte_courant_associe": float,
        "charges_financieres": float, "charges_exceptionnelles": float,
        "achats_non_stockes": float, "sous_traitance": float,
        "entretien_reparation": float, "personnel_exterieur": float,
        "frais_telecom": float, "impots_taxes": float,
        "dotations_amortissements": float, "impot_societes": float,
        "materiel_transport": float, "fond_commerce": float,
        "constructions": float, "materiel_informatique": float,
        "mobilier": float, "stocks": float,
        "clients": float, "fournisseurs": float,
        "prestation": str|None, "multitva": str|None,
        "resultat": float,
        "bfr": float, "frng": float}, ...]
    """
    acc = defaultdict(lambda: {
        "ca":              0.0,
        "charges":         0.0,
        "produits":        0.0,
        "tresorerie":      0.0,
        "emprunt":         0.0,
        "masse_salariale": 0.0,
        "assurance":       0.0,
        "deplacement":     0.0,
        "loyer":           0.0,
        "cfe":             0.0,
        "tns":             0.0,
        "publicite":       0.0,
        "honoraires":      0.0,
        "banque":                  0.0,
        "compte_791":              0.0,
        "produits_financiers":     0.0,
        "produits_exceptionnels":  0.0,
        "placements":              0.0,
        "capital":                 0.0,
        "reserves":                0.0,
        "report_a_nouveau":        0.0,
        "compte_exploitant":       0.0,
        "compte_courant_associe":  0.0,
        "charges_financieres":     0.0,
        "charges_exceptionnelles": 0.0,
        "achats_non_stockes":      0.0,
        "sous_traitance":          0.0,
        "entretien_reparation":    0.0,
        "personnel_exterieur":     0.0,
        "frais_telecom":           0.0,
        "impots_taxes":            0.0,
        "dotations_amortissements": 0.0,
        "impot_societes":           0.0,
        "materiel_transport":       0.0,
        "fond_commerce":            0.0,
        "constructions":            0.0,
        "materiel_informatique":    0.0,
        "mobilier":                 0.0,
        "stocks":                   0.0,
        "clients":                  0.0,
        "fournisseurs":             0.0,
    })

    # Indicateurs qualitatifs — ensembles de comptes rencontrés par SIRET
    comptes_706  = defaultdict(bool)   # True si au moins un compte 706
    comptes_707  = defaultdict(bool)   # True si au moins un compte 707
    comptes_4457 = defaultdict(set)    # ensemble des comptes 4457*

    for r in rows:
        siret  = r["siret"]
        compte = r["compte"]
        solde  = r["solde"]

        # ── Produits ──────────────────────────────────────────────────────────

        if _commence_par(compte, "70"):
            acc[siret]["ca"] += solde * -1

        # 791 isolé avant le bloc 7 générique
        if _commence_par(compte, "791"):
            acc[siret]["compte_791"] += solde * -1
        elif _commence_par(compte, "7"):
            acc[siret]["produits"] += solde * -1

        # Marqueurs prestation
        if _commence_par(compte, "706"):
            comptes_706[siret] = True
        if _commence_par(compte, "707"):
            comptes_707[siret] = True

        # ── Charges ───────────────────────────────────────────────────────────

        if _commence_par(compte, "6"):
            acc[siret]["charges"] += solde

            if _commence_par(compte, "64"):
                acc[siret]["masse_salariale"] += solde
                if _commence_par(compte, "644"):
                    acc[siret]["tns"] += solde

            elif _commence_par(compte, "616"):
                acc[siret]["assurance"] += solde

            elif _commence_par(compte, "625"):
                acc[siret]["deplacement"] += solde

            elif _commence_par(compte, "613"):
                acc[siret]["loyer"] += solde

            elif _commence_par(compte, "63511"):
                acc[siret]["cfe"] += solde

            elif _commence_par(compte, "623"):
                acc[siret]["publicite"] += solde

            elif _commence_par(compte, "6226"):
                acc[siret]["honoraires"] += solde

            elif _commence_par(compte, "627"):
                acc[siret]["banque"] += solde

            # Charges détaillées — if indépendants pour cumuler sans exclusion
            if _commence_par(compte, "66"):
                acc[siret]["charges_financieres"] += solde

            if _commence_par(compte, "67"):
                acc[siret]["charges_exceptionnelles"] += solde

            if _commence_par(compte, "606"):
                acc[siret]["achats_non_stockes"] += solde

            if _commence_par(compte, "611"):
                acc[siret]["sous_traitance"] += solde

            if _commence_par(compte, "615"):
                acc[siret]["entretien_reparation"] += solde

            if _commence_par(compte, "621"):
                acc[siret]["personnel_exterieur"] += solde

            if _commence_par(compte, "626"):
                acc[siret]["frais_telecom"] += solde

            if _commence_par(compte, "63"):
                acc[siret]["impots_taxes"] += solde

            if _commence_par(compte, "68"):
                acc[siret]["dotations_amortissements"] += solde

            if _commence_par(compte, "695"):
                acc[siret]["impot_societes"] += solde

        # ── Produits financiers / exceptionnels (sous-ensembles de 7) ───────────

        if _commence_par(compte, "76"):
            acc[siret]["produits_financiers"] += solde * -1

        if _commence_par(compte, "77"):
            acc[siret]["produits_exceptionnels"] += solde * -1

        # ── Immobilisations (classe 2) ────────────────────────────────────────

        # 2183/2184 sont des sous-ensembles de 218 — if indépendants
        if _commence_par(compte, "218"):
            acc[siret]["materiel_transport"] += solde
        if _commence_par(compte, "2183"):
            acc[siret]["materiel_informatique"] += solde
        if _commence_par(compte, "2184"):
            acc[siret]["mobilier"] += solde

        if _commence_par(compte, "207"):
            acc[siret]["fond_commerce"] += solde

        if _commence_par(compte, "213"):
            acc[siret]["constructions"] += solde

        # ── Stocks (classe 3) ─────────────────────────────────────────────────

        if _commence_par(compte, "3"):
            acc[siret]["stocks"] += solde

        # ── Créances / dettes d'exploitation ─────────────────────────────────

        # 411 : créances clients — actif débiteur → signe normal
        if _commence_par(compte, "411"):
            acc[siret]["clients"] += solde

        # 401 : dettes fournisseurs — passif créditeur → × -1 pour valeur positive
        if _commence_par(compte, "401"):
            acc[siret]["fournisseurs"] += solde * -1

        # ── Bilan actif ───────────────────────────────────────────────────────

        if _commence_par(compte, "5"):
            acc[siret]["tresorerie"] += solde
            if _commence_par(compte, "508"):
                acc[siret]["placements"] += solde * -1

        if _commence_par(compte, "16"):
            acc[siret]["emprunt"] += solde

        # ── Bilan passif ──────────────────────────────────────────────────────

        if _commence_par(compte, "101"):
            acc[siret]["capital"] += solde * -1

        if _commence_par(compte, "106"):
            acc[siret]["reserves"] += solde * -1

        # 108 testé avant "11" pour éviter qu'il matche le préfixe "1"
        if _commence_par(compte, "108"):
            acc[siret]["compte_exploitant"] += solde * -1
        elif _commence_par(compte, "11"):
            acc[siret]["report_a_nouveau"] += solde * -1

        if _commence_par(compte, "455"):
            acc[siret]["compte_courant_associe"] += solde * -1

        # ── TVA multi-taux ────────────────────────────────────────────────────

        if _commence_par(compte, "4457"):
            comptes_4457[siret].add(compte)

    # ── Mise en forme finale ──────────────────────────────────────────────────
    resultat = []
    for siret, vals in sorted(acc.items()):
        c791 = vals["compte_791"]

        marge_brute = (
            vals["ca"] - vals["achats_non_stockes"] - vals["sous_traitance"]
        )
        va = (
            marge_brute
            - vals["loyer"] - vals["assurance"]     - vals["entretien_reparation"]
            - vals["frais_telecom"] - vals["publicite"] - vals["honoraires"]
            - vals["banque"] - vals["deplacement"]  - vals["personnel_exterieur"]
        )
        ebe  = va  - vals["masse_salariale"] - vals["impots_taxes"]
        rex  = ebe - vals["dotations_amortissements"]
        res  = vals["produits"] - vals["charges"] + c791
        caf  = res + vals["dotations_amortissements"] - c791

        bfr  = vals["stocks"] + vals["clients"] - vals["fournisseurs"]
        immo = vals["materiel_transport"] + vals["fond_commerce"] + vals["constructions"]
        frng = (
            vals["capital"] + vals["reserves"] + vals["report_a_nouveau"] + res
            - immo
        )

        productivite            = round(va / vals["masse_salariale"], 2) if vals["masse_salariale"] > 0 else 0
        capacite_remboursement  = round(abs(vals["emprunt"]) / caf, 2) if caf > 0 else 999

        liquidite_generale  = round((vals["clients"] + vals["stocks"] + vals["tresorerie"]) / vals["fournisseurs"], 2) if vals["fournisseurs"] > 0 else 999
        delai_client        = round((vals["clients"]      / vals["ca"])                  * 360, 2) if vals["ca"]                  > 0 else 0
        delai_fournisseur   = round((vals["fournisseurs"] / vals["achats_non_stockes"])  * 360, 2) if vals["achats_non_stockes"]  > 0 else 0

        resultat.append({
            "siret":           siret,
            "ca":              round(vals["ca"],              2),
            "charges":         round(vals["charges"],         2),
            "produits":        round(vals["produits"],        2),
            "tresorerie":      round(vals["tresorerie"],      2),
            "emprunt":         round(vals["emprunt"],         2),
            "masse_salariale": round(vals["masse_salariale"], 2),
            "assurance":       round(vals["assurance"],       2),
            "deplacement":     round(vals["deplacement"],     2),
            "loyer":           round(vals["loyer"],           2),
            "cfe":             round(vals["cfe"],             2),
            "tns":             round(vals["tns"],             2),
            "publicite":       round(vals["publicite"],       2),
            "honoraires":      round(vals["honoraires"],      2),
            "banque":                  round(vals["banque"],                  2),
            "compte_791":              round(c791,                             2),
            "produits_financiers":     round(vals["produits_financiers"],      2),
            "produits_exceptionnels":  round(vals["produits_exceptionnels"],   2),
            "placements":              round(vals["placements"],               2),
            "capital":                 round(vals["capital"],                  2),
            "reserves":                round(vals["reserves"],                 2),
            "report_a_nouveau":        round(vals["report_a_nouveau"],         2),
            "compte_exploitant":       round(vals["compte_exploitant"],        2),
            "compte_courant_associe":  round(vals["compte_courant_associe"],   2),
            "charges_financieres":     round(vals["charges_financieres"],     2),
            "charges_exceptionnelles": round(vals["charges_exceptionnelles"], 2),
            "achats_non_stockes":      round(vals["achats_non_stockes"],      2),
            "sous_traitance":          round(vals["sous_traitance"],          2),
            "entretien_reparation":    round(vals["entretien_reparation"],    2),
            "personnel_exterieur":     round(vals["personnel_exterieur"],     2),
            "frais_telecom":           round(vals["frais_telecom"],           2),
            "impots_taxes":             round(vals["impots_taxes"],             2),
            "dotations_amortissements": round(vals["dotations_amortissements"], 2),
            "impot_societes":           round(vals["impot_societes"],           2),
            "materiel_transport":       round(vals["materiel_transport"],       2),
            "fond_commerce":            round(vals["fond_commerce"],            2),
            "constructions":            round(vals["constructions"],            2),
            "materiel_informatique":    round(vals["materiel_informatique"],    2),
            "mobilier":                 round(vals["mobilier"],                 2),
            "stocks":                   round(vals["stocks"],                   2),
            "clients":                  round(vals["clients"],                  2),
            "fournisseurs":             round(vals["fournisseurs"],             2),
            "prestation":              "presta" if comptes_706[siret] and not comptes_707[siret] else None,
            "multitva":                "multitva" if len(comptes_4457[siret]) > 1 else None,
            "resultat":                round(res, 2),
            "marge_brute":             round(marge_brute, 2),
            "valeur_ajoutee":          round(va,          2),
            "ebe":                     round(ebe,         2),
            "rex":                     round(rex,         2),
            "resultat_financier":      round(vals["produits_financiers"]    - vals["charges_financieres"],     2),
            "resultat_exceptionnel":   round(vals["produits_exceptionnels"] - vals["charges_exceptionnelles"], 2),
            "caf":                     round(caf,  2),
            "bfr":                     round(bfr,  2),
            "frng":                    round(frng, 2),
            "productivite":            productivite,
            "capacite_remboursement":  capacite_remboursement,
            "liquidite_generale":      liquidite_generale,
            "delai_client":            delai_client,
            "delai_fournisseur":       delai_fournisseur,
        })

    return resultat
