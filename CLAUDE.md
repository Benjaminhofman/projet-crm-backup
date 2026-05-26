# CRM Collaborateurs Comptables

## Présentation du projet
Application CRM destinée aux collaborateurs comptables pour piloter
un portefeuille client. L'objectif prioritaire est une UX/UI excellente :
fluide, intuitive et moderne.

Intégrations :
- **Make (Integromat)** : automatisation de workflows (en cours)

---

## Règles de comportement
- Toujours répondre et commenter en **français**
- Ne jamais demander de confirmation avant de modifier, créer ou supprimer un fichier
- Ne jamais demander de permission avant d'exécuter une commande
- Travailler de manière autonome et aller jusqu'au bout des tâches
- Après chaque tâche terminée, proposer 2 ou 3 améliorations ou nouvelles
  fonctionnalités pertinentes en lien avec le code modifié

## Priorités de développement
- **UX/UI en premier** : chaque fonctionnalité doit être fluide, responsive
  et agréable à utiliser
- Privilégier les animations subtiles et les transitions douces
- Penser à l'ergonomie pour un usage quotidien intensif (collaborateurs comptables)
- Optimiser les performances (chargements rapides, pas de blocage UI)

## Standards de code
- Code propre, lisible et bien commenté en français
- Composants réutilisables et modulaires
- Toujours gérer les états de chargement et les erreurs
- Penser à l'expérience mobile si pertinent

## Style des prompts pour Claude Code
- Toujours en français
- Maximum 5-6 lignes par prompt
- Découper en mini-blocs si plus long
- Pas de demande de confirmation avant de coder

## Workflow git
Après chaque modification de code, faire automatiquement :
1. `git add .`
2. `git commit -m "message descriptif en français"`
3. `git push origin main`

Les messages de commit doivent décrire clairement ce qui a été modifié.
Ne jamais demander de confirmation avant de push.

## Ce qu'il ne faut pas toucher
- Les fichiers de configuration d'environnement (`.env`)
- Les clés API et tokens d'authentification

## Mise à jour de ce fichier
À la fin de chaque session de travail, mettre à jour la section
« État du projet » et « Prochaines étapes » avec ce qui a été
accompli et ce qui reste à faire.

---

## Stack technique
- Frontend : HTML/JS vanilla (`static/` servi par FastAPI)
- Backend : FastAPI Python (`fec-explorer/app/main.py`)
- Base de données : PostgreSQL (Render, Basic-256mb, Frankfurt EU)
- Hébergement : Render (Web Service + PostgreSQL)
- Versioning : GitHub — https://github.com/Benjaminhofman/projet-crm
- URL production : https://projet-crm-m0o3.onrender.com
- `DATABASE_URL` depuis variable d'environnement

## Architecture des fichiers
- `fec-explorer/app/main.py` : API FastAPI (tous les endpoints)
- `fec-explorer/static/` : tous les fichiers HTML/JS servis
- `fec-explorer/app/core/fec_parser.py` : parsing des fichiers FEC
- `fec-explorer/app/core/indicators.py` : calcul des 61+ indicateurs
- `fec-explorer/app/core/postgres_sync.py` : sync FEC → PostgreSQL
- `fec-explorer/import_csv.py` : import CSV → PostgreSQL
- `fec-explorer/sync_html.py` : synchronise HTML racine → `static/`

## Workflow de modification standard
1. Modifications côté Python → commit → push → Render redéploie en 1-2 min
2. Modifications de schéma BDD → toujours via un endpoint `/api/migrate/...`
   appelé une fois dans le navigateur (pas de migrations locales)
3. Modifications côté `static/` → `sync_html.py` si édité hors `static/`,
   sinon commit direct
4. Hard refresh (Ctrl+Shift+R) après push pour bypasser le cache Render

---

## Base de données PostgreSQL

### Table principale `clients` (135 colonnes)
- Clé primaire : `siret` (exactement 9 chiffres)
- Colonnes `_r` : alimentées par le FEC Explorer
- Colonnes sans `_r` : saisies manuellement via le CRM
- UPSERT sur `siret`

### Conventions de nommage
- Colonnes BDD : snake_case minuscule strict, jamais d'espaces
- Champs alimentés par FEC : suffixe `_r` (`ca_r`, `resultat_r`, `activite_r`…)
- Champs métier saisis manuellement : sans suffixe
- Exception : `mai_ir` n'a pas le suffixe `_r` mais reste une saisie manuelle
  (échéance fiscale IR de mai, type NUMERIC)

### Table NAF
- Table `naf` (`code` TEXT, `libelle` TEXT)
- Importée via `GET /api/migrate/naf` (88 codes hardcodés dans `main.py`)
- Trigger `trigger_activite_r` : remplit `activite_r` automatiquement
  quand `code_naf_r` change

### Colonnes TEXT à ne pas confondre avec NUMERIC
Ces colonnes stockent du texte (ex : « détecté », « en cours ») mais
ont été créées en NUMERIC dans le schéma initial :
`suivi_mission_retraite`, `suivi_mission_patrimoniale`,
`suivi_mission_placement`, `suivi_mission_prevoyance`.

Si erreur `invalid input syntax for type numeric` :
```sql
ALTER TABLE clients ALTER COLUMN suivi_mission_retraite TYPE TEXT;
```
(idem pour les 3 autres)

### Règle absolue — Stockage des données
Toutes les données métier sont stockées en PostgreSQL.
JAMAIS de `localStorage`, `sessionStorage` ou variables JS globales
pour persister des données entre sessions. `localStorage`/`sessionStorage`
sont de toute façon interdits dans Render.
Tout nouveau champ = `ALTER TABLE ADD COLUMN` en base.

---

## Endpoints API principaux (publics)
- `GET /api/clients` → liste tous les clients
- `GET /api/client/{siret}` → détail d'un client
- `POST /api/client/create` → créer un client
- `POST /api/client/update` → modifier un client
- `PATCH /api/client/{siret}` → mettre à jour un ou plusieurs champs
- `DELETE /api/client/{siret}` → supprimer un client
- `POST /api/clients/import` → import CSV en masse (UPSERT)
- `GET /api/clients/columns` → types des colonnes PostgreSQL
- `GET /api/clients/template-csv` → CSV vide avec en-têtes
- `POST /api/fec/upload` → parse FEC + sync PostgreSQL
- `GET /api/calendrier/fiscal` → données pour le calendrier intelligent
- `GET /api/rendement_detail/{siret}` → détail JSON pour la modal rendement

### Migration Airtable → PostgreSQL (terminée)
Airtable est totalement abandonné. AUCUN appel à `/api/update-airtable`
ne doit subsister. Pattern correct pour toute sauvegarde :
```
PATCH /api/client/{siret}
Body : {champ: valeur}
```
Si `/api/update-airtable` est trouvé dans un fichier → remplacer
immédiatement sans toucher au reste du code.
Ne plus jamais utiliser `AIRTABLE_TOKEN`, `BASE_ID` ou `TABLE_NAME`.

---

## Sécurité et authentification

### Variables d'environnement Render (3 au total)
- `ADMIN_TOKEN` → protège `/api/migrate/*` et `/api/debug/*`
- `CRM_PASSWORD` → mot de passe unique CRM pour tous les collaborateurs
- `JWT_SECRET` → clé de signature JWT

⚠️ Ces 3 variables sont définies dans `.env` local et dans les variables
d'environnement Render. Ne JAMAIS committer leurs valeurs, ni dans `.env`,
ni dans ce fichier, ni dans aucun fichier versionné.

> NOTE DE COHÉRENCE À TRANCHER : deux affirmations contradictoires existaient
> dans l'ancien fichier. Soit `/api/migrate/*` est protégé par le middleware
> `ADMIN_TOKEN`, soit il est exempté via `_MIGRATE_PUBLIC`. Vérifier le code
> réel de `main.py` et corriger cette section en conséquence. Tant que ce
> n'est pas tranché, considérer que `/api/migrate/*` peut être public.

### Endpoints protégés par Bearer token
`/api/migrate/*` et `/api/debug/*` — middleware global.
Header requis : `Authorization: Bearer <ADMIN_TOKEN>`.
Pour Claude Code : lire `ADMIN_TOKEN` depuis `.env` avant d'appeler
un endpoint migrate ou debug.

PowerShell :
```powershell
$h = @{Authorization="Bearer $env:ADMIN_TOKEN"}
Invoke-RestMethod -Uri "https://projet-crm-m0o3.onrender.com/api/migrate/XXX" -Headers $h
```

### Authentification utilisateurs
- `POST /api/auth/login` → `{password}` → `{token JWT 1h, expiry}`
- `GET /api/auth/verify` → header `Authorization: Bearer` → `{valid, expires_in}`
- Protection brute force : 5 tentatives max par IP → blocage 15 min → HTTP 429,
  compteur « X tentatives restantes » affiché, reset si login réussi
- Token JWT : durée 1h, stocké en `sessionStorage` sous clé `crm_token`,
  signé avec `JWT_SECRET`
- Timeout inactivité (`auth.js`) : déconnexion auto après 60 min sans action.
  Événements écoutés en mode passive : `mousemove`, `keydown`, `click`, `scroll`.
  Bannière de warning à 55 min (slide depuis le bas) : orange `#e67e22` de
  5:00 à 1:01, rouge `#e74c3c` de 1:00 à 0:00. Bouton « Rester connecté »
  reset les timers et ferme la bannière. À 60 min : `logout()` automatique.

### Fichiers auth
- `static/login.html` : page de connexion (design CRM)
- `static/auth.js` : `checkAuth()`, `logout()`, gestion inactivité + bannière
- `auth.js` et le bouton Déconnexion injectés dans tous les HTML sauf `login.html`

### Règle importante
Ne jamais protéger `/api/auth/*` avec le middleware `ADMIN_TOKEN` :
le login doit rester accessible pour obtenir un token.

---

## Triggers PostgreSQL actifs (11 — état mai 2026)

| # | Trigger | Champ calculé | Colonnes sources |
|---|---------|---------------|------------------|
| 1 | `trigger_activite_r` | `activite_r` | `code_naf_r` |
| 2 | `trg_rendement` | `rendement` | `honoraires_cpta`, `temps_passe`, `ca_r`, `resultat_r`, `anciennete` |
| 3 | `trg_franchise_tva` | `franchise_tva_prest` | `ca_r`, `achat_revente` |
| 4 | `trg_franchise_achrevente` | `franchise_tva_achrevente` | `ca_r`, `achat_revente` |
| 5 | `trg_arbitrage_remuneration` | `arbitrage_remuneration_dirigeant` | `resultat_r` |
| 6 | `trg_op_prevoyance` | `op_prevoyance` | `prevoyance`, `structure` |
| 7 | `trg_mission_placement` | `mission_placement` | `ca_r`, `tresorerie_r` |
| 8 | `trg_age` | `age` | `anniversaire` |
| 9 | `trg_mission_retraite` | `mission_retraite` | `age`, `anniversaire` |
| 10 | `trg_mission_patrimoniale` | `mission_patrimoniale` | `mai_ir` |
| 11 | `trg_anciennete` | `anciennete` | `date_entree` |

Diagnostic : `GET /api/debug/triggers` (doit retourner ces 11 triggers).
Si un trigger manque → relancer `/api/migrate/install_trigger_<nom>`.

### Logique des champs calculés

| Champ | Condition `OUI` / valeur | Notes |
|-------|--------------------------|-------|
| `activite_r` | libellé NAF de `SPLIT_PART(code_naf_r, '.', 1)` | chiffres avant le point |
| `rendement` | score 0-100 pondéré | voir détail ci-dessous |
| `franchise_tva_prest` | `ca_r < 37500` ET `achat_revente='non'` | seuil officiel 2025 |
| `franchise_tva_achrevente` | `ca_r < 85000` ET `achat_revente='oui'` | seuil officiel 2025 |
| `arbitrage_remuneration_dirigeant` | `resultat_r > 42500` | |
| `op_prevoyance` | `prevoyance='non'` ET `structure IN ('EI','SARL')` | |
| `mission_placement` | `'OPPORTUNITÉ FORTE'` ou `'OPPORTUNITÉ MOYENNE'` | voir seuils ci-dessous |
| `age` | `EXTRACT(YEAR FROM AGE(NOW(), anniversaire))` | INTEGER |
| `mission_retraite` | `age > 50` ET `age < 65` (bornes exclusives) | |
| `mission_patrimoniale` | `mai_ir > 8000` | |
| `anciennete` | `EXTRACT(YEAR FROM AGE(NOW(), date_entree))` | INTEGER |

`mission_placement` : `'OPPORTUNITÉ FORTE'` si `ca_r > 50000` ET
`tresorerie_r > 50000` ET ratio tréso/CA > 25 % ; `'OPPORTUNITÉ MOYENNE'`
si `ca_r > 50000` ET `tresorerie_r > 20000` ET ratio > 15 %.

### Convention globale des champs calculés
- `OUI` → condition remplie
- `Données manquantes` → au moins un champ source est NULL
- `NULL` (vide) → condition non remplie — **jamais `NON`**
- Toujours stocké en TEXT, jamais en booléen

### Seuils officiels (à ne pas modifier sans confirmation)
- Franchise TVA prestataires de services : 37 500 €
- Franchise TVA achat-revente : 85 000 €
- Arbitrage rémunération dirigeant : 42 500 €
- Mission placement TPE — seuil CA minimum : 50 000 €

### Score `rendement` (Stratégie C)
4 facteurs pondérés : taux horaire 50 % / ancienneté 20 % / CA 15 % / résultat 15 %.
- Si `nb_facteurs_renseignés < 2` → score = NULL
- Sinon : `score = (pts obtenus / poids cumulé des facteurs renseignés) × 100`
- Plafond progressif : 2 facteurs → max 70, 3 facteurs → max 85, 4 facteurs → pas de plafond
- Deux fonctions PostgreSQL portent cette logique : `calc_rendement(siret)`
  (calcul depuis la BDD) et `update_rendement_trigger()` (calcul depuis `NEW.*`).
  **Toute modification de la formule doit être reportée dans LES DEUX**, sinon désynchro.

---

## Conventions pour les nouveaux champs calculés

### Pattern standard
1. `/api/migrate/{champ}_setup` → `ALTER TABLE` + premier `UPDATE` initial
2. `/api/migrate/install_trigger_{champ}` → `DROP IF EXISTS` + `CREATE` fonction et trigger
3. `/api/migrate/force_recalc_{champ}` (optionnel) → `UPDATE` direct contournant le trigger
4. `/api/debug/{champ}_function` (optionnel) → inspection du code source
5. Lancer dans le navigateur dans l'ordre : `setup` → `install_trigger`
6. Vérifier via `/api/debug/triggers`

### Triggers en cascade
Quand un trigger calcule un champ B à partir d'un champ A lui-même calculé
par un trigger, lister TOUTES les colonnes sources dans `UPDATE OF`, pas
seulement le champ intermédiaire :

```sql
-- ❌ Ne marche pas
CREATE TRIGGER trg_B BEFORE UPDATE OF champ_a ON clients ...
-- ✅ Correct
CREATE TRIGGER trg_B BEFORE UPDATE OF champ_a, source_reelle ON clients ...
```

Raison : PostgreSQL évalue `UPDATE OF` sur les colonnes du `SET` original,
pas sur celles modifiées par d'autres triggers `BEFORE`.
Exemple : `trg_mission_retraite` dépend de `age` (calculé par `trg_age`
depuis `anniversaire`) → il doit écouter `age` ET `anniversaire`.

### Limite connue — recalcul annuel
`age` et `anciennete` ne se mettent pas à jour automatiquement au passage
d'une nouvelle année. Workaround : appeler `/api/migrate/refresh_age` et
`/api/migrate/anciennete` périodiquement (cron Render quotidien recommandé).

---

## Méthodologie de débug d'un trigger

Quand un champ calculé donne un résultat bizarre :
1. **Vérifier que le trigger existe** : `GET /api/debug/triggers`
2. **Inspecter le code de la fonction** :
   `SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname='nom_fonction'`
3. **Vérifier les données sources** (table `naf`, colonnes utilisées)
4. **Tester en modifiant réellement la colonne source** dans l'UI
   (un `UPDATE x = x` ne déclenche rien — voir piège 1)
5. **Forcer un recalcul global** via `/api/migrate/force_recalc_<champ>`

### Pièges connus
1. **`UPDATE x = x` ne déclenche pas le trigger** : beaucoup de fonctions
   contiennent `IF NEW.X IS DISTINCT FROM OLD.X`. Pour forcer un recalcul
   après un fix, créer un endpoint avec un `UPDATE` direct contournant le trigger.
2. **`LEFT` vs `SPLIT_PART`** : `LEFT(code_naf_r, 1)` ne prend que le 1er
   caractère (« 5 » pour « 56.30Z »). Utiliser
   `SPLIT_PART(code_naf_r::text, '.', 1)` (« 56 »). Le `1` = numéro de partie,
   pas nombre de caractères.
3. **Double création silencieuse** : `CREATE OR REPLACE` écrase l'ancienne
   version sans avertir. Toujours vérifier le code source via `pg_get_functiondef`
   après un fix.
4. **Recréer un trigger** après modif de sa logique : faire `DROP` + `CREATE`,
   pas seulement `CREATE OR REPLACE`.

---

## Frontend — règles transverses

### Filtres booléens PostgreSQL — règle critique
PostgreSQL retourne les booléens sous plusieurs formes : `true`, `'t'`,
`'true'`, `1` — jamais uniquement `true`. Toujours utiliser :
```javascript
const isTruthy = v => v === true || v === 't' || v === 'true' || v === 1 || v === '1'
```
Jamais `c.is === true` seul. Pages concernées : `is.html`, `cfe.html`,
`tvs.html`, `cvae.html`, `ca12.html`, `ir.html`, et toute future page
avec un filtre booléen.

### Filtre des champs TEXT d'opportunité
Ne jamais utiliser `Boolean(c[champ])` sur un champ TEXT. Utiliser :
```javascript
const isActive = v => v === 'OUI'
  || v === 'OPPORTUNITÉ FORTE' || v === 'OPPORTUNITÉ MOYENNE'
```

### Règles dates JavaScript — CRITIQUES
`new Date("yyyy-mm-dd")` parse en UTC minuit → affiché la veille en UTC+2.
- ❌ `new Date("1970-05-15")` → INTERDIT
- ✅ `const [a,m,j] = "1970-05-15".split('-').map(Number); new Date(a, m-1, j)`
- ❌ FullCalendar `{ start: "1970-05-15" }` → INTERDIT
- ✅ FullCalendar `{ start: "1970-05-15T00:00:00" }` → interprétation locale

### Format date de clôture JJ/MM
`date_de_cloture` est stockée en `YYYY-MM-DD` mais affichée en `JJ/MM`
(sans année) dans tous les tableaux :
```javascript
${ (v => { if (!v) return ''; const p = v.split('-'); return p[2] + '/' + p[1]; })(c.date_de_cloture) }
```
Pages concernées : `declaratif.html`, `missions.html`, `ir.html`,
`rendement.html`, `is.html`, `opportunites.html`, `commercial.html`.

### `rentabilite` vs `rendement` — ne jamais confondre
- `rentabilite` : taux horaire calculé côté JS (`honoraires_cpta / temps_passe`)
- `rendement` : score 0-100 pondéré calculé par le trigger `trg_rendement` ;
  c'est CE champ qui s'affiche dans la colonne Rendement

---

## Formulaires `gestion-clients.html`

### Structure des champs (3 listes JS)
- `TEXT_FIELDS` : inputs texte, selects, textareas → `collectForm()` lit `.value`
- `TOGGLE_FIELDS` : checkboxes booléennes → `collectForm()` lit `.checked`
- `DATE_FIELDS` : inputs date → `collectForm()` lit `.value` (format ISO)

### Règle critique — Noms des champs
L'id HTML doit correspondre EXACTEMENT au nom de la colonne PostgreSQL.
Préfixe `c-` pour le formulaire Créer, `m-` pour Modifier.
Un mismatch ne lève aucune erreur : le payload est envoyé, PostgreSQL ignore
la colonne inconnue, **la donnée est silencieusement perdue**.
Pièges déjà rencontrés :
- `cotisation_fonciere_des_entreprises` ≠ `cotisation_fonciere_entreprise`
- `juridique` (BOOLEAN, toggle ici) ≠ `juridique_exceptionnel` (TEXT, `missions.html`)
- `resultat` ≠ `resultat_r`

### Ajouter un nouveau champ dans les 2 formulaires
1. `ALTER TABLE clients ADD COLUMN IF NOT EXISTS {champ} TYPE` via `/api/migrate/champs_setup`
2. Ajouter le champ HTML dans le formulaire Créer (`id: c-{champ}`)
3. Ajouter le champ HTML dans le formulaire Modifier (`id: m-{champ}`)
4. Ajouter le nom dans `TEXT_FIELDS` (ou `TOGGLE_FIELDS` si booléen)
5. Vérifier que `fillModifyForm` pré-remplit bien le champ au chargement
6. Hard refresh navigateur après déploiement

### Champs calculés — ne pas les exposer en saisie
Ne jamais mettre dans les formulaires : `age`, `anciennete`, `rendement`,
`activite_r`, `mission_retraite`, `mission_patrimoniale`, `mission_placement`,
`franchise_tva_prest`, `franchise_tva_achrevente`,
`arbitrage_remuneration_dirigeant`, `op_prevoyance`.

### Erreur `addEventListener null`
`Cannot read properties of null (reading 'addEventListener')` → un élément
est référencé avant d'exister dans le DOM. Fix : `if (el)` avant chaque
`addEventListener` sur des éléments dynamiques.

---

## Import CSV — `POST /api/clients/import`

### Principe fondamental
`col_types` est rechargé depuis PostgreSQL à CHAQUE appel :
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'clients'
```
JAMAIS en cache global au boot — sinon les nouvelles colonnes créées via
`/api/migrate/*` ne sont pas reconnues.

### Conversions obligatoires avant upsert
```python
# Valeur vide
if val == "": val = None
# Booléens (type 'boolean')
if col_types[col] == 'boolean':
    if val.lower() in ('oui', 'true', '1', 'yes'):  val = True
    elif val.lower() in ('non', 'false', '0', 'no'): val = False
    else: val = None
# Dates (type 'date') format DD/MM/YYYY
if 'date' in col_types[col] and '/' in val:
    parts = val.split('/')
    if len(parts) == 3: val = f"{parts[2]}-{parts[1]}-{parts[0]}"
# "0" numérique : float("0") = 0.0 → inclus dans l'upsert
```

### Structure upsert
```sql
INSERT INTO clients ("siret", "col1", "col2"...)
VALUES (%s, %s, %s...)
ON CONFLICT (siret) DO UPDATE SET
"col1"=EXCLUDED."col1", "col2"=EXCLUDED."col2"...
```
`conn.commit()` après chaque ligne. La colonne `siret` n'est pas dans le `SET`.
Les colonnes du CSV absentes de `col_types` sont ignorées silencieusement.

### Après un import CSV massif
Appeler `/api/migrate/activite` et `/api/migrate/anciennete` pour recalculer
les champs dérivés sur l'ensemble des clients.

---

## Import FEC — `POST /api/fec/upload`
- Accepte plusieurs fichiers simultanément
- SIRET extrait automatiquement du nom : `SIREN + FEC + DATE.txt`
- Chaîne : `fec_parser.py` → `indicators.py` → `postgres_sync.py` → UPSERT sur `siret`
- Réponse : `{results: [{siret, status, indicators_updated, message}]}`
  (`status` = `"ok"` ou `"error"`)
- Interface : onglet « Import FEC » dans `gestion-clients.html`, drag & drop
  multi-fichiers, actualisation auto de la liste clients après import réussi

### Calcul CAF — distinction 781x / 791x
- `781x` (reprises sur amortissements/provisions) → produit non décaissé → **neutraliser**
- `791x` (transferts de charges = remboursements assurance) → encaissement réel → **garder**

```python
c781 = vals["compte_781"]   # reprises amortissements → neutraliser
c791 = vals["compte_791"]   # transferts charges → garder
resultat = produits(7x hors 781,791) - charges(6x) + c781 + c791
caf = resultat + dotations_amortissements - c781
```
Ne jamais faire `caf = res + dotations - c791` (faux : neutralise les
remboursements d'assurance).

---

## Calendrier intelligent (`anciennement anniversaires.html`)

`GET /api/calendrier/fiscal` retourne pour chaque client : `siret`,
`nom_client`, `date_de_cloture`, `is`, `cvae`, `tvs`, `ca12`, `liasse`,
`dividendes`, `ca_r`.

### Règles fiscales par type d'événement

| Type | Condition | Date | Couleur |
|------|-----------|------|---------|
| Liasse fiscale | `is` ou `liasse` | clôture 31/12 → 20 mai ; sinon dernier jour du 3e mois + 15j | `#e74c3c` |
| IS acomptes | `is` | 4 dates fixes : 16 mars, 15 juin, 15 sept, 15 déc | `#e67e22` |
| Solde IS | `is` | clôture 31/12 → 15 mai ; sinon 15 du 4e mois après clôture | `#e67e22` |
| CVAE | `cvae` | solde 5 mai (tous) ; acomptes 15 juin + 15 sept si `ca_r > 500000` ou null | `#9b59b6` |
| CA12 | `ca12` | clôture 31/12 → 5 mai ; sinon dernier jour du 3e mois après clôture | `#27ae60` |
| TVS | `tvs` | `ca12=true` → même date que le CA12 du client ; `ca12=false` → 27 janvier N+1 | `#3498db` |
| 2561 / IFU | `dividendes > 1` | 16 février | `#f39c12` |
| DAS2 | — | 20 mai (sans nom client) | — |
| DECLOYER | — | 30 avril (sans nom client) | — |

Note : le 1er acompte IS 2026 est le 16 mars (15 mars = dimanche).

### Différence clé CA12 vs Liasse
- Liasse : +15 jours pour télédéclaration EDI → 20 mai (clôture 31/12)
- CA12 : pas de +15 jours → 5 mai (clôture 31/12)
- Exercices décalés : Liasse = 3 mois + 15j ; CA12 = 3 mois exactement

### Architecture événements groupés
Au lieu de N événements identiques, `computeFiscalEvents()` alimente une `Map`
de clé `"label|dateStr"`. Tous les clients d'un même type tombant le même jour
sont agrégés. Titre : « 📋 Liasse (3) », « 💰 Solde IS (7) »…
Exceptions non groupées : anniversaires, DAS2, DECLOYER.
Chaque événement groupé porte `extendedProps.clients = [{nom, siret}, ...]`.

### Modal au clic
`eventClick` : si `extendedProps.clients` non vide → `showClientsModal()`
(liste à fond alterné, fermeture par ✕ ou clic overlay).

### Filtres collaborateur / assistant
`allClients` chargé une seule fois au démarrage. `refreshCalendar()` filtre
en mémoire (pas de fetch). Filtres combinables, badge « N clients » si actif.
Ne JAMAIS recréer l'instance FullCalendar pour rafraîchir : utiliser
`calendarInst.removeAllEvents()` puis `calendarInst.addEvent(event)`.

---

## Tableaux larges avec scroll (`tvs.html`, `ca12.html`)

```html
<div style="height: calc(100vh - 280px); overflow-y: auto; overflow-x: scroll;">
  <div class="table-scroll">
    <table>
      <thead> <!-- sticky top:0 z-index:10 bg:#1e3a5f -->
      <tbody>
    </table>
  </div>
</div>
```
- Un seul wrapper gère les deux scrolls (vertical + horizontal)
- `thead` sticky → header figé pendant le scroll vertical
- Pas de barre miroir JS (trop fragile)
- Colonnes fixes (Code, Nom, Assistant, Collab, Année, Clôture) : `sticky left`

### Colonnes mensuelles déclaratives
- TVS (12 NUMERIC) : `janvier_tvs` → `decembre_tvs`
- CA12 soldes (12 NUMERIC) : `janvier_ca12_solde` → `decembre_ca12_solde`
- CA12 acomptes : `juillet_ca12`, `decembre_ca12`
- CVAE : `mai_cvae`, `acompte_cvae_juin`, `acompte_cvae_septembre`
- `mai_ca12` : SUPPRIMÉ

### Logique de grisage des colonnes mensuelles (TVS + CA12 solde)
```javascript
const moisClo = parseInt(date_de_cloture.split('-')[1])  // 1-12
// ca12=false → mois_actif = 1 (janvier) pour TVS
// ca12=true  → moisClo === 12 ? mois_actif = 5 (exception)
//                              : mois_actif = moisClo + 3 (−12 si > 12)
```
Input actif (blanc) uniquement pour `mois_actif` ; les 11 autres `disabled`
+ `background:#f0f0f0`.

Correspondance clôture → mois actif : 31/01 → avril, 28/02 → mai,
31/03 → juin, 30/04 → juillet, 31/05 → août, 30/06 → septembre,
31/07 → octobre, 31/08 → novembre, 30/09 → décembre, 31/10 → janvier,
30/11 → février, 31/12 → mai (exception).

### Règle seuil CVAE
- `ca_r > 500000` (strictement) → colonnes actives
- `ca_r <= 500000` → `disabled` + grisé
- `ca_r` null → actif (par sécurité)

---

## Page `opportunites.html`

### Cases à cocher en lecture seule
Toutes les cases indicateurs sont `disabled` + `pointer-events:none`
+ `stopPropagation`. Elles reflètent les triggers PostgreSQL, ne jamais
les rendre cliquables. Conditions d'activation : voir le tableau de la
section « Triggers PostgreSQL actifs ».

### Tooltips par colonne (données constitutives)
- Retraite : `age`, `anniversaire`
- Patrimoniale : `mai_ir`
- Placement : `ca_r`, `tresorerie_r`, ratio tréso/CA
- Franchise TVA prest / achat-revente : `ca_r`, `achat_revente`
- Prévoyance : `prevoyance`, `structure`
- Arbitrage rémunération : `resultat_r`
- « Données manquantes » si la valeur est NULL

---

## Modal détail client (`index.html`)
- Masquer les champs NULL, vides ou à 0 → modal épurée
- Booléens : `true`/`t` → « Oui », `false`/`f` → « Non »
- Dates ISO → format `JJ/MM/YYYY`
- Champ `commentaires` : pleine largeur en bas de modal

---

## Pièges connus à éviter

1. **`sync_html.py` écrase `static/index.html`** → ce fichier est exclu de
   la synchronisation. Modifier UNIQUEMENT `static/index.html` pour les
   changements spécifiques à la prod ; ne jamais modifier `index.html`
   (racine) directement pour la prod.
2. **Cache Render des fichiers statiques** → la route `/index.html` dans
   `main.py` a `Cache-Control: no-cache`. Ne pas supprimer cette route.
3. **Dates** : affichées en `DD/MM/YYYY` (ou `JJ/MM`) dans l'interface,
   stockées en `YYYY-MM-DD` dans PostgreSQL. Toujours convertir avant INSERT/UPDATE.
4. **`anciennete`** : recalculer via `/api/migrate/anciennete` après chaque
   import CSV massif.
5. **`filterField` snake_case strict** : dans `initDeclaratifPage()` (et tout
   moteur de filtre similaire), la valeur passée doit correspondre EXACTEMENT
   au nom de colonne PostgreSQL en snake_case minuscules (ex : `"cvae"`, pas
   `"CVAE"`). PostgreSQL est sensible à la casse. Le moteur peut appliquer
   `.toLowerCase()` mais la valeur de référence doit déjà être correcte.

---

## RÈGLE ABSOLUE — Modifications ciblées

Avant toute modification d'un fichier HTML/JS :
1. Lire le fichier AVANT de modifier (`git show <commit> -- <fichier>` si besoin)
2. Modifier UNIQUEMENT ce qui est demandé
3. Ne jamais toucher aux fonctions de sauvegarde, filtres, autres colonnes
   ou logique métier non concernées
4. `git diff` avant de committer pour vérifier
5. Si le diff montre plus de 3 lignes modifiées pour un simple changement
   d'affichage → STOP, quelque chose cloche
6. Pour une modification globale (ex : migration d'endpoint) → vérifier
   CHAQUE occurrence individuellement

Régressions fréquentes : après une modif de `missions.html`, vérifier que
`juridique_exceptionnel` est toujours lu et sauvegardé via
`PATCH /api/client/{siret}`.

---

## État du projet
<!-- Mettre à jour à la fin de chaque session -->
- 35 étapes réalisées (migration PostgreSQL, frontend complet, 11 triggers,
  calendrier intelligent, sécurité RGPD, import FEC multi-fichiers,
  pagination serveur, modal rendement, index PostgreSQL).
- CRM en production : https://projet-crm-m0o3.onrender.com

### Session 19/05/2026 — étapes 28 à 35
- **Étape 28** : `auth.js` — vérification locale JWT (payload.exp) avant fetch réseau
- **Étape 29** : Restauration `anniversaires.html` (calendrier fiscal détruit par commit `77f8d39`) + fix `response.data`
- **Étape 30** : `GET /api/clients/distinct?field=X` — whitelist collaborateur/assistant/structure/activite_r
- **Étape 31** : `GET /api/clients?limit=0` — tous les clients sans pagination
- **Étape 32** : `gestion-clients.html` — filtres et datalists alimentés par l'API ; `loadAllClients?limit=0`
- **Étape 33** : `GET /api/migrate/add_indexes` — 4 index PostgreSQL (nom, collab, assistant, annee), appelé en prod
- **Étape 34** : `rendement.html` — modal détail score avec 4 barres de progression + plafond progressif
- **Étape 35** : Pagination serveur sur `declaratif.html`, `missions.html`, `commercial.html`

## Prochaines étapes
<!-- Mettre à jour à la fin de chaque session -->
- Pagination serveur sur `opportunites.html` (même pattern que les 3 pages refactorisées)
- Export CSV filtré sur `commercial.html` et `declaratif.html` (bouton « Exporter » → `limit=0`)
- Trancher la cohérence sécurité `/api/migrate/*` (protégé vs `_MIGRATE_PUBLIC`)
- Endpoint `/api/migrate/install_all_triggers` (réinstalle les 11 en 1 clic)
- Endpoint `/api/debug/health` (vérifie la présence des 11 triggers)
- Affichage badges colorés `franchise_tva` sur `declaratif.html`
- Cron Render quotidien pour `refresh_age` et `anciennete`
## Session 21/05/2026 — Filtres, performance, Make, sécurité

### requireFn vs filterField — règle critique
Les pages déclaratives doivent utiliser `filterField` (filtre serveur)
et NON `requireFn` (filtre JS côté client).

`requireFn` ne fonctionne que sur les 50 clients de la page courante
→ pagination et compteur incorrects.

**Mapping correct par page :**
| Page | filterField |
|------|-------------|
| ca12.html | `"ca12"` |
| tvs.html | `"tvs"` |
| cvae.html | `"cvae"` |
| is.html | `"is"` |
| ir.html | `"impot_sur_le_revenu"` |
| liasse.html | `"liasse"` |
| cfe.html | `"cotisation_fonciere_entreprise"` |
| dividendes.html | `"dividendes"` (NUMERIC → filtre > 0) |
| juridique.html | `"juridique"` |
| situation.html | `"situation"` |
| tbb.html | `"tbb"` |

Ne jamais utiliser `requireFn` sur une page paginée.

---

### Types PostgreSQL des colonnes déclaratives
Vérifié via `information_schema.columns` :
- **boolean** : `ca12`, `tvs`, `cvae`, `cotisation_fonciere_entreprise`,
  `impot_sur_le_revenu`, `is`, `juridique`, `liasse`, `situation`, `tbb`
- **numeric** : `dividendes`

Condition SQL selon le type :
- boolean → `"champ" = TRUE`
- numeric → `"champ" > 0`

Dans `main.py`, `get_clients()` gère déjà les deux cas :
```python
if filterField == "dividendes":
    conditions.append('"dividendes" > 0')
else:
    conditions.append(f'"{filterField}" = TRUE')
```

---

### Filtres exact côté serveur (index.html)
Nouveaux paramètres dans `GET /api/clients` :
`collaborateur_exact`, `assistant_exact`,
`structure_exact`, `activite_r_exact`
→ correspondance stricte `= %s` (pas ILIKE)
→ évite que `assistant1` matche `assistant10`

Même ajout dans `get_clients_stats()` pour que les compteurs
dashboard reflètent les filtres.

---

### Endpoint `/api/clients/distinct`
`GET /api/clients/distinct?field=collaborateur`
Retourne les valeurs distinctes non nulles triées.
Whitelist : `collaborateur`, `assistant`, `structure`, `activite_r`.
Utilisé pour alimenter les datalists/selects indépendamment
de la pagination.

---

### Endpoint `/api/auth/token-make`
`POST /api/auth/token-make`
Protégé par `ADMIN_TOKEN` (header `Authorization: Bearer`).
Génère un JWT sans expiration pour les automatisations Make.
Payload : `{"sub": "make-automation", "role": "readonly"}`

PowerShell pour générer le token :
```powershell
$token = 'ADMIN_TOKEN_VALUE'
$h = @{Authorization="Bearer $token"; "Content-Type"="application/json"}
Invoke-RestMethod -Method Post -Uri "https://projet-crm-m0o3.onrender.com/api/auth/token-make" -Headers $h
```

⚠️ Token à stocker dans Make uniquement, jamais dans un fichier versionné.

---

### Correction ADMIN_TOKEN Render
Le token Render était `CRM-Hofman-2026-!Lorient` (! mal placé)
au lieu de `CRM-Hofman-2026-Lorient!`.
Tous les appels `/api/migrate/*` et `/api/debug/*` échouaient
silencieusement en production depuis le début.
Corrigé dans Render → Environment le 21/05/2026.

---

### Automatisation Make — Alertes calendrier fiscal
Scénario Make opérationnel :
- Déclencheur : chaque jour à 07:00
- Module HTTP : `GET /api/calendrier/fiscal` avec token Make
- Iterator + Text aggregator : filtre événements du jour
- Microsoft 365 Email : récapitulatif à `benjamin.hofman@hotmail.com`
- Filtre : email envoyé uniquement si au moins 1 événement

**Important** : `/api/calendrier/fiscal` ne nécessite pas de pagination
— il charge tous les clients pour construire le calendrier complet.
Ne jamais ajouter de limite à cet endpoint.

---

### Bouton déconnexion violet
Dans `auth.js`, `injectLogoutButton()` :
- Couleur : `background:#8e44ad`
- Hover : `background:#6c3483`

---

### Panneau filtres latéral (index.html)
Filtres restructurés en panneau latéral rétractable :
- Bouton "Filtres" dans le header ouvre/ferme le panneau
- Sections : Collaborateur, Assistant, Structure, Activité, Clôture
- Bouton "Réinitialiser" vide tous les filtres + search + tranche
- Filtres Structure et Activité alimentés depuis `/api/clients/distinct`

---

### Guillemets typographiques — prévention
Après toute refonte importante d'un fichier HTML,
vérifier la présence de guillemets courbes U+2018/U+2019 :
```python
with open('fichier.html', encoding='utf-8') as f: data = f.read()
count = data.count('\u2018') + data.count('\u2019')
print(f'{count} guillemets courbes — {"⚠️ corriger" if count else "✅ OK"}')
```

---

### Index PostgreSQL (ajoutés le 21/05/2026)
```sql
CREATE INDEX IF NOT EXISTS idx_clients_nom ON clients(nom_client);
CREATE INDEX IF NOT EXISTS idx_clients_collab ON clients(collaborateur);
CREATE INDEX IF NOT EXISTS idx_clients_assistant ON clients(assistant);
CREATE INDEX IF NOT EXISTS idx_clients_annee ON clients(annee);
```
Via `GET /api/migrate/add_indexes` (protégé ADMIN_TOKEN).
Utiles à partir de ~1000 clients.

---

### État du projet (21/05/2026)
- 1010 clients en base (10 réels + 1000 fictifs pour tests)
- Pagination serveur opérationnelle sur toutes les interfaces
- Filtres booléens corrigés sur toutes les pages déclaratives
- Automatisation Make calendrier fiscal active
- Token Make sans expiration généré et configuré

### Prochaines étapes
- Supprimer les logs debug temporaires (`/api/debug/bool_counts`,
  logs AUTH HEADER dans `token-make`)
- Cron Render quotidien pour `refresh_age` et `anciennete`
- Pagination `opportunites.html` complète avec filtres serveur
- Export CSV filtré sur `commercial.html` et `declaratif.html`
- Endpoint `/api/clients/light` (colonnes réduites) pour performance
## Session 21/05/2026 (après-midi) — Filtres dynamiques, performance, UX

### Endpoint /api/clients/filters (endpoint groupé)
Remplace les 5 appels `/api/clients/distinct` séparés par 1 seul :
`GET /api/clients/filters`
Retourne :
```json
{
  "assistants": [...],
  "collaborateurs": [...],
  "annees": [...],
  "mois_cloture": ["01","02",...,"12"],
  "noms": [...]
}
```
Toutes les pages appellent cet endpoint au chargement
pour alimenter leurs datalists/selects.
Gain : 5 requêtes → 1 par page au chargement.

---

### Filtres dynamiques — pattern standard (toutes les pages)
Chaque page a maintenant :
- Input texte + datalist pour : Nom client, Assistant,
  Collaborateur, Année, Clôture (mois)
- Option par défaut labelisée : "— Assistant —" etc.
- Correspondance exacte via `_exact` params pour
  assistant et collaborateur (évite collab1 → collab10)
- Clôture : filtre par mois via `-MM-` (ILIKE)
- Debounce 300ms sur le champ recherche nom client
- Bouton "🔄 Réinitialiser" sur toutes les pages

Pages migrées : `decl-engine.js` (couvre ca12, tvs, cvae,
is, ir, liasse, cfe, dividendes, juridique, situation, tbb),
`missions.html`, `opportunites.html`, `commercial.html`,
`rendement.html`, `declaratif.html`

### Paramètres exact dans GET /api/clients
```
collaborateur_exact, assistant_exact,
structure_exact, activite_r_exact
```
→ condition `= %s` (pas ILIKE)
→ aussi dans `get_clients_stats()` pour cohérence compteurs

### Filtre clôture par mois
`/api/clients/distinct?field=mois_cloture` retourne
`["01","02",...,"12"]` (SUBSTRING de date_de_cloture).
Frontend passe `cloture=-MM-` (ex: `-06-`) → ILIKE matche
toutes les dates du mois 06 quelle que soit l'année.

---

### SELECT colonnes réduites dans get_clients()
`SELECT *` remplacé par ~45 colonnes essentielles dans
`get_clients()` pour réduire le payload des listes.
`SELECT *` conservé uniquement dans `get_client(siret)`
(fiche détail complète).

Colonnes exclues des listes (non nécessaires pour les tableaux) :
colonnes mensuelles TVS (`janvier_tvs`...`decembre_tvs`),
colonnes mensuelles CA12 soldes, colonnes CVAE mensuelles,
colonnes bilan détaillées, ratios financiers.

⚠️ Si une page liste a besoin d'une colonne absente →
l'ajouter à la liste dans `get_clients()`, pas revenir à SELECT *.

---

### requireFn → filterField — règle définitive
`requireFn` est INTERDIT sur toute page paginée.
Toujours utiliser `filterField` (filtre serveur).
Les seuls cas où du filtrage JS post-réponse est acceptable :
- Cases à cocher colonnes dans `declaratif.html`
  (filtrage sur la page courante seulement, pagination affectée)
- Indicateurs TEXT dans `opportunites.html`
  (mission_retraite="OUI", mission_placement="OPPORTUNITÉ...")

---

### Export CSV filtré
Bouton "⬇ Exporter tout" sur `commercial.html` et
`declaratif.html` : appelle `GET /api/clients?limit=0`
avec tous les filtres actifs → exporte l'intégralité
de la sélection, pas seulement la page courante.

---

### Pagination opportunites.html côté serveur
Filtres indicateurs booléens passés comme params URL :
`mission_retraite=OUI`, `op_prevoyance=OUI`, etc.
`mission_placement=OPPORTUNITÉ FORTE,OPPORTUNITÉ MOYENNE`
Backend : condition `IN` pour mission_placement,
`= 'OUI'` pour les autres champs TEXT d'opportunités.
Whitelist ALLOWED étendue avec ces champs TEXT.

---

### Debounce recherche
Pattern debounce 300ms sur tous les champs recherche :
```javascript
let _debounceTimer = null;
function applyFilters() {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => loadPage(1), 300);
}
```
Évite un appel API à chaque frappe de touche.

---

### mois_cloture dans whitelist distinct
`/api/clients/distinct?field=mois_cloture` ajouté à la
whitelist de l'endpoint distinct.
Retourne les mois distincts (`SUBSTRING(date_de_cloture, 6, 2)`)
triés, pour alimenter les filtres clôture.

---

### Affichage mois clôture
Options du select clôture affichées comme :
"Janvier (01)", "Février (02)", ..., "Décembre (12)"
Map côté JS : `{"01":"Janvier","02":"Février",...}`

---

### État du projet (21/05/2026 après-midi)
Toutes les interfaces principales ont :
✅ Pagination serveur (50 par page)
✅ Filtres dynamiques avec datalist
✅ Correspondance exacte assistant/collaborateur
✅ Filtre clôture par mois
✅ Bouton Réinitialiser
✅ Champ recherche nom client avec debounce

### Prochaines étapes
- Supprimer endpoint debug `/api/debug/bool_counts`
  et logs temporaires dans `token-make`
- Cron Render quotidien pour `refresh_age` et `anciennete`
- Filtre rendement minimum sur `rendement.html`
- Vérifier cohérence SELECT colonnes réduites vs besoins
  de chaque page (ajouter colonnes manquantes si nécessaire)

---

## Session 21/05/2026 (soir) — Performance SELECT, exports CSV, filtres serveur

### SELECT explicite dans get_clients() — 59 colonnes
`get_clients()` utilise désormais une liste explicite de 59 colonnes
au lieu de `SELECT *`. Exclut les 24 colonnes mensuelles :
- `janvier_tvs` → `decembre_tvs` (12 colonnes)
- `janvier_ca12_solde` → `decembre_ca12_solde` (12 colonnes)

`get_client(siret)` conserve `SELECT *` (fiche détail complète).

⚠️ **Conséquence connue** : `tvs.html` et `ca12.html` ne reçoivent plus
les valeurs mensuelles via `get_clients()`. Un endpoint dédié
`/api/clients/monthly` sera nécessaire pour pré-remplir ces inputs.

---

### Endpoint /api/clients/filters (groupé)
`GET /api/clients/filters` retourne en une seule requête SQL :
```json
{"assistants":[...],"collaborateurs":[...],"annees":[...],"mois_cloture":[...],"noms":[...]}
```
Utilise `array_agg(DISTINCT col ORDER BY col) FILTER (WHERE ...)`.
Remplace les 4–5 appels séparés à `/api/clients/distinct` dans `populateSelects()`.

Pages migrées : `missions.html`, `decl-engine.js` (11 pages déclaratives),
`opportunites.html`, `commercial.html`, `rendement.html`, `declaratif.html`.

---

### Filtres TEXT opportunités côté serveur
Dans `get_clients()`, whitelist `ALLOWED` étendue avec les champs TEXT
d'opportunité. Condition SQL selon le type :
- Champs TEXT_OPP (`mission_retraite`, `mission_patrimoniale`, `op_prevoyance`,
  `franchise_tva_prest`, `franchise_tva_achrevente`, `arbitrage_remuneration_dirigeant`) :
  `"champ" IS NOT NULL AND "champ" != '' AND "champ" != 'Données manquantes'`
- `mission_placement` :
  `"mission_placement" IN ('OPPORTUNITÉ FORTE','OPPORTUNITÉ MOYENNE')`

---

### Bouton "⬇ Exporter tout"
Ajouté sur `declaratif.html` et `commercial.html`.
Pattern : `GET /api/clients?limit=0` + filtres actifs → post-filtrage JS
→ `exportCSV()`. Génère le CSV complet de la sélection courante.

Colonnes exportées `declaratif.html` (17) :
`code_client, nom_client, assistant, collaborateur, annee, date_de_cloture,
ca12, tvs, cvae, impot_sur_le_revenu, is, liasse,
cotisation_fonciere_entreprise, dividendes, juridique, situation, tbb`

Colonnes exportées `commercial.html` (10) :
`code_client, annee, nom_client, assistant, collaborateur, date_de_cloture,
suivi_mission_retraite, suivi_mission_patrimoniale, suivi_mission_placement, suivi_mission_prevoyance`

---

### Debounce `:not(#search)` — piège double-bind
Quand un input a `list="dl-xxx"`, il est ciblé par `input[list]` ET
peut avoir un listener dédié avec debounce. Toujours exclure `#search` :
```javascript
document.querySelectorAll('.filters-top input[list]:not(#search)').forEach(...)
```
Sinon `applyFilters` est bindé deux fois sur `#search` (direct + debounced).

---

### État du projet (21/05/2026 soir)
- 43 étapes réalisées
- Exports CSV opérationnels sur `declaratif.html` et `commercial.html`
- `populateSelects()` unifié sur toutes les pages via `/api/clients/filters`
- `get_clients()` optimisé : 59 colonnes explicites, payload réduit

### Prochaines étapes
- Endpoint `/api/clients/monthly` pour `tvs.html` et `ca12.html` (colonnes mensuelles)
- Bouton "⬇ Exporter tout" sur `rendement.html` et `opportunites.html`
- Supprimer code mort (`dataGlobal`, `fetchClients()`) dans `opportunites.html`
- Supprimer logs debug temporaires (`/api/debug/bool_counts`, logs AUTH dans `token-make`)
- Cron Render quotidien pour `refresh_age` et `anciennete`
- Endpoint `/api/migrate/install_all_triggers` (réinstalle les 11 en 1 clic)
- Endpoint `/api/debug/health` (vérifie présence des 11 triggers)

## ÉTAPE 44 — CVAE acomptes juin/septembre (22/05/2026)
- cvae.html : 3 colonnes mai_cvae, acompte_cvae_juin, acompte_cvae_septembre
- Grisées si ca_r connu ET <= 500000, actives sinon
- disabledFn: c => c.ca_r && parseFloat(c.ca_r) <= 500000


## ÉTAPE 45 — Espace collaborateur (26/05/2026)
- Sélecteur « Mon espace » sur index.html
- `sessionStorage('espaceCollab')` partagé entre toutes les pages
- Badge « Espace : X » + bouton ✕ sur toutes les pages
- `collaborateur_exact` injecté dans `loadPage()` sur toutes les pages
- Dashboard index.html filtré sur l'espace actif
  (KPIs + répartition + anniversaires) ; répartition masquée + grille
  pleine largeur + titre « Portefeuille de X » quand un espace est actif
- Changement d'espace sans rechargement complet (loadPage(1) + loadDashboardExtra)
- `espace.js ?v=8`, `decl-engine.js ?v=3`

### État du projet (26/05/2026)
- 45 étapes réalisées
- Espace collaborateur opérationnel : un collaborateur peut filtrer tout le
  CRM sur son portefeuille via le sélecteur « Mon espace » (sessionStorage),
  filtre appliqué côté serveur (`collaborateur_exact`) sur chaque page.
- CRM en production : https://projet-crm-m0o3.onrender.com

### Prochaines étapes
- `exportAll()` des pages de suivi : lire `sessionStorage` pour exporter
  en cohérence avec l'espace actif
- Titre/badge « espace » sur les pages de suivi (homogénéité avec l'accueil)
- Persistance optionnelle du dernier espace côté serveur (sessionStorage est
  vidé à la fermeture de l'onglet)


## ÉTAPE 47 — Dashboard portefeuille enrichi (26/05/2026)
> Note : pas d'ÉTAPE 46 dans ce fichier (numérotation poursuivie à 47 sur demande).
- Badges Opportunités cliquables vers opportunites.html
  avec filtre type + collab/assistant propagé en URL
- opportunites.html lit les params URL au chargement
- Section "💼 Suivi Commercial" dans vue portefeuille :
  tableau Mission | Nb détectés | Nb acceptés
  colonnes : suivi_mission_retraite/patrimoniale/
  placement/prevoyance (valeurs exactes 'détecté','accepté')
- Liens vers commercial.html avec suivi_mission_X=détecté
  + collab/assistant propagé
- commercial.html lit les params URL au chargement
- Exclusivité mutuelle collab/assistant :
  sélectionner l'un vide l'autre (sessionStorage + select)
- Pagination repositionnée sous le tableau principal
- Total missions détectées en pied de tableau


## Espace collaborateur — `sessionStorage` (26/05/2026, refondu)

### Principe
Permet à un collaborateur de naviguer dans tout le CRM en ne voyant que SON
portefeuille. L'espace actif est stocké dans **`sessionStorage` sous la clé
`espaceCollab`** (et NON plus via un paramètre d'URL `?collab`). Le filtre
serveur reste `collaborateur_exact`.

> Exception assumée à la « Règle absolue » sur `sessionStorage` : `espaceCollab`
> est un **état UI éphémère** (filtre de vue, effacé à la fermeture de l'onglet),
> pas une donnée métier — même statut que le token JWT `crm_token` déjà stocké
> en `sessionStorage`. Aucune donnée client n'y est persistée.

### Module partagé `static/espace.js`
Source unique de toute la logique « espace ». Inclus dans 17 pages via
`<script src="/espace.js?v=N"></script>` (cache-busting `?v=` à incrémenter
à CHAQUE modif du fichier). Deux modèles de pages :

- **`index.html`** (pilotage) : `<select id="mon-espace">` + badge fermable ✕.
  - `onMonEspaceChange(val)` : `sessionStorage.setItem('espaceCollab', val)`
    (ou `removeItem` si « — Tous — ») puis `location.reload()`.
  - `populateMonEspace()` : alimente le select via `/api/clients/filters`,
    présélectionne d'après `sessionStorage`.
  - `renderEspaceBadge()` : badge « Espace : X » avec ✕ →
    `removeItem('espaceCollab')` + reload.
  - `initEspaceIndex()` : lit `sessionStorage`, pré-remplit le select + badge.

- **Pages de suivi** : `injectEspaceCollab()` lit `sessionStorage`, pré-remplit
  l'input collaborateur (`filter-collab` ou `f-collab`), expose
  `window._espaceCollab`, affiche un badge « 🏢 Espace : X » (lien vers
  `index.html`) après `#page-title` sinon dans `.header`.

⚠️ Plus AUCUNE propagation `?collab` dans les liens (fonctions
`propagateCollabToNav` / `propagateCollabToLinks` et le `MutationObserver`
SUPPRIMÉS) : `sessionStorage` persiste nativement entre les navigations du
même onglet.

### Règle critique — filtre TOUJOURS appliqué dans `loadPage()`
Chaque `loadPage()` lit `sessionStorage` **juste avant le `fetch`**, en DERNIER
`params.set` (prioritaire) :
```javascript
const _c = sessionStorage.getItem("espaceCollab");
if (_c) params.set("collaborateur_exact", _c);
```
Présent dans : `decl-engine.js`, `declaratif.html`, `missions.html`,
`opportunites.html`, `commercial.html`, `rendement.html`. Sur `index.html`,
`loadPage()` lit aussi `sessionStorage.getItem('espaceCollab')`.

### Architecture des pages déclaratives — PIÈGE
- `decl-engine.js` est le moteur partagé chargé par **11 pages HTML
  indépendantes** (`cvae`, `tvs`, `ca12`, `dividendes`, `juridique`, `tbb`,
  `situation`, `is`, `cfe`, `liasse`, `ir`). PAS d'iframe.
- `declaratif.html` est une page DISTINCTE avec sa PROPRE `loadPage()` (ne
  charge pas `decl-engine.js`). Toute logique espace doit y être ajoutée
  séparément.

### Non couvert (TODO)
- `exportAll()` lit encore l'input (OK car rempli au chargement par
  `injectEspaceCollab`), pas `sessionStorage` directement.


## Claude Code — capacités
- Prompts courts suffisent (5-10 lignes max)
- Peut lire, modifier plusieurs fichiers, committer et pusher en autonomie
- Pas besoin de découper si la tâche est claire

Mets à jour CLAUDE.md, ajoute après l'étape 45 :

ÉTAPE 46 — Espace assistant + dashboard opportunités (26/05/2026)
- Sélecteur "👤 Assistant" dans le header de index.html
- sessionStorage('espaceAssistant') partagé entre toutes les pages
- assistant_exact injecté dans loadPage() de decl-engine.js,
  missions.html, opportunites.html, commercial.html, 
  rendement.html, declaratif.html
- Vue "Portefeuille de X" identique collab et assistant :
  KPIs filtrés, Mon portefeuille, Anniversaires 45j
- Section "📊 Opportunités" : badges colorés avec compteurs
  (Retraite, Patrimoniale, Placement, Franchise TVA prest/achrev,
  Prévoyance, Arbitrage rémunération) — masqués si compteur = 0
- Header redesigné sur 2 lignes : logo+search+actions / 
  navigation+filtres+espaces
- Masquage section "Répartition collaborateurs" 
  quand un espace assistant est actif

  