# morfPackages

[![Version](https://img.shields.io/badge/version-0.4.0-blue)](CHANGELOG.md)

J'avais besoin de pouvoir installer une version de morfSystem sans transformer les dépôts de code en entrepôts de binaires. `morfPackages` garde donc un rôle étroit : il rassemble les livrables déjà construits, sans compiler à leur place ni s'approprier leurs recettes.

Le dépôt Git ne contient que ce qui doit durer : le contrat de manifeste et les scripts. Les `.deb`, `.zip` et firmwares restent uniquement dans les assets des releases GitHub. Une release porte le nom `<projet>-v<version>` et réunit les plateformes de cette version, son `manifest.json` et `checksums.sha256`.

Le dépôt source public reste l'autorité. Avant toute publication, le script vérifie qu'il expose déjà cette version publiquement, contrôle le commit complet et le SHA-256, puis refuse un conflit au lieu d'écraser un fichier existant.

`scripts/sync-release-assets.py` récupère les assets déjà publiés dans le dossier de distribution commun. `scripts/publish-release.py` ajoute seulement les artefacts manquants d'une plateforme, après les vérifications nécessaires. Les deux passent uniquement par `gh release` pour les assets.

Le schéma du manifeste v1 se trouve dans [schema/manifest.schema.json](schema/manifest.schema.json).
