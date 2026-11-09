[English](CHANGELOG.md) · **Français**

# Journal des modifications

Toutes les évolutions notables de FreeFox sont documentées ici.
Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et le projet utilise le
[versionnage sémantique](https://semver.org/lang/fr/).

## [Non publié]

## [0.2.2] - 2026-11-09

Première version publiée sur PyPI : `pip install freefox`.

### Corrigé
- Métadonnées du paquet : remplacement d'un classifier PyPI invalide qui bloquait l'envoi de la 0.2.1.
  La CI valide désormais `pyproject.toml` à chaque pull request.

## [0.2.1] - 2026-11-09

Non publiée sur PyPI à cause d'un classifier invalide : utilisez la 0.2.2. L'image Docker
`ghcr.io/thoukam/freefox:0.2.1` est disponible.

### Ajouté
- Publication sur PyPI, avec les commandes `freefox-dashboard` et `freefox-status`.
- Option `--version` sur toutes les commandes (merci à [@X6M-Work](https://github.com/X6M-Work), #16).
- Documentation en anglais et en français, avec un guide d'architecture.

### Corrigé
- Un worker d'upload ne s'arrête plus en silence quand le calcul BLAKE3 ou la création du backend échoue.

### Modifié
- L'unité systemd est maintenant générique (`/etc/freefox/config.yaml`, `/var/lib/freefox`).

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

[Non publié]: https://github.com/thoukam/freefox/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/thoukam/freefox/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/thoukam/freefox/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/thoukam/freefox/releases/tag/v0.2.0
[0.1.0]: https://github.com/thoukam/freefox/commits/v0.2.0
