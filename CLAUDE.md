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