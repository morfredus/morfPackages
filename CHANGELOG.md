# Journal des versions - morfPackages

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/)
et du [versionnage sémantique](https://semver.org/lang/fr/).

## [0.6.10] - 2026-09-03

### Fixed

- Add the parc-standard `.gitattributes` (`* text=auto`, shell scripts LF, Windows
  scripts CRLF, binaries left untouched). Without it, a working tree checked out
  with CRLF by Git for Windows showed as dirty under WSL git (`core.autocrlf=false`),
  which made the release chain's dirty-tree check refuse the repo. With `text=auto`,
  line endings are normalised consistently in every environment.

## [0.6.9] - 2026-08-25

### Ajouté

- **Stratégie d'installation dans le manifeste (`install`).** Le `manifest.json`
  déclare désormais un bloc `install` : `{"type":"package"}` pour une release
  compilée (flux historique, .deb/.zip par plateforme), ou
  `{"type":"source-bundle","asset":"...tar.gz"}` pour un projet non compilé
  (Python, ex. morfDashboard). But : que morfUpdate lise QUOI installer au lieu
  de présumer un binaire. Rétro-compat : un manifeste sans `install` vaut
  `package`. Format `source-bundle` ajouté à l'énumération du schéma
  (`schema/manifest.schema.json`), bloc `install` optionnel déclaré.
  Cf. `.morfredus_travail/Evolution/morfUpdate - strategies d'installation…`.

## [0.6.8] - 2026-08-25

### Corrigé

- **Retry étendu au transport git/SSH (`scripts/release.py`).** Le helper
  `_attempt` ne réessayait que les erreurs serveur `gh` ; une coupure SSH sur un
  `git fetch`/`pull` du preflight ou de la synchro (« Connection closed by ...
  port 22 »...) faisait encore échouer la publication. `_attempt` réessaie
  désormais aussi `git` sur ces motifs transitoires de transport, jamais sur un
  vrai refus (auth, non-fast-forward, 404).

## [0.6.7] - 2026-08-25

### Corrigé

- **Téléversement des assets de contrôle idempotent (`scripts/release.py`).**
  `gh release upload --clobber` n'écrase pas toujours l'asset existant : GitHub
  répond parfois `HTTP 422 « ReleaseAsset.name already exists »` (souvent après
  qu'une tentative précédente a bien téléversé mais renvoyé une erreur
  transitoire au client). `upload_control_assets` supprime désormais l'asset puis
  le re-téléverse dans ce cas ; `manifest.json` / `checksums.sha256` étant
  déterministes pour une version donnée, notre contenu régénéré l'emporte
  toujours.

## [0.6.6] - 2026-08-25

### Corrigé

- **Résilience aux hoquets serveur de GitHub (`scripts/release.py`).** Un seul
  `HTTP 502` (ou 429, timeout de passerelle...) pendant un `gh release upload`
  faisait échouer toute la publication du parc : vu sur l'upload d'un
  `manifest.json` rendu en 502, laissant la release sans son manifeste (et le
  garde de synchro refusait alors « no readable manifest.json » au run suivant).
  Les appels `gh` passent désormais par un helper qui **réessaie avec backoff**
  uniquement sur ces erreurs serveur transitoires (5xx/429/timeout), jamais sur
  une vraie erreur (404, refus). Sondes d'existence et téléchargement du
  manifeste inclus.

## [0.6.5] - 2026-08-22

### Corrigé

- Recopie des notes : le PATCH REST utilise l'id numérique
  (`/releases/tags/vX.Y.Z` → `.id`), plus l'id GraphQL `RE_kwDO…` renvoyé par
  `gh release view --json id` (HTTP 404 alors que les binaires étaient déjà
  montés).

## [0.6.4] - 2026-08-21

### Corrigé

- La recopie des notes vers la release source n'utilise plus `gh release edit`
  (HTTP 422 `tag_name already exists`). Un PATCH de l'id de release met a jour
  titre et corps sans renvoyer le tag.

## [0.6.3] - 2026-08-20

### Corrigé

- La synchronisation recrée le sidecar de chaque binaire téléchargé depuis son
  manifeste validé, au lieu de conserver une provenance locale obsolète.

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
