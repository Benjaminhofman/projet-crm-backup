# CRM Collaborateurs Comptables

## Présentation du projet
Application CRM destinée aux collaborateurs comptables pour piloter 
un portefeuille client. L'objectif prioritaire est une UX/UI 
excellente : fluide, intuitive et moderne.

Intégrations actuelles et à venir :
- **Make (Integromat)** : automatisation de workflows (en cours)

## Règles de comportement
- Toujours répondre et commenter en **français**
- Ne jamais demander de confirmation avant de modifier, créer 
  ou supprimer un fichier
- Ne jamais demander de permission avant d'exécuter une commande
- Travailler de manière autonome et aller jusqu'au bout des tâches
- Après chaque tâche terminée, proposer automatiquement 2 ou 3 
  améliorations ou nouvelles fonctionnalités pertinentes en lien 
  avec le code modifié

## Priorités de développement
- **UX/UI en premier** : chaque fonctionnalité doit être fluide, 
  responsive et agréable à utiliser
- Privilégier les animations subtiles et les transitions douces
- Penser à l'ergonomie pour un usage quotidien intensif 
  (collaborateurs comptables)
- Optimiser les performances (chargements rapides, pas de blocage UI)

## Standards de code
- Code propre, lisible et bien commenté en français
- Composants réutilisables et modulaires
- Toujours gérer les états de chargement et les erreurs
- Penser à l'expérience mobile si pertinent


## Ce qu'il ne faut pas toucher
- Les fichiers de configuration d'environnement (.env)
- Les clés API et tokens d'authentification

le lien de mon projet sur github est https://github.com/Benjaminhofman/projet-crm
- Après chaque modification de code, faire automatiquement :
  1. git add .
  2. git commit -m "message descriptif en français"
  3. git push origin main
- Ne jamais demander de confirmation avant de push
- Les messages de commit doivent décrire clairement ce qui a été modifié

## Mise à jour automatique
A la fin de chaque session de travail, mets à jour la section 
"État du projet" et "Prochaines étapes" de ce fichier CLAUDE.md 
avec ce qui a été accompli et ce qui reste à faire.

Dans CLAUDE.md, remplace la section "## Intégration Airtable" et ajoute les sections manquantes :

## Stack technique actuelle
- Frontend : HTML/JS vanilla (static/ servi par FastAPI)
- Backend : FastAPI Python (fec-explorer/app/main.py)
- Base de données : PostgreSQL (Render, Frankfurt)
- Hébergement : Render (Web Service + PostgreSQL)
- Versioning : GitHub https://github.com/Benjaminhofman/projet-crm
- URL production : https://projet-crm-m0o3.onrender.com

## Architecture des fichiers
- fec-explorer/app/main.py : API FastAPI (tous les endpoints)
- fec-explorer/static/ : tous les fichiers HTML/JS servis
- fec-explorer/app/core/fec_parser.py : parsing des fichiers FEC
- fec-explorer/app/core/indicators.py : calcul des 61+ indicateurs
- fec-explorer/app/core/postgres_sync.py : sync FEC → PostgreSQL
- fec-explorer/import_csv.py : import CSV → PostgreSQL
- fec-explorer/sync_html.py : synchronise HTML racine → static/

## Base de données PostgreSQL
- Table principale : clients (135 colonnes)
- Colonnes _r : alimentées par le FEC Explorer
- Colonnes sans _r : saisies manuellement via le CRM
- UPSERT sur siret (clé primaire)
- DATABASE_URL depuis variable d'environnement

## Endpoints API principaux
- GET /api/clients → liste tous les clients
- GET /api/client/{siret} → détail d'un client
- POST /api/client/create → créer un client
- POST /api/client/update → modifier un client
- DELETE /api/client/{siret} → supprimer un client
- POST /api/clients/import → import CSV en masse (UPSERT)
- GET /api/clients/columns → types des colonnes PostgreSQL
- GET /api/clients/template-csv → CSV vide avec en-têtes
- POST /update-airtable → met à jour un champ (siret, field, value)
- POST /api/fec/upload → parse FEC + sync PostgreSQL

## Règles importantes
- NE JAMAIS utiliser Airtable — migration terminée, PostgreSQL uniquement
- Toujours utiliser c.siret et NON c.id dans les fichiers HTML
- Les noms de champs sont en snake_case PostgreSQL (pas d'espaces)
- Après modification d'un fichier HTML racine, exécuter sync_html.py
  pour synchroniser vers static/
- Les booléens s'envoient en true/false (pas "oui"/"non") vers l'API
- Les dates s'envoient en format ISO YYYY-MM-DD vers l'API

## ~~Intégration Airtable~~ (SUPPRIMÉE)
Airtable a été complètement remplacé par PostgreSQL.
Ne plus jamais utiliser AIRTABLE_TOKEN, BASE_ID ou TABLE_NAME.

## Pièges connus à éviter

1. sync_html.py écrase static/index.html — ce fichier est exclu
   de la synchronisation. Modifier UNIQUEMENT static/index.html
   pour les changements spécifiques à la prod.

2. Render cache les fichiers statiques — la route /index.html
   dans main.py a Cache-Control: no-cache. Ne pas supprimer cette route.

3. Les dates s'affichent en DD/MM/YYYY dans l'interface mais
   sont stockées en YYYY-MM-DD dans PostgreSQL. Toujours convertir
   avant INSERT/UPDATE.

4. La colonne anciennete est calculée via :
   UPDATE clients SET anciennete = EXTRACT(YEAR FROM AGE(NOW(), date_entree))
   Appeler GET /api/migrate/anciennete après chaque import CSV massif.

5. Ne jamais modifier index.html (racine) directement pour la prod —
   seul static/index.html est servi par Render.

## Colonnes calculées PostgreSQL
- anciennete : EXTRACT(YEAR FROM AGE(NOW(), date_entree))
  → recalculer via GET /api/migrate/anciennete après import
- rentabilite : calculé côté JS frontend (honoraires_cpta / temps_passe)
- anciennete badge "Nouveau" : anciennete < 1 ou date_entree récente

Dans CLAUDE.md, ajoute cette section après ## Pièges connus :

## Table NAF
- Table naf (code TEXT, libelle TEXT) dans PostgreSQL
- Importée via GET /api/migrate/naf (données hardcodées dans main.py)
- Trigger update_activite_r : remplit activite_r automatiquement
  quand code_naf_r change (prend les chiffres avant le point)
- Après import CSV massif : appeler /api/migrate/activite

## Colonnes de type TEXT à ne pas confondre avec NUMERIC
Ces colonnes stockent du texte (ex: "détecté", "en cours") mais
étaient créées en NUMERIC dans le schéma initial :
suivi_mission_retraite, suivi_mission_patrimoniale,
suivi_mission_placement, suivi_mission_prevoyance
Si erreur "invalid input syntax for type numeric" :
ALTER TABLE clients ALTER COLUMN suivi_mission_retraite TYPE TEXT;
(idem pour les 3 autres)

## Formats d'affichage
- Dates affichées en JJ/MM (sans année) dans toutes les pages
- SIRET : exactement 9 chiffres (validation frontend)
- filterField dans decl-engine.js : toujours en snake_case minuscules
  ex: "ca12", "tvs", "is", "impot_sur_le_revenu"

## Endpoints de migration
Appeler une seule fois après déploiement ou import massif :
- GET /api/migrate/naf → importe les 88 codes NAF
- GET /api/migrate/activite → remplit activite_r depuis code_naf_r
- GET /api/migrate/anciennete → recalcule anciennete depuis date_entree
- GET /api/migrate/trigger-activite → recrée le trigger PostgreSQL

### ÉTAPE 8 — Champ rendement calculé ✅ TERMINÉ
- Colonne rendement (numeric) ajoutée dans table clients
- Fonction calc_rendement(siret) : score 0-100 pondéré
  (taux horaire 50% + ancienneté 20% + ca_r 15% + resultat_r 15%)
- Trigger trg_rendement BEFORE INSERT/UPDATE auto-recalcule
- Endpoints : /api/migrate/rendement_setup, install_trigger_rendement
- Endpoint debug : /api/debug/rendement, /api/debug/triggers
- Page rendement.html : tri DESC + filtre par tranche + badges couleur

## Architecture du projet (mise à jour 07/05/2026)

### Stack
- Backend : FastAPI Python (`fec-explorer/app/main.py`)
- Frontend : HTML/JS statique dans `static/` (servi par Render)
- BDD : PostgreSQL Render (Basic-256mb, Frankfurt EU)
- DATABASE_URL dans variable d'environnement
- GitHub : Benjaminhofman/projet-crm

### Workflow de modification standard
1. Modifications côté Python → commit → push → Render redéploie en 1-2 min
2. Modifications de schéma BDD → toujours via un endpoint `/api/migrate/...` 
   appelé une fois dans le navigateur (pas de migrations locales)
3. Modifications côté static/ → sync_html.py si édité hors static/, 
   sinon commit direct
4. Hard refresh (Ctrl+Shift+R) après push pour bypasser le cache Render

### Triggers PostgreSQL actifs
- `trigger_activite_r` (BEFORE INSERT/UPDATE) → remplit activite_r 
  depuis code_naf_r (chiffres avant le point)
- `trg_rendement` (BEFORE INSERT OR UPDATE OF honoraires_cpta, 
  temps_passe, ca_r, resultat_r, anciennete) → recalcule rendement
- Diagnostic : `GET /api/debug/triggers`

### Fonctions PostgreSQL
- `calc_rendement(siret)` → calcul depuis la BDD (utilisé par rendement_setup)
- `update_rendement_trigger()` → calcul depuis NEW.* (utilisé par le trigger)
- Les 2 doivent rester synchronisées sur la logique : seuils, plafond, 
  règles de NULL

### Conventions de nommage
- Colonnes BDD : snake_case minuscule strict
- Champs alimentés par FEC : suffixe `_r` (ca_r, resultat_r, activite_r...)
- Champs métier saisis manuellement : sans suffixe
- Champs booléens (missions) : `boolean` PostgreSQL → vérifier le type 
  avant de saisir du texte (cf. bug juridique_exceptionnel étape 10)

### Endpoints utilitaires (debug et migration)
- `/api/migrate/rendement_setup` → recalcule rendement de tous les clients
- `/api/migrate/install_trigger_rendement` → réinstalle le trigger rendement
- `/api/migrate/anciennete` → recalcule colonne anciennete
- `/api/migrate/naf` → crée table naf et importe les codes
- `/api/migrate/activite` → remplit activite_r depuis code_naf_r
- `/api/debug/rendement` → liste clients + ingrédients du calcul
- `/api/debug/triggers` → liste triggers actifs sur table clients
- `/api/rendement_detail/{siret}` → détail JSON pour la modal frontend

### Logique du score rendement (Stratégie C)
- 4 facteurs pondérés : taux horaire 50% / ancienneté 20% / CA 15% / résultat 15%
- Si nb_facteurs_renseignés < 2 → score = NULL
- Score relatif = (pts obtenus / poids cumulé des facteurs renseignés) × 100
- Plafonnement : 2 fact → max 70, 3 fact → max 85, 4 fact → pas de plafond
- Toute modif de la formule doit être reportée DANS LES DEUX fonctions 
  (calc_rendement ET update_rendement_trigger), sinon désynchro

### Pièges connus
- `localStorage`/`sessionStorage` interdits dans Render (à éviter de 
  toute façon)
- Index sur `index.html` doit avoir Cache-Control no-cache (déjà configuré)
- Triggers doivent être recréés via endpoint après chaque modif de leur 
  logique (DROP + CREATE), pas juste CREATE OR REPLACE
- Date de clôture : format JJ/MM partout (déclaratif, commercial, 
  missions, opportunités, rendement, index)

### Style des prompts pour Claude Code (rappel)
- Toujours en français
- Maximum 5-6 lignes par prompt
- Découper en mini-blocs si plus long
- Pas de demande de confirmation avant de coder
- Toujours commit + push à la fin

## Mises à jour 07/05/2026 (session étapes 11-12)

### Nouveau champ calculé : franchise_tva_prest
- Colonne TEXT auto-calculée par trigger `trg_franchise_tva`
- Logique : ca_r < 40000 ET achat_revente = 'non' → 'OUI', 
  NULL si ca_r ou achat_revente manquant → 'Données manquantes', 
  sinon → 'NON'
- Endpoints : /api/migrate/franchise_tva_setup, /api/migrate/install_trigger_franchise_tva
- Affichage : visible dans gestion-clients (à styliser dans declaratif.html ultérieurement)

### Triggers actifs (mis à jour)
1. trigger_activite_r → activite_r depuis SPLIT_PART(code_naf_r, '.', 1)
2. trg_rendement → score 0-100 calculé sur 4 facteurs
3. trg_franchise_tva → franchise_tva_prest depuis ca_r + achat_revente
- Vérification : GET /api/debug/triggers
- Inspection du code source d'une fonction : 
  SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname='nom_fonction'

### Pièges à connaître absolument

#### Piège 1 : UPDATE qui ne déclenche pas le trigger
- Beaucoup de fonctions trigger contiennent `IF NEW.X IS DISTINCT FROM OLD.X`
- Du coup `UPDATE clients SET x = x` ne déclenche RIEN (la valeur n'a pas changé)
- Pour forcer un recalcul global après un fix de fonction, créer un endpoint 
  qui fait un UPDATE direct contournant le trigger :
  UPDATE clients SET activite_r = (SELECT libelle FROM naf 
    WHERE code = SPLIT_PART(code_naf_r::text, '.', 1)) 
    WHERE code_naf_r IS NOT NULL;
- Modèle réutilisable : /api/migrate/force_recalc_<champ>

#### Piège 2 : LEFT vs SPLIT_PART pour code_naf_r
- ❌ LEFT(code_naf_r::text, 1) → ne prend que le 1er caractère ("5" pour "56.30Z")
- ✅ SPLIT_PART(code_naf_r::text, '.', 1) → tout avant le point ("56" pour "56.30Z")
- Le `1` dans SPLIT_PART = numéro de partie, pas nombre de caractères

#### Piège 3 : Une fonction PostgreSQL peut être créée 2 fois différemment
- CREATE OR REPLACE écrase silencieusement l'ancienne version
- Toujours vérifier le code source avec pg_get_functiondef après un fix
- Endpoint type : /api/debug/<nom_fonction>_function

### Méthodologie de débug d'un trigger qui semble cassé

Procédure standard quand un champ calculé donne un résultat bizarre :

1. **Vérifier que le trigger existe** : GET /api/debug/triggers
2. **Inspecter le code de la fonction** : créer endpoint debug avec pg_get_functiondef
3. **Vérifier les données sources** : table de référence (naf), colonnes utilisées
4. **Tester en modifiant réellement la colonne source** dans l'UI 
   (ne pas se contenter d'un UPDATE x = x qui ne déclenche rien)
5. **Forcer un recalcul global** via endpoint /api/migrate/force_recalc_<champ> 
   si plusieurs lignes ont des valeurs figées historiques

### Endpoints debug créés ce soir

- /api/debug/activite_function : code source de update_activite_r()
- /api/debug/naf_sample : échantillon table naf (utile pour vérifier codes)
- /api/debug/type_achat_revente : types des colonnes franchise_tva
- /api/debug/triggers : liste tous les triggers de la table clients

Les endpoints debug peuvent rester en place, ils sont utiles pour 
les futures sessions de débug et ne consomment rien tant qu'on ne 
les appelle pas.

### Convention pour les nouveaux champs calculés

Pour tout futur champ calculé par trigger, suivre cette structure :
1. Endpoint /api/migrate/<champ>_setup → ALTER TABLE + UPDATE initial 
   (utilise calc_<champ>(siret) ou logique CASE inline)
2. Endpoint /api/migrate/install_trigger_<champ> → DROP+CREATE function 
   et trigger (BEFORE INSERT OR UPDATE OF colonnes_sources)
3. Endpoint /api/migrate/force_recalc_<champ> → UPDATE direct contournant 
   trigger (à créer en cas de besoin de recalcul forcé)
4. Endpoint /api/debug/<champ>_function → inspection code sourCE
## ⚠️ TRIGGERS POSTGRESQL ACTIFS — NE PAS MODIFIER SANS CONFIRMATION

5 triggers vivants en base PostgreSQL :
1. trigger_activite_r → activite_r depuis SPLIT_PART(code_naf_r, '.', 1)
2. trg_rendement → score 0-100 (4 facteurs pondérés)
3. trg_franchise_tva → franchise_tva_prest (seuil 37500€)
4. trg_franchise_achrevente → franchise_tva_achrevente (seuil 85000€)
5. trg_arbitrage_remuneration → arbitrage_remuneration_dirigeant (seuil 42500€)

Avant de toucher une fonction trigger, ALWAYS :
- Inspecter le code actuel via /api/debug/<function>_function
- Vérifier que la modif ne casse pas un trigger existant
- Tester avec /api/debug/triggers après modif
- Forcer un recalcul global avec /api/migrate/force_recalc_<champ> si besoin

Endpoints d'installation (à relancer si trigger disparu) :
- /api/migrate/install_trigger_rendement
- /api/migrate/install_trigger_franchise_tva
- /api/migrate/install_trigger_franchise_achrevente
- /api/migrate/install_trigger_arbitrage_remuneration
- /api/migrate/fix_activite_trigger

## Mises à jour 07/05/2026 (session étapes 13)

### Triggers actifs (liste complète à jour — 7 triggers)
1. trigger_activite_r → activite_r depuis SPLIT_PART(code_naf_r, '.', 1)
2. trg_rendement → score 0-100 (4 facteurs pondérés + plafond progressif)
3. trg_franchise_tva → franchise_tva_prest (seuil 37 500€, achat_revente=non)
4. trg_franchise_achrevente → franchise_tva_achrevente (seuil 85 000€, achat_revente=oui)
5. trg_arbitrage_remuneration → arbitrage_remuneration_dirigeant (seuil 42 500€)
6. trg_op_prevoyance → op_prevoyance (EI/SARL + prevoyance=non)
7. trg_mission_placement → mission_placement (ratio tréso/CA, seuil CA 50k)

### Nouveaux champs calculés

#### arbitrage_remuneration_dirigeant (TEXT)
- OUI si resultat_r > 42 500
- 'Donnée manquante' si resultat_r IS NULL
- NULL sinon
- Sources : resultat_r
- Endpoints : /api/migrate/arbitrage_remuneration_setup
             /api/migrate/install_trigger_arbitrage_remuneration

#### op_prevoyance (TEXT)
- OUI si prevoyance='non' ET structure IN ('EI','SARL')
- 'Donnée manquante' si prevoyance ou structure IS NULL
- NULL sinon
- Sources : prevoyance, structure
- Endpoints : /api/migrate/op_prevoyance_setup
             /api/migrate/install_trigger_op_prevoyance

#### franchise_tva_achrevente (TEXT)
- OUI si achat_revente='oui' ET ca_r BETWEEN 0 AND 85000
- 'Données manquantes' si ca_r ou achat_revente IS NULL
- NULL sinon
- Sources : ca_r, achat_revente
- Endpoints : /api/migrate/franchise_tva_achrevente_setup
             /api/migrate/install_trigger_franchise_achrevente

#### mission_placement (TEXT — champ existant réutilisé)
- 'OPPORTUNITÉ FORTE' si ca_r>50k ET tresorerie_r>50k ET ratio>25%
- 'OPPORTUNITÉ MOYENNE' si ca_r>50k ET tresorerie_r>20k ET ratio>15%
- 'Données manquantes' si ca_r ou tresorerie_r IS NULL
- NULL sinon
- Ratio = tresorerie_r * 100.0 / ca_r
- Sources : ca_r, tresorerie_r
- Endpoints : /api/migrate/mission_placement_setup
             /api/migrate/install_trigger_mission_placement
- ⚠️ Champ ancien mission_placement écrasé (ancienne valeur = texte libre)

### Convention globale champs calculés (à respecter pour tous les futurs triggers)
- OUI → condition remplie
- 'Données manquantes' → au moins un champ source IS NULL
- NULL (vide) → condition non remplie (JAMAIS 'NON')
- Pas de valeur booléenne stockée, toujours TEXT

### Seuils officiels TVA 2025 (à ne pas modifier sans confirmation)
- Prestataires de services : 37 500 €
- Achat-revente : 85 000 €
- Arbitrage rémunération dirigeant : 42 500 €
- Mission placement TPE — seuil CA minimum : 50 000 €

### Endpoint de vérification rapide
- GET /api/debug/triggers → liste tous les triggers actifs
- Doit toujours retourner 7 triggers minimum
- Si un trigger manque → relancer /api/migrate/install_trigger_<nom>
- Vérifier le code source d'une fonction :
  SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname='nom_fonction'

### ⚠️ À FAIRE (prochaine session)
- Créer endpoint /api/migrate/install_all_triggers (réinstalle les 7 en 1 clic)
- Créer endpoint /api/debug/health (vérifie présence des 7 triggers)
- Affichage badges colorés franchise_tva sur declaratif.html
- Mettre à jour CLAUDE.md après chaque nouveau trigger

## Convention triggers PostgreSQL en cascade

Quand un trigger calcule un champ (B) à partir d'un autre champ
calculé par un trigger (A), il faut lister TOUTES les colonnes
sources dans `UPDATE OF`, pas seulement le champ intermédiaire.

❌ Ne marche pas :
  CREATE TRIGGER trg_B BEFORE UPDATE OF champ_a ON clients ...

✅ Correct :
  CREATE TRIGGER trg_B BEFORE UPDATE OF champ_a, source_reelle ON clients ...

Raison : PostgreSQL évalue `UPDATE OF` sur les colonnes du SET
original, pas sur celles modifiées par d'autres triggers BEFORE.

Exemple concret : trg_mission_retraite dépend de age, calculé par
trg_age depuis anniversaire. Le trigger doit écouter age ET anniversaire.

## Champs calculés en cascade actuels (chaîne anniversaire)
- anniversaire (saisie) → trg_age → age (INTEGER)
- age + anniversaire → trg_mission_retraite → mission_retraite (TEXT)

## Pattern standard nouveau champ calculé
1. Endpoint /api/migrate/{champ}_setup → ALTER TABLE + premier UPDATE
2. Endpoint /api/migrate/install_trigger_{champ} → DROP IF EXISTS + CREATE
3. Endpoint /api/migrate/refresh_{champ} (optionnel) → recalcul forcé
4. Lancer dans le navigateur dans cet ordre : setup → install_trigger
5. Vérifier via /api/debug/triggers

## Formulaires gestion-clients.html — Architecture

### Structure des champs
Les champs du formulaire sont répartis en 3 listes dans le JS :
- `TEXT_FIELDS` : inputs texte, selects, textareas → collectForm() lit .value
- `TOGGLE_FIELDS` : checkboxes booléennes → collectForm() lit .checked (true/false)
- `DATE_FIELDS` : inputs date → collectForm() lit .value (format ISO)

### Règle critique — Noms des champs
Le nom/id HTML doit correspondre EXACTEMENT au nom de la colonne PostgreSQL.
Préfixe `c-` pour le formulaire Créer, `m-` pour Modifier.
Exemple : colonne `cotisation_fonciere_entreprise` → id `c-cotisation_fonciere_entreprise`

❌ Erreur classique : `cotisation_fonciere_des_entreprises` ≠ `cotisation_fonciere_entreprise`
→ La valeur est envoyée dans le payload mais PostgreSQL ignore la colonne inconnue
→ Aucune erreur visible, la donnée est silencieusement perdue

### Ajouter un nouveau champ dans les 2 formulaires
1. ALTER TABLE clients ADD COLUMN IF NOT EXISTS {champ} TYPE → /api/migrate/champs_setup
2. Ajouter le champ HTML dans le formulaire Créer (id: c-{champ})
3. Ajouter le champ HTML dans le formulaire Modifier (id: m-{champ})
4. Ajouter le nom dans TEXT_FIELDS (ou TOGGLE_FIELDS si booléen)
5. Vérifier que fillModifyForm pré-remplit bien le champ au chargement
6. Hard refresh navigateur après déploiement (Ctrl+Shift+R)

### Champs calculés — ne pas les mettre dans les formulaires
Les champs suivants sont calculés automatiquement par trigger PostgreSQL,
ne jamais les exposer en saisie manuelle :
age, anciennete, rendement, activite_r, mission_retraite,
franchise_tva_prest, franchise_tva_achrevente,
arbitrage_remuneration_dirigeant, op_prevoyance, mission_placement

### Erreur addEventListener null (ligne ~1952)
Si erreur "Cannot read properties of null (reading 'addEventListener')" :
→ Un élément est référencé en JS avant d'exister dans le DOM
→ Fix : ajouter `if (el)` avant chaque addEventListener sur des éléments dynamiques
→ Hard refresh souvent suffisant si lié au cache

## Règles formulaires gestion-clients.html — pièges courants

### Mismatch nom de champ (erreur silencieuse la plus fréquente)
Le payload est envoyé mais PostgreSQL ignore la colonne inconnue
sans retourner d'erreur. Toujours vérifier :
- TOGGLE_FIELDS : id doit être le nom exact de la colonne PostgreSQL
- TEXT_FIELDS : idem
- Exemple piège : "juridique_exceptionnel" ≠ "juridique"
- Exemple piège : "cotisation_fonciere_des_entreprises" ≠ "cotisation_fonciere_entreprise"
- Exemple piège : "resultat" ≠ "resultat_r"

### Champs FEC (_r) vs saisie manuelle
- Suffixe _r = alimenté par FEC parser → NE PAS mettre dans les formulaires
- Exception : mai_ir (suffixe _r mais = échéance fiscale, saisie manuelle)
- Toujours vérifier la nature du champ avant de l'ajouter au formulaire

### Deux champs "juridique" distincts
- `juridique` (BOOLEAN) → toggle dans gestion-clients.html
- `juridique_exceptionnel` (TEXT) → saisie dans missions.html uniquement
- Ne jamais les confondre dans TOGGLE_FIELDS

## Page opportunites.html — architecture indicateurs

### Cases à cocher lecture seule
Toutes les cases indicateurs sont disabled + pointer-events:none.
Ne jamais les rendre cliquables — elles reflètent des triggers PostgreSQL.

### Conditions exactes par indicateur
- mission_retraite = 'OUI' → age > 50 AND age < 65
- mission_patrimoniale = 'OUI' → mai_ir > 8000
- mission_placement = 'OPPORTUNITÉ FORTE' ou 'OPPORTUNITÉ MOYENNE'
- franchise_tva_prest = 'OUI' → ca_r < 37500 AND achat_revente = 'non'
- franchise_tva_achrevente = 'OUI' → ca_r < 85000 AND achat_revente = 'oui'
- op_prevoyance = 'OUI' → prevoyance = 'non' AND structure IN ('EI','SARL')
- arbitrage_remuneration_dirigeant = 'OUI' → resultat_r > 42500

## Modal détail client (index.html) — conventions affichage
- Masquer les champs NULL, vides ou à 0
- Booléens : true/t → "Oui", false/f → "Non"
- Dates ISO → format JJ/MM/YYYY
- Commentaires : pleine largeur en bas de modal
- Champs renseignés uniquement → modal épurée

## Triggers actifs (10 au total) — mai 2026
1. trigger_activite_r (sur code_naf_r)
2. trg_rendement (sur honoraires_cpta, temps_passe, ca_r, resultat_r, anciennete)
3. trg_franchise_tva (sur ca_r, achat_revente)
4. trg_franchise_achrevente (sur ca_r, achat_revente)
5. trg_arbitrage_remuneration (sur resultat_r)
6. trg_op_prevoyance (sur prevoyance, structure)
7. trg_mission_placement (sur ca_r, tresorerie_r)
8. trg_age (sur anniversaire)
9. trg_mission_retraite (sur age, anniversaire)
10. trg_mission_patrimoniale (sur mai_ir)

## Trigger anciennete — historique

anciennete était le seul champ calculé sans trigger PostgreSQL
(recalcul au démarrage app uniquement via thread daemon).
Désormais aligné sur le pattern standard via trg_anciennete.

Si anciennete ne se met pas à jour → vérifier /api/debug/triggers
que trg_anciennete est bien présent.

## Règles dates JavaScript — CRITIQUES

### Parsing de dates ISO PostgreSQL (yyyy-mm-dd)
❌ INTERDIT : new Date("1970-05-15") → parse en UTC → décalage en heure locale
✅ CORRECT :
  const [a, m, j] = "1970-05-15".split('-').map(Number)
  const d = new Date(a, m-1, j) // heure locale, pas de décalage

### FullCalendar — propriété start/date
❌ INTERDIT : { start: "1970-05-15" } → FullCalendar interprète en UTC
✅ CORRECT  : { start: "1970-05-15T00:00:00" } → interprétation locale

### Règle générale
Toute string "YYYY-MM-DD" passée à new Date() ou à FullCalendar
sera interprétée en UTC minuit → affichée la veille en UTC+2.
Toujours ajouter T00:00:00 ou parser manuellement.

## Triggers actifs (11 au total) — mai 2026
1. trigger_activite_r (sur code_naf_r)
2. trg_rendement (sur honoraires_cpta, temps_passe, ca_r, resultat_r, anciennete)
3. trg_franchise_tva (sur ca_r, achat_revente)
4. trg_franchise_achrevente (sur ca_r, achat_revente)
5. trg_arbitrage_remuneration (sur resultat_r)
6. trg_op_prevoyance (sur prevoyance, structure)
7. trg_mission_placement (sur ca_r, tresorerie_r)
8. trg_age (sur anniversaire)
9. trg_mission_retraite (sur age, anniversaire)
10. trg_mission_patrimoniale (sur mai_ir)
11. trg_anciennete (sur date_entree)

## Calendrier intelligent (anniversaires.html)

### Endpoint backend
GET /api/calendrier/fiscal retourne pour chaque client :
siret, nom_client, date_de_cloture, is, cvae, tvs, ca12,
liasse, dividendes, ca_r

### Parsing date_de_cloture
Format PostgreSQL = YYYY-MM-DD → parser avec split('-') :
  const parts = c.date_de_cloture.split('-')
  const moisClo = parseInt(parts[1])  // 1-12
  const jourClo = parseInt(parts[2])

### Règles fiscales par type

Liasse fiscale (is=true ou liasse=true) :
  clôture 31/12 → 20 mai (EDI +15j)
  autre → dernier jour du (moisClo+3)e mois + 15j
  couleur #e74c3c

IS acomptes (is=true) :
  TOUJOURS 4 dates fixes : 16 mars, 15 juin, 15 sept, 15 déc
  Indépendant de la clôture. Note : 16 mars en 2026 (15=dimanche)
  couleur #e67e22

Solde IS (is=true) :
  clôture 31/12 → 15 mai
  règle générale → 15 du 4e mois après clôture
  couleur #e67e22

CVAE (cvae=true) :
  Solde 5 mai → tous
  Acomptes 15 juin + 15 sept → si ca_r > 500000 ou ca_r null
  couleur #9b59b6

CA12 (ca12=true) :
  clôture 31/12 → 5 mai (PAS de +15j contrairement à liasse)
  autre → dernier jour du 3e mois après clôture (CA12E)
  couleur #27ae60

TVS (tvs=true) :
  ca12=true → même date que CA12 du client
  ca12=false → 27 janvier N+1
  couleur #3498db

2561 / IFU (dividendes > 1) :
  16 février, 1 événement par client
  couleur #f39c12

DAS2 : 5 mai (sans nom client)
DECLOYER : 20 mai (sans nom client)

### Différence clé CA12 vs Liasse
- Liasse : +15 jours pour télédéclaration → 20 mai (31/12)
- CA12 : PAS de +15 jours → 5 mai (31/12)
- Pour exercices décalés :
  Liasse : 3 mois + 15j après clôture
  CA12 : 3 mois exactement après clôture (pas de bonus)

### Dates FullCalendar — règle anti-décalage UTC
Toujours passer "YYYY-MM-DDT00:00:00" (jamais "YYYY-MM-DD")
Toujours parser avec split('-').map(Number) (jamais new Date(string))

## Navigation inter-pages — passage de paramètres URL

### Pattern standard lien vers fiche client
Toutes les pages qui affichent un client cliquable pointent vers :
  client.html?siret=SIRET_CLIENT

### Pattern standard lien vers modification client
Depuis n'importe quelle page, pour ouvrir le formulaire
de modification pré-rempli d'un client :
  gestion-clients.html?siret=SIRET_CLIENT&action=modifier

### Lecture des paramètres URL (pattern standard)
  const params = new URLSearchParams(location.search)
  const siret = params.get('siret')
  const action = params.get('action')

### Comportement gestion-clients.html au chargement
Si action=modifier ET siret présent dans l'URL :
  1. Activer l'onglet Modifier automatiquement
  2. Remplir le champ siret avec la valeur
  3. Appeler la fonction de chargement client directement
  4. Formulaire pré-rempli sans action manuelle de l'utilisateur

### Pages qui utilisent ce pattern
- client.html → bouton "Modifier" → gestion-clients.html?siret=X&action=modifier
- client.html → bouton "Créer client" → gestion-clients.html (sans paramètre)
- Toute future page peut utiliser ce même pattern pour
  rediriger vers la modification d'un client spécifique

### Règle générale
Ne jamais hardcoder un siret dans un lien.
Toujours le récupérer dynamiquement depuis :
- L'URL courante (URLSearchParams)
- Les données chargées depuis l'API (c.siret ou data.siret)

Ajoute à la fin de CLAUDE.md ce bloc exact sans rien modifier 
d'autre, puis commit push :

## Sécurité API — Endpoints protégés (ajouté 11/05/2026)

Les endpoints /api/migrate/* et /api/debug/* sont protégés
par un middleware Bearer token. Sans token → 401 automatique.

### Pour appeler un endpoint migrate ou debug

PowerShell :
$h = @{Authorization="Bearer $env:ADMIN_TOKEN"}
Invoke-RestMethod -Uri "https://projet-crm-m0o3.onrender.com/api/migrate/XXX" -Headers $h

Curl :
curl -H "Authorization: Bearer $env:ADMIN_TOKEN" https://projet-crm-m0o3.onrender.com/api/migrate/XXX

### Token
Stocké dans variable d'environnement locale ADMIN_TOKEN.
Fichier .env local (jamais committer) :
ADMIN_TOKEN=CRM-Hofman-2026-Lorient!

### Pour Claude Code
Lire ADMIN_TOKEN depuis .env avant d'appeler un endpoint migrate.
Exemple prompt : "Appelle /api/migrate/XXX avec le token du .env"

### Endpoints publics (pas de token)
/api/clients, /api/client/*, /api/fec/upload,
/api/calendrier/*, /api/rendement_detail/*
→ jamais de token requis, le CRM fonctionne normalement.

### Nouveaux endpoints migrate → automatiquement protégés
Le middleware est global, aucune modification nécessaire.

Ajoute à la fin de CLAUDE.md ce bloc exact, commit push :

## Authentification CRM (ajouté 11/05/2026)

### Endpoints auth (publics, hors middleware ADMIN_TOKEN)
- POST /api/auth/login → {password} → {token JWT 1h, expiry}
- GET /api/auth/verify → header Authorization: Bearer → {valid, expires_in}

### Sécurité login
- 5 tentatives max par IP → blocage 15 min → HTTP 429
- Compteur affiché : "X tentatives restantes"
- Reset automatique si login réussi

### Token JWT
- Durée : 1h
- Stocké en sessionStorage sous clé "crm_token"
- Signé avec JWT_SECRET (variable d'env Render)

### Timeout inactivité (auth.js)
- Déconnexion auto après 60 min sans action
- Événements écoutés : mousemove, keydown, click, scroll (passive)
- Warning à 55 min : bannière orange slide depuis le bas
- Décompte 5:00 → 1:01 : bannière orange #e67e22
- Décompte 1:00 → 0:00 : bannière rouge #e74c3c
- Bouton "Rester connecté" : reset timers + ferme bannière
- À 60 min : logout() automatique

### Variables d'environnement Render (3 au total)
- ADMIN_TOKEN → protège /api/migrate/* et /api/debug/*
- CRM_PASSWORD → mot de passe unique CRM collaborateurs
- JWT_SECRET → clé signature JWT
⚠️ Toutes dans .env local (jamais committer)

### Fichiers auth
- static/login.html : page de connexion
- static/auth.js : checkAuth(), logout(), inactivité, bannière
- Injectés dans tous les HTML sauf login.html

### Règle importante
Ne jamais protéger /api/auth/* avec le middleware ADMIN_TOKEN
→ le login doit rester accessible pour obtenir un token

## Calendrier intelligent — architecture événements groupés

### Principe de groupement
Au lieu de N événements identiques (un par client),
computeFiscalEvents() alimente une Map dont la clé est "label|dateStr".
Tous les clients qui tombent le même jour pour le même type sont agrégés.
Titre affiché : "📋 Liasse (3)", "💰 Solde IS (7)", etc.

Exceptions NON groupées : anniversaires, DAS2, DECLOYER

### Structure extendedProps
Chaque événement groupé porte :
  extendedProps.clients = [{nom, siret}, ...] // liste des clients

### Modal au clic (eventClick)
Si event.extendedProps.clients est non vide → showClientsModal()
Affiche la liste des clients avec fond alterné
Fermeture via ✕ ou clic overlay

### Filtres collaborateur / assistant
- allClients chargé une seule fois au démarrage
- refreshCalendar() filtre allClients en mémoire (pas de fetch)
- Filtres combinables (collab ET assistant simultanément)
- Badge "N clients" visible si filtre actif
- Anniversaires filtrés aussi selon le portefeuille

### Règle importante
Ne JAMAIS recréer l'instance FullCalendar pour rafraîchir.
Toujours utiliser :
  calendarInst.removeAllEvents()
  calendarInst.addEvent(event)
pour mettre à jour sans recréer l'instance.

### Champs utilisés pour les filtres
- collaborateur (TEXT) → filtre portefeuille collaborateur
- assistant (TEXT) → filtre portefeuille assistant
Les valeurs sont extraites dynamiquement depuis allClients
(valeurs uniques non-vides, triées alphabétiquement)

## Règle absolue — Stockage des données
Toutes les données métier sont stockées en PostgreSQL.
JAMAIS de localStorage, sessionStorage, ou variables JS globales
pour persister des données entre sessions.
Tout nouveau champ = ALTER TABLE ADD COLUMN en base.

## Pattern tableau large avec scroll (tvs.html, ca12.html)
Structure HTML :
  <div style="height: calc(100vh - 280px); overflow-y: auto; overflow-x: scroll;">
    <div class="table-scroll">
      <table>
        <thead> <!-- sticky top:0 z-index:10 bg:#1e3a5f -->
        <tbody>
      </table>
    </div>
  </div>

Règles :
- Un seul wrapper gère les deux scrolls (vertical + horizontal)
- thead sticky top:0 → header figé pendant scroll vertical
- Barre horizontale native toujours visible en bas du wrapper
- Pas de barre miroir JS (trop fragile)
- Ajuster la hauteur calc(100vh - Npx) selon hauteur des filtres

## Logique grisage colonnes mensuelles (TVS + CA12 solde)
Pour chaque client, calculer mois_actif :
  const parts = date_de_cloture.split('-')  // format YYYY-MM-DD
  const moisClo = parseInt(parts[1])  // 1-12

  Si ca12=false → mois_actif = 1 (janvier) pour TVS
  Si ca12=true :
    Si moisClo === 12 → mois_actif = 5 (mai, exception)
    Sinon → mois_actif = moisClo + 3
            si mois_actif > 12 → mois_actif -= 12

Input actif (blanc) uniquement pour mois_actif
11 autres inputs : disabled + background: #f0f0f0

Tableau correspondance clôture → mois actif :
  31/01 → avril | 28/02 → mai | 31/03 → juin
  30/04 → juillet | 31/05 → août | 30/06 → septembre
  31/07 → octobre | 31/08 → novembre | 30/09 → décembre
  31/10 → janvier | 30/11 → février | 31/12 → mai (exception)

## Endpoints migrate — token admin
Tous les /api/migrate/* sont exemptés du token admin via _MIGRATE_PUBLIC.
Pattern dans main.py :
  if request.url.path.startswith("/api/migrate/"):
      pass  # bypass token
Ne jamais protéger un endpoint de migration par token.
## Colonnes TVS en base (12 champs NUMERIC)
janvier_tvs, fevrier_tvs, mars_tvs, avril_tvs, mai_tvs, juin_tvs,
juillet_tvs, aout_tvs, septembre_tvs, octobre_tvs, novembre_tvs, decembre_tvs

## Colonnes CA12 en base
Soldes (12 champs NUMERIC) : janvier_ca12_solde → decembre_ca12_solde
Acomptes (2 champs) : juillet_ca12, decembre_ca12
mai_ca12 : SUPPRIMÉ

## Import CSV — Architecture et règles définitives

### Endpoint POST /api/clients/import
Réécrit entièrement en mai 2026. Ne jamais revenir à l'ancienne version.

### Principe fondamental
col_types est rechargé depuis PostgreSQL à CHAQUE appel :
  SELECT column_name, data_type FROM information_schema.columns
  WHERE table_name = 'clients'
JAMAIS en cache global au boot — sinon les nouvelles colonnes
créées via /api/migrate/* ne sont pas reconnues.

### Conversions obligatoires avant upsert

**Valeur vide :**
  if val == "" → val = None → NULL en base

**Booléens (type 'boolean') :**
  oui/true/1/yes → True
  non/false/0/no → False
  autre → None

**Dates (type 'date') format DD/MM/YYYY :**
  if '/' in val:
    parts = val.split('/')
    val = f"{parts[2]}-{parts[1]}-{parts[0]}"
  Format YYYY-MM-DD déjà correct → inchangé

**Valeur "0" numérique :**
  float("0") = 0.0 → inclus dans l'upsert (pas ignoré)

### Structure upsert
  INSERT INTO clients ("siret", "col1", "col2"...)
  VALUES (%s, %s, %s...)
  ON CONFLICT (siret) DO UPDATE SET
  "col1"=EXCLUDED."col1", "col2"=EXCLUDED."col2"...
  conn.commit() après chaque ligne

### Ce qui est ignoré silencieusement
- Colonnes du CSV absentes de col_types (ex: colonnes inconnues)
- Colonne "siret" (clé, pas dans SET)

### Historique du bug (pour mémoire)
Le bug persistait à cause de 4 problèmes cumulés :
1. col_types chargé au boot → nouvelles colonnes ignorées
2. Sentinelle _SKIP mal gérée → valeurs vides non écrites
3. "oui"/"non" non convertis → erreur PostgreSQL boolean
4. "31/12/2026" non converti → erreur PostgreSQL date
Solution : réécriture complète sans cache ni sentinelle.
lonnes déclaratives (mai 2026)
TVS : janvier_tvs → decembre_tvs (12 NUMERIC)
CA12 soldes : janvier_ca12_solde → decembre_ca12_solde (12 NUMERIC)
CA12 acomptes : juillet_ca12, decembre_ca12
CVAE : mai_cvae, acompte_cvae_juin, acompte_cvae_septembre
mai_ca12 : SUPPRIMÉ
## Règle seuil CVAE
ca_r > 500000 (strictement) → colonnes actives
ca_r <= 500000 → disabled + grisé
ca_r null → actif (par sécurité)