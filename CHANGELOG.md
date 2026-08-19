# Journal des versions - morfPackages

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et du [versionnage sémantique](https://semver.org/lang/fr/).

## [0.1.0] - 2026-08-20

### Ajouté

- Le contrat v1 de `manifest.json` pour documenter chaque livrable par son nom,
  son SHA-256, son commit Git complet, sa cible et sa plateforme.
- Les scripts de synchronisation et de publication de releases, conçus pour ne
  jamais mettre un binaire dans l'historique Git.

