[English](CHANGELOG.md) · **Français**

# Journal des modifications

Toutes les évolutions notables de FreeFox sont documentées ici.
Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et le projet utilise le
[versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté
- Option `--version` sur `freefox`, `freefox-dashboard` et `freefox-status` pour afficher la version installée.
- Publication sur PyPI : `pip install freefox` (avec l'extra `s3` pour S3 / MinIO). Un workflow
  publie chaque release GitHub via le Trusted Publishing PyPI.
- Commandes `freefox-dashboard` et `freefox-status`, installées avec le paquet. Les scripts
  `scripts/dashboard.py` et `scripts/queue_status.py` fonctionnent toujours.
- Guide de publication (`docs/fr/releasing.md`, `docs/en/releasing.md`).
- Versions française et anglaise de tous les documents : `*.md` / `*.fr.md` à la racine,
  `docs/en/` et `docs/fr/` pour les guides.
- Guide de contribution, code de conduite, politique de sécurité, modèles d'issues et de pull requests.
- Guide d'architecture (`docs/fr/architecture.md`, `docs/en/architecture.md`).
- Workflow de CI qui lance les tests sur Python 3.10 à 3.12.

### Corrigé
- Un thread d'upload ne meurt plus en silence quand le calcul de l'empreinte BLAKE3 ou la création
  du backend échoue (par exemple une config S3 invalide ou un bag supprimé pendant la lecture).
  L'entrée est désormais réessayée avec backoff et l'erreur est enregistrée.

### Modifié
- Code formaté et vérifié avec ruff, contrôlé par la CI. Le worker d'upload et la logique multipart
  S3 sont découpés en petites fonctions documentées.
- Les tests couvrent maintenant la reprise multipart S3, les sessions expirées, les conflits et la
  politique d'erreurs du worker.
- L'unité `systemd/freefox.service` est maintenant générique (`/etc/freefox/config.yaml`, `/var/lib/freefox`).
- Guides déplacés dans `docs/en/` et `docs/fr/`, et guides Docker et Google Drive réorganisés.
- Feuille de route du README présentée par phases.
- Métadonnées du package : licence SPDX, classifiers, URLs du projet, version définie à un seul
  endroit. Le logo du dashboard est inclus dans le paquet (31 Ko) et l'image Docker ne copie plus `images/`.

## [0.2.0] - 2026-08-15

### Ajouté
- **Backend AWS S3 et compatible MinIO** (`storage.backend: s3`, extra `pip install freefox[s3]`) :
  - uploads multipart durables : `UploadId` et parts persistés en SQLite et repris après redémarrage,
  - taille des parts calculée automatiquement sous la limite de 10 000 parts,
  - BLAKE3 et taille stockés dans les métadonnées de l'objet, déduplication et détection de conflits,
  - chaîne de credentials AWS standard uniquement (secrets refusés dans le YAML), prise en charge d'un CA privé,
  - masquage des signatures et des clés dans les messages d'erreur.
- Snapshot de destination par transfert : un transfert en attente garde les réglages de son backend d'origine.
- Nouvel état `conflict` : un contenu différent au même chemin distant n'est jamais écrasé.
- Hiérarchie d'erreurs indépendante du fournisseur et registre de backends chargé à la demande.
- `scripts/s3_smoke.py` pour les vérifications réelles S3 et MinIO.

## [0.1.0] - 2026-06-08

### Ajouté
- Surveillance des bags ROS 2 (`.mcap`, `.db3`) avec détection de stabilité et motifs à ignorer.
- File d'upload SQLite persistante, avec retries et backoff exponentiel.
- Backend Google Drive : OAuth2 ou compte de service, Shared Drives, sessions resumables conservées
  entre les redémarrages, création de dossiers robuste, gestion des erreurs de quota.
- Backend rsync pour disques locaux, NAS et destinations SSH, avec fichiers sidecar BLAKE3.
- Empreintes d'intégrité BLAKE3 et déduplication par hash.
- Dashboard web local : progression, durée, débit en MiB/s et Mbps, ETA, retries, incidents.
- Délais de retry dédiés aux erreurs réseau temporaires, et transferts en échec remis en file au démarrage.
- Unité systemd et `install.sh`.
- Image Docker (`linux/amd64`, `linux/arm64`) publiée sur GHCR, avec fichiers Docker Compose.
- Site du projet sur GitHub Pages.

[Non publié]: https://github.com/thoukam/freefox/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/thoukam/freefox/releases/tag/v0.2.0
[0.1.0]: https://github.com/thoukam/freefox/commits/v0.2.0
