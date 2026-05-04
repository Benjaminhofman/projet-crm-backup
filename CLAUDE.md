# CRM Collaborateurs Comptables

## Présentation du projet
Application CRM destinée aux collaborateurs comptables pour piloter 
un portefeuille client. L'objectif prioritaire est une UX/UI 
excellente : fluide, intuitive et moderne.

Intégrations actuelles et à venir :
- **Airtable** : source de données principale
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

## Intégration Airtable
- Respecter les limites de l'API Airtable (5 req/sec)
- Toujours gérer les erreurs d'API proprement
- Mettre en cache les données quand c'est possible pour la fluidité

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