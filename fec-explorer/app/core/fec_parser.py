import csv
import logging


def parse_fec_file(file_path: str) -> dict:
    """
    Lit un fichier FEC (tabulé, ISO-8859-1) et retourne la balance par compte.

    Colonnes attendues (index 0-based) :
      4  → numéro de compte
      11 → montant débit
      12 → montant crédit

    Retourne :
      { compte: {"debit": float, "credit": float, "solde": float} }
    """
    soldes = {}

    with open(file_path, "r", encoding="ISO-8859-1") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # ignore l'en-tête

        for row_num, row in enumerate(reader, start=2):
            try:
                if len(row) < 13:
                    raise IndexError(
                        f"Ligne {row_num} : {len(row)} colonnes trouvées, 13 attendues"
                    )

                compte = row[4].strip()
                debit  = float(row[11].replace(",", ".")) if row[11].strip() else 0.0
                credit = float(row[12].replace(",", ".")) if row[12].strip() else 0.0

                if compte not in soldes:
                    soldes[compte] = {"debit": 0.0, "credit": 0.0, "solde": 0.0}

                soldes[compte]["debit"]  += debit
                soldes[compte]["credit"] += credit

            except IndexError as e:
                logging.warning("parse_fec_file – %s", e)
            except ValueError as e:
                logging.warning("parse_fec_file – conversion ligne %d : %s", row_num, e)

    # calcul du solde une seule fois après l'agrégation
    for compte, vals in soldes.items():
        vals["solde"] = round(vals["debit"] - vals["credit"], 2)
        vals["debit"]  = round(vals["debit"],  2)
        vals["credit"] = round(vals["credit"], 2)

    return soldes
