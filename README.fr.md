# morfPackages

[![Version](https://img.shields.io/badge/version-0.6.0-blue)](CHANGELOG.md)

J'avais besoin de pouvoir installer une version de morfSystem sans transformer les dépôts de code en entrepôts de binaires. `morfPackages` garde donc un rôle étroit : il rassemble les livrables déjà construits, sans compiler à leur place ni s'approprier leurs recettes.

Le dépôt Git ne contient que ce qui doit durer : le contrat de manifeste et les scripts. Les `.deb`, `.zip` et firmwares restent uniquement dans les assets des releases GitHub. Une release porte le nom `<projet>-v<version>` et réunit les plateformes de cette version, son `manifest.json` et `checksums.sha256`.

Le dépôt source du workspace reste l'autorité. Avant toute publication, le
script vérifie la release et le tag distant `vX.Y.Z`, puis exige que leur commit
complet corresponde exactement à celui de l'artefact et contrôle son SHA-256.
Un conflit est refusé sans écrasement. Après validation, les mêmes assets, le
manifeste et les sommes de contrôle sont recopiés dans la release du dépôt
source : l'utilisateur trouve donc directement les installables sur la page de
release du projet.

`scripts/release.py sync` récupère les assets déjà publiés dans le dossier de distribution commun. `scripts/release.py publish` ajoute seulement les artefacts manquants d'une plateforme, après les vérifications nécessaires, puis les recopie dans la release source. Les deux passent uniquement par `gh release` pour les assets.

Le schéma du manifeste v1 se trouve dans [schema/manifest.schema.json](schema/manifest.schema.json).
