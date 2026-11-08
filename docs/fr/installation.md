[English](../en/installation.md) · **Français**

# Installation

Ce guide explique comment installer FreeFox en local pour les tests, puis comme service systemd sur
un robot ou une machine Linux. Pour Docker, voir [docker-deployment.md](docker-deployment.md).

## Prérequis

- Linux
- Python 3.10 ou plus récent, avec `pip`
- Un backend de stockage :
  - Google Drive : voir [google-drive-setup.md](google-drive-setup.md)
  - rsync : une destination locale ou SSH (`rsync` et `openssh-client` installés)
  - S3 / MinIO : un bucket existant, voir [s3-storage.md](s3-storage.md)

Optionnel : `sqlite3` pour inspecter la base de la file d'upload.

## Installation locale de développement

```bash
git clone https://github.com/thoukam/freefox
cd freefox
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"        # ajoutez ,s3 pour le backend S3 : ".[dev,s3]"
```

`-e` signifie *editable* : la commande `freefox` installée exécute directement le code du dépôt.
boto3 reste optionnel et n'est importé que si `storage.backend: s3` est sélectionné.

Vérifier :

```bash
.venv/bin/freefox --help
.venv/bin/python -m pytest
.venv/bin/python scripts/local_smoke.py   # test de bout en bout sans compte cloud
```

> **ROS 2 sourcé dans votre shell ?** ROS ajoute ses propres plugins pytest au `PYTHONPATH`. Si la
> collecte des tests échoue, lancez
> `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_timeout`.

Les fichiers générés par pip (`freefox.egg-info/`, `.venv/`) sont ignorés par git et ne doivent pas
être modifiés à la main.

## Configuration locale

```bash
cp config/config.example.yaml config/local.gdrive.yaml
```

Exemple minimal pour Google Drive :

```yaml
robot_id: pc-test

watch:
  directory: /tmp/freefox-bags
  stable_seconds: 2.0

upload:
  workers: 1
  chunk_size: 8388608
  verify_blake3: true
  deduplicate_by_hash: true

drive:
  credentials_file: ./secrets/freefox-oauth-client.json
  target_folder_id: "ID_DU_DOSSIER_GOOGLE_DRIVE"

queue_db: /var/lib/freefox/queue.db
```

Toutes les options sont commentées dans
[`config/config.example.yaml`](../../config/config.example.yaml). Les fichiers `config/local*.yaml`
sont ignorés par git.

## Validation de la configuration

Avant de lancer le service, vous pouvez valider le fichier de configuration et tester la connectivité au backend de stockage :

```bash
freefox --config config/local.gdrive.yaml --check-config
```

Cette commande vérifie la validité du schéma YAML, s'assure que `watch.directory` existe et est accessible en lecture, et teste que le backend de stockage répond (`exists("freefox-check")`).

## Test Google Drive

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Au premier lancement OAuth2, Google ouvre un navigateur pour l'autorisation. Le token est ensuite
écrit dans `FREEFOX_TOKEN_PATH`.

## Test avec de vrais rosbags

```bash
mkdir -p /tmp/freefox-bags
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/freefox --config config/local.gdrive.yaml
```

Dans un autre terminal :

```bash
cp /chemin/vers/votre/bag.mcap /tmp/freefox-bags/
```

FreeFox attend que la taille du fichier soit stable pendant `watch.stable_seconds`, l'ajoute à la
file, puis lance l'upload vers `<robot_id>/<AAAA-MM-JJ>/<fichier>`, par exemple
`pc-test/2026-06-05/bag.mcap`.

Inspecter la file :

```bash
.venv/bin/freefox-status /var/lib/freefox/queue.db
# ou
sqlite3 -header -column /var/lib/freefox/queue.db \
  "SELECT id, local_path, remote_path, status, retries, error FROM queue;"
```

## Installation comme service systemd

```bash
sudo ./install.sh
sudo nano /etc/freefox/config.yaml
sudo systemctl enable --now freefox
journalctl -u freefox -f
```

`install.sh` :

- installe le package Python (avec l'extra S3),
- crée `/etc/freefox` et `/var/lib/freefox`,
- copie `config/config.example.yaml` vers `/etc/freefox/config.yaml` s'il n'existe pas,
- installe `systemd/freefox.service` en utilisant l'utilisateur qui lance `sudo`. Vous pouvez le
  surcharger avec `SERVICE_USER=... SERVICE_GROUP=...`.

L'unité est durcie (`ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=true`). Si
`delete_after_upload: true`, ajoutez le dossier des bags à `ReadWritePaths` avec
`sudo systemctl edit freefox`.

Sous systemd, évitez une base de file dans `/tmp` : à cause de `PrivateTmp=true`, le service voit un
`/tmp` privé que vos outils ne voient pas. Utilisez `/var/lib/freefox/queue.db`.

## Redémarrage et reprise d'upload

L'état de chaque transfert est stocké dans SQLite : statut, retries, progression, empreinte BLAKE3,
URI de session Google Drive et parts S3 déjà envoyées.

Au redémarrage, les entrées restées en `uploading` repassent en `queued` :

- **Google Drive** : le worker réutilise l'URI de session sauvegardée, demande à Google la plage
  d'octets déjà reçue et reprend à partir de là. Une session expirée est nettoyée et recréée.
- **S3** : les parts déjà confirmées ne sont pas renvoyées.
- **rsync** : `--partial --inplace` reprend le fichier partiellement transféré.

La base doit persister entre les redémarrages et rester protégée, car les URI de session sont sensibles.

## Dashboard web local

```bash
.venv/bin/freefox-dashboard --config config/local.gdrive.yaml --host 127.0.0.1 --port 8765
```

Ouvrir `http://127.0.0.1:8765`. Pour y accéder depuis un autre PC du réseau, utilisez
`--host 0.0.0.0` puis ouvrez `http://IP_DU_ROBOT:8765` (`hostname -I` donne l'IP).

Le dashboard affiche le statut, la progression, la durée, le débit, l'ETA, les retries, les erreurs,
les fichiers du dossier surveillé et les incidents en cours. Il lit la même base SQLite que le service.

> Le dashboard n'a pas encore d'authentification : ne l'exposez que sur un réseau de confiance,
> jamais sur Internet.

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `FREEFOX_ROBOT_ID` | Remplace `robot_id` du YAML |
| `FREEFOX_CREDENTIALS` | Remplace `drive.credentials_file` |
| `FREEFOX_TOKEN_PATH` | Cache du token OAuth2 (défaut : `/var/lib/freefox/token.json`) |
| `AWS_*` | Chaîne de credentials standard pour S3, voir [s3-storage.md](s3-storage.md) |
