# Journal des versions - morfPackages

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et du [versionnage sémantique](https://semver.org/lang/fr/).

## [0.6.2] - 2026-08-20

### Corrigé

- Les manifestes et sommes de contrôle sont remplacés séparément lors d'une
  reprise. Ils peuvent évoluer sans provoquer de conflit avec les binaires.
- Un échec de commande sans sortie ne masque plus son code de retour par une
  erreur Python.

## [0.6.1] - 2026-08-20

### Corrigé

- Une reconstruction locale différente ne bloque plus la recopie vers la
  release projet d'un asset déjà validé dans l'index. L'asset indexé n'est
  jamais remplacé.

## [0.6.0] - 2026-08-20

### Ajouté

- Les installables validés, le manifeste et les sommes de contrôle sont aussi
  ajoutés à la release du dépôt source, pour les rendre accessibles depuis la
  page de release consultée par les utilisateurs.

## [0.5.0] - 2026-08-20

### Ajouté

- La publication résout désormais le tag distant `vX.Y.Z` du dépôt source
  d'autorité et exige que son SHA complet soit celui de chaque artefact.
- Le manifeste enregistre le dépôt source, le tag et son commit. Toute
  divergence avec un asset déjà enregistré est un refus bloquant, sans mutation
  de la release.

## [0.4.0] - 2026-08-20

### Modifié

- La vérification de la release source déduit le dépôt correspondant du
  workspace courant, afin que la sandbox publie et vérifie ses releases privées
  sans toucher à la production.

## [0.3.1] - 2026-08-20

### Ajouté

- Modèles GitHub pour les rapports de bug, les questions et les améliorations.

## [0.3.0] - 2026-08-20

### Ajouté

- Texte de release personnalisable lors de la première publication d'une
  version depuis `package-all`.

## [0.2.0] - 2026-08-20

### Modifié

- `package-all` prépare désormais le dépôt avant de construire et publie
  automatiquement chaque livrable prouvé vers sa release GitHub privée.

## [0.1.0] - 2026-08-20

### Ajouté

- Le contrat v1 de `manifest.json` pour documenter chaque livrable par son nom,
  son SHA-256, son commit Git complet, sa cible et sa plateforme.
- Les scripts de synchronisation et de publication de releases, conçus pour ne
  jamais mettre un binaire dans l'historique Git.
