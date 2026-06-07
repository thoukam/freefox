<p align="center">
  <img src="images/freefox.png" alt="FreeFox" width="420">
</p>

# FreeFox

**Collecte et upload automatique de rosbag ROS 2 vers Google Drive, libre et open source.**

FreeFox est un petit service Linux qui surveille un dossier, detecte les rosbags termines, les place dans une file SQLite persistante, puis les envoie vers Google Drive avec reprise d'upload.

L'objectif est simple: donner a une equipe robotique un outil de collecte de donnees fiable, local, lisible, et sans abonnement.

<p align="center">
  <img src="images/dashboard_freefox_blur.png" alt="Apercu floute du dashboard FreeFox" width="860">
</p>

<p align="center">
  <em>Un apercu volontairement floute du dashboard local.</em>
</p>

```text
Robot -> ros2 bag record -> /bags/ -> FreeFox -> Google Drive
```

## Fonctionnalites

- **Collecte automatique**: tourne comme service systemd, demarre au boot et continue apres redemarrage.
- **Upload resumable**: envoi par chunks, retry automatique, backoff exponentiel.
- **Reprise apres interruption**: les sessions Google Drive resumables sont stockees en SQLite.
- **File persistante**: l'etat des transferts survit aux crashs et redemarrages.
- **Integrite BLAKE3**: empreinte locale stockee en SQLite puis dans les metadonnees Drive.
- **Gestion des doublons**: un contenu deja present avec le meme BLAKE3 n'est pas renvoye.
- **Statut d'integrite**: le dashboard affiche `OK`, `NO` ou `attente` pour chaque transfert.
- **Detection propre des fichiers**: FreeFox attend que la taille du fichier soit stable avant upload.
- **Stockage organise**: les fichiers arrivent sous `<robot_id>/<YYYY-MM-DD>/<filename>`.
- **Dashboard local**: interface web locale pour voir progression, debit, erreurs, fichiers surveilles et incidents.
- **Compatible ROS 2**: fonctionne avec les bags `.mcap` et `.db3`.

## Demarrage rapide

Pour la procedure detaillee, voir [docs/installation.md](docs/installation.md).

```bash
git clone https://github.com/thoukam/freefox
cd freefox

python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cp config/config.example.yaml config/local.gdrive.yaml
nano config/local.gdrive.yaml
```

Lancer le dashboard local:

```bash
.venv/bin/python scripts/dashboard.py --config config/local.gdrive.yaml --host 127.0.0.1 --port 8765
```

Puis ouvrir:

```text
http://127.0.0.1:8765
```

Pour ouvrir le dashboard depuis un autre PC du meme reseau, lancez-le sur l'adresse reseau du robot:

```bash
.venv/bin/python scripts/dashboard.py --config config/local.gdrive.yaml --host 0.0.0.0 --port 8765
```

Puis, depuis le PC client:

```text
http://IP_DU_ROBOT:8765
```

Exemple:

```text
http://192.168.1.42:8765
```

## Installation systemd

```bash
sudo ./install.sh
sudo nano /etc/freefox/config.yaml
sudo systemctl enable --now freefox
journalctl -u freefox -f
```

Le script installe le package Python local, copie la configuration d'exemple, et enregistre `systemd/freefox.service`.

## Deploiement Docker

Docker est disponible comme option de deploiement progressive, sans remplacer systemd.

Voir [docs/docker-deployment.md](docs/docker-deployment.md), notamment la checklist "nouvelle machine".

L'image officielle du projet est publiee sur GHCR:

```text
ghcr.io/thoukam/freefox
```

Elle est construite pour `linux/amd64` et `linux/arm64`.

Le fichier `docker-compose.yml` utilise l'image publiee. Pour developper localement depuis le code source, `docker-compose.build.yml` sert d'override: Docker Compose fusionne les deux fichiers.

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

Pour utiliser l'image GHCR sans build local:

```bash
docker compose pull
docker compose up -d
```

## Google Drive

La procedure complete est dans [docs/google-drive-setup.md](docs/google-drive-setup.md).

Deux modes sont possibles:

- **OAuth2 Desktop**: recommande pour tester avec un Google Drive personnel.
- **Compte de service**: recommande pour un deploiement robot/flotte avec Shared Drive Google Workspace.

Pour un Drive personnel, OAuth2 est le chemin le plus simple.

## Configuration

Voir [`config/config.example.yaml`](config/config.example.yaml).

Parametres principaux:

| Cle | Exemple | Role |
|---|---:|---|
| `robot_id` | `robot-01` | Nom du robot, utilise dans le chemin Drive |
| `watch.directory` | `/home/ros/bags` | Dossier surveille |
| `watch.stable_seconds` | `5.0` | Temps sans modification avant upload |
| `upload.workers` | `1` ou `2` | Nombre d'uploads en parallele |
| `upload.chunk_size` | `8388608` | Taille des chunks resumables |
| `upload.verify_blake3` | `true` | Calcule et stocke l'empreinte BLAKE3 |
| `upload.deduplicate_by_hash` | `true` | Evite de renvoyer un contenu deja present |
| `drive.credentials_file` | `secrets/client.json` | Fichier OAuth2 ou compte de service |
| `drive.target_folder_id` | `...` | ID du dossier Google Drive cible |
| `queue_db` | `/var/lib/freefox/queue.db` | Base SQLite persistante |

Variables d'environnement utiles:

- `FREEFOX_ROBOT_ID`
- `FREEFOX_CREDENTIALS`
- `FREEFOX_TOKEN_PATH`

## Tests locaux

Test sans Google Drive:

```bash
.venv/bin/python scripts/local_smoke.py
```

Test avec Google Drive:

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Voir la file SQLite:

```bash
.venv/bin/python scripts/queue_status.py /var/lib/freefox/queue.db
```

## Architecture

```text
Watcher fichier
    |
    | fichier stable
    v
File SQLite persistante
    |
    | workers d'upload
    v
Backend Google Drive
    |
    v
Dossier Google Drive partage
```

## Developpement

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Point d'entree CLI:

```bash
freefox --config /etc/freefox/config.yaml
```

## Feuille de route

- [ ] Backend S3 / MinIO
- [ ] Backend NAS / rsync
- [ ] Filtres ROS 2 par topic
- [x] Dashboard web local
- [ ] Endpoint metriques Prometheus
- [ ] Configuration multi-robots centralisee

## Licence

Apache 2.0 - utilisation libre, contributions bienvenues.

## Auteur

FreeFox est porte par **YVES THOUKAM**.

Contact: [thoukamy@gmail.com](mailto:thoukamy@gmail.com)
