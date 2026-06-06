# Installation

Ce guide explique comment installer FreeFox en local pour les tests, puis comme service systemd sur un robot ou une machine Linux.

## Prerequis

- Linux
- Python 3.10 ou plus recent
- `pip`
- Une configuration Google Drive, documentee dans [google-drive-setup.md](google-drive-setup.md)

Optionnel mais recommande:

- `watchdog`, installe automatiquement par le package Python, pour une surveillance efficace du systeme de fichiers
- `sqlite3`, utile pour inspecter la base de file d'upload

## Installation locale de developpement

Ce mode est recommande sur votre PC pendant les essais.

```bash
git clone https://github.com/thoukam/freefox
cd freefox
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Le package local est installe en mode editable. Quand vous modifiez les fichiers dans `freefox/`, la commande installee utilise directement le code source du repo.

La commande importante est:

```bash
.venv/bin/pip install -e .
```

Ou avec les outils de developpement:

```bash
.venv/bin/pip install -e ".[dev]"
```

`-e` signifie editable. `pip` installe les metadonnees du package et le point d'entree CLI, mais le code Python reste lu depuis ce depot.

Verifier la CLI:

```bash
.venv/bin/freefox --help
```

Lancer les tests:

```bash
.venv/bin/python -m pytest
```

Lancer un smoke test local sans Google Drive:

```bash
.venv/bin/python scripts/local_smoke.py
```

## Fichiers generes par pip

Apres `pip install -e .`, vous pouvez voir des fichiers generes:

```text
freefox.egg-info/
.venv/lib/python3.12/site-packages/freefox-0.1.0.dist-info/
```

Ces fichiers sont crees par `pip` et `setuptools`. Il ne faut pas les modifier a la main.

Modifiez plutot les sources:

```text
freefox/
scripts/
config/
docs/
```

`.venv/` et `*.egg-info/` sont ignores par git.

## Test Google Drive local

Creer une configuration locale:

```bash
cp config/config.example.yaml config/local.gdrive.yaml
```

Modifier `config/local.gdrive.yaml`:

```yaml
robot_id: pc-test

watch:
  directory: /tmp/freefox-bags
  stable_seconds: 2.0
  extensions:
    - .mcap
    - .db3
  ignore_patterns:
    - "*.active"
    - "*.tmp"
    - metadata.yaml

upload:
  workers: 1
  chunk_size: 8388608
  max_retries: 3
  retry_backoff_base: 2.0
  retry_backoff_max: 30.0
  delete_after_upload: false

drive:
  credentials_file: ./secrets/freefox-oauth-client.json
  target_folder_id: "ID_DU_DOSSIER_GOOGLE_DRIVE"
  use_date_subfolder: true

queue_db: /var/lib/freefox/queue.db
log_level: INFO
```

Lancer le smoke test Google Drive:

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Au premier lancement OAuth2, Google ouvre un navigateur pour l'autorisation. Ensuite, le token est ecrit dans `FREEFOX_TOKEN_PATH`.

## Test avec de vrais rosbags

Une fois le smoke test Google Drive valide, vous pouvez tester avec de vrais fichiers rosbag.

Creer le dossier surveille:

```bash
mkdir -p /tmp/freefox-bags
```

Verifier que `config/local.gdrive.yaml` pointe vers ce dossier:

```yaml
watch:
  directory: /tmp/freefox-bags

queue_db: /var/lib/freefox/queue.db
```

Lancer le watcher reel:

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/watch_gdrive.py --config config/local.gdrive.yaml
```

Dans un autre terminal, copier ou creer un vrai rosbag dans `/tmp/freefox-bags`:

```bash
cp /chemin/vers/votre/real_bag.mcap /tmp/freefox-bags/
```

FreeFox attend que la taille du fichier soit stable pendant `watch.stable_seconds`, puis ajoute le fichier a la file et lance l'upload.

Chemin Drive attendu:

```text
<robot_id>/<YYYY-MM-DD>/<filename>
```

Exemple:

```text
pc-test/2026-06-05/real_bag.mcap
```

Inspecter la file locale:

```bash
sqlite3 -header -column /var/lib/freefox/queue.db "SELECT id, local_path, remote_path, status, retries, error FROM queue;"
```

Ou utiliser le script fourni:

```bash
.venv/bin/python scripts/queue_status.py /var/lib/freefox/queue.db
```

Pendant les uploads, `progress_percent` est mis a jour dans SQLite.

Sous systemd, evitez `/tmp/freefox-queue.db` car le service utilise `PrivateTmp=true`. systemd donne alors un `/tmp` prive au service, et vos outils locaux ne voient pas la meme base. Utilisez `/var/lib/freefox/queue.db`.

## Redemarrage et reprise d'upload

FreeFox stocke les informations de reprise Google Drive dans SQLite:

- `upload_session_uri`
- `uploaded_bytes`
- `progress_percent`
- `upload_started_at`
- `upload_finished_at`

Si le service s'arrete pendant un gros upload, l'entree repasse en `queued` au redemarrage. Quand un worker la reprend, il reutilise l'URI de session Google Drive sauvegardee et demande a Google quelle plage d'octets est deja stockee. L'upload reprend depuis le dernier octet confirme.

Points importants:

- La base de file doit persister entre les redemarrages.
- Pour le service, utilisez `/var/lib/freefox/queue.db`.
- Les sessions resumables Google Drive expirent apres un certain temps.
- Si une session expire, FreeFox la nettoie et demarre une nouvelle session.
- L'URI de session est sensible: gardez la base locale et protegee.

## Dashboard web local

Lancer le dashboard:

```bash
.venv/bin/python scripts/dashboard.py --config config/local.gdrive.yaml --host 127.0.0.1 --port 8765
```

Ouvrir:

```text
http://127.0.0.1:8765
```

### Acces depuis un autre PC du reseau

Par defaut, le dashboard ecoute seulement sur `127.0.0.1`: il est donc accessible uniquement depuis la machine qui le lance.

Pour l'ouvrir depuis un PC client avec l'IP du robot, lancez le dashboard sur `0.0.0.0`:

```bash
.venv/bin/python scripts/dashboard.py --config config/local.gdrive.yaml --host 0.0.0.0 --port 8765
```

Trouver l'IP du robot:

```bash
hostname -I
```

Puis ouvrir depuis le PC client:

```text
http://IP_DU_ROBOT:8765
```

Exemple:

```text
http://192.168.1.42:8765
```

Important: le dashboard n'a pas encore d'authentification. Il faut l'exposer uniquement sur un reseau de confiance, pas sur Internet.

Le dashboard affiche:

- statut des transferts
- progression des uploads
- duree des uploads
- debit de transfert
- trafic estime
- ETA des uploads actifs
- retries et erreurs
- lignes recentes de la base SQLite
- fichiers presents dans le dossier surveille
- resume de configuration
- incidents courants

Il lit la meme base SQLite que le watcher. Gardez `scripts/watch_gdrive.py` ou le service systemd en marche, puis ouvrez le dashboard dans un autre terminal.

## Variables d'environnement

FreeFox peut lire ces variables:

| Variable | Role |
|---|---|
| `FREEFOX_ROBOT_ID` | Remplace `robot_id` du YAML |
| `FREEFOX_CREDENTIALS` | Remplace `drive.credentials_file` du YAML |
| `FREEFOX_TOKEN_PATH` | Chemin du cache OAuth2 |

Exemple:

```bash
FREEFOX_ROBOT_ID=pc-test \
FREEFOX_CREDENTIALS=./secrets/freefox-oauth-client.json \
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/freefox --config config/local.gdrive.yaml
```
