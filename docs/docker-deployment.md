# Deploiement Docker

Cette methode ajoute Docker comme option de deploiement sans supprimer l'installation systemd existante.

L'idee:

```text
robot
  docker compose
    freefox     -> surveille /bags et upload vers le backend configure
    dashboard  -> expose http://IP_DU_ROBOT:8765
```

Le service `freefox` et le dashboard partagent la meme base SQLite montee depuis l'hote:

```text
/var/lib/freefox/queue.db
```

## Ce que Docker change

Docker ne change pas le code FreeFox.

Il change seulement les chemins vus par l'application:

| Hote robot | Container |
|---|---|
| `/chemin/vers/rosbags` | `/bags` |
| `/var/lib/freefox` | `/var/lib/freefox` |
| `./config/config.docker.yaml` | `/etc/freefox/config.yaml` |
| `./secrets` | `/etc/freefox/secrets` |

Donc dans la config Docker, `watch.directory` doit etre `/bags`.

## Fichiers ajoutes

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `docker-compose.build.yml`
- `.github/workflows/docker-publish.yml`
- `config/config.docker.example.yaml`
- `docs/docker-deployment.md`

Ces fichiers n'impactent pas systemd. Vous pouvez continuer a utiliser `systemd/freefox.service`.

## Checklist nouvelle machine

Pour deployer FreeFox Docker sur une nouvelle machine, il faut:

- Docker et Docker Compose installes
- un dossier de bags local, par exemple `/chemin/vers/rosbags`
- un dossier d'etat persistant, par exemple `./runtime/freefox` ou `/var/lib/freefox`
- un fichier `.env`
- un fichier `config/config.docker.yaml`
- les secrets du backend choisi dans `secrets/`
- le fichier `docker-compose.yml`

Fichiers a copier ou creer localement:

```text
docker-compose.yml
.env
config/config.docker.yaml
secrets/freefox-token.json
secrets/freefox-oauth-client.json
```

Ces fichiers sont locaux a la machine et ne doivent pas etre commits.

Si l'image existe deja dans GHCR, il n'est pas necessaire de cloner tout le code sur le robot.

Pour rsync, les secrets Google ne sont pas necessaires. On utilise plutot une cle
SSH dediee, par exemple:

```text
secrets/freefox_rsync
```

## Preparation sur le robot

Depuis le dossier de deploiement FreeFox:

```bash
cp config/config.docker.example.yaml config/config.docker.yaml
```

Modifier:

```bash
nano config/config.docker.yaml
```

Exemple minimum:

```yaml
robot_id: robot-indoor-001

watch:
  directory: /bags

upload:
  quota_retry_delay: 60.0
  transient_retry_delay: 60.0
  retry_failed_on_start: true
  verify_blake3: true
  deduplicate_by_hash: true

drive:
  credentials_file: /etc/freefox/secrets/freefox-oauth-client.json
  target_folder_id: "ID_DU_DOSSIER_GOOGLE_DRIVE"

queue_db: /var/lib/freefox/queue.db
```

Pour utiliser rsync a la place de Google Drive:

```yaml
storage:
  backend: rsync

rsync:
  destination: user@serveur:/data/freefox
  ssh_command: ssh
  options:
    - --archive
    - --partial
    - --inplace
    - --mkpath
    - --info=progress2
```

Avec `verify_blake3`, FreeFox calcule une empreinte BLAKE3 locale avant upload
et la stocke en base SQLite puis dans les metadonnees du backend.
Avec `deduplicate_by_hash`, un fichier deja present avec le meme BLAKE3 et la
meme taille n'est pas uploade une seconde fois.
Avec rsync, cette verification utilise un petit fichier sidecar
`<filename>.blake3` envoye a cote du bag.

## Deploiement rsync sur un vrai robot

Cette option est utile quand le robot doit envoyer les bags vers un PC de
supervision, un NAS ou un serveur SSH au lieu de Google Drive.

Flux cible:

```text
robot -> FreeFox -> rsync SSH -> machine de destination
```

### Sur la machine de destination

Creer le dossier de stockage:

```bash
sudo mkdir -p /data/freefox
sudo chown -R "$USER:$USER" /data/freefox
```

La destination finale ressemblera a:

```text
/data/freefox/<robot_id>/<YYYY-MM-DD>/<bag.mcap>
/data/freefox/<robot_id>/<YYYY-MM-DD>/<bag.mcap.blake3>
```

### Sur le robot

Installer les outils systeme si FreeFox tourne hors Docker:

```bash
sudo apt update
sudo apt install -y rsync openssh-client
```

Avec Docker, `rsync` et `openssh-client` sont deja installes dans l'image
FreeFox.

Creer une cle SSH dediee au transfert:

```bash
ssh-keygen -t ed25519 -f ./secrets/freefox_rsync -C "freefox-rsync"
```

Copier la cle publique vers la machine de destination:

```bash
ssh-copy-id -i ./secrets/freefox_rsync.pub user@IP_DE_DESTINATION
```

Tester SSH:

```bash
ssh -i ./secrets/freefox_rsync user@IP_DE_DESTINATION
```

Tester rsync seul avant de lancer FreeFox:

```bash
echo test > /tmp/freefox-rsync-test.txt
rsync -av --mkpath -e "ssh -i ./secrets/freefox_rsync" \
  /tmp/freefox-rsync-test.txt \
  user@IP_DE_DESTINATION:/data/freefox/test/
```

### Configuration FreeFox

Dans `config/config.docker.yaml`:

```yaml
storage:
  backend: rsync

rsync:
  destination: user@IP_DE_DESTINATION:/data/freefox
  ssh_command: "ssh -i /etc/freefox/secrets/freefox_rsync -o StrictHostKeyChecking=accept-new"
  options:
    - --archive
    - --partial
    - --inplace
    - --mkpath
    - --info=progress2
  use_date_subfolder: true
```

Garder aussi:

```yaml
upload:
  verify_blake3: true
  deduplicate_by_hash: true
```

### Montage Docker de la cle SSH

Dans `docker-compose.yml`, le dossier `secrets` est monte dans le conteneur:

```yaml
volumes:
  - ${FREEFOX_SECRETS_DIR:-./secrets}:/etc/freefox/secrets:ro
```

La cle locale:

```text
./secrets/freefox_rsync
```

sera donc visible dans le conteneur comme:

```text
/etc/freefox/secrets/freefox_rsync
```

### Lancement et verification

Lancer FreeFox:

```bash
docker compose up -d
```

Voir les logs:

```bash
docker compose logs -f freefox
```

Verifier la destination:

```bash
ssh user@IP_DE_DESTINATION "find /data/freefox -type f | sort | tail -20"
```

Verifier la file depuis le robot:

```bash
docker compose exec freefox python scripts/queue_status.py /var/lib/freefox/queue.db --limit 10
```

Un transfert valide doit afficher:

```text
STATUT: done
INTEGRITE: OK
```

Creer les dossiers persistants:

```bash
mkdir -p secrets
sudo mkdir -p /var/lib/freefox
sudo chown -R "$(id -u):$(id -g)" /var/lib/freefox
```

Creer le fichier d'environnement Docker:

```bash
cp .env.example .env
nano .env
```

Exemple:

```text
FREEFOX_IMAGE=ghcr.io/thoukam/freefox:latest
FREEFOX_UID=1000
FREEFOX_GID=1000
FREEFOX_BAGS_DIR=/chemin/vers/rosbags
FREEFOX_STATE_DIR=/var/lib/freefox
FREEFOX_CONFIG=./config/config.docker.yaml
FREEFOX_SECRETS_DIR=./secrets
FREEFOX_DASHBOARD_PORT=8765
```

Mettre les identifiants Google dans `secrets/`:

```bash
cp /chemin/vers/freefox-oauth-client.json secrets/freefox-oauth-client.json
```

Le dossier `secrets/` est ignore par git.

## OAuth2 et token

Pour un robot headless, il est plus simple de preparer le token avant.

Sur une machine avec navigateur:

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Puis copier `secrets/freefox-token.json` sur le robot dans:

```text
./secrets/freefox-token.json
```

Dans Docker, ce token sera vu comme:

```text
/etc/freefox/secrets/freefox-token.json
```

Le `docker-compose.yml` definit deja:

```yaml
FREEFOX_TOKEN_PATH: /etc/freefox/secrets/freefox-token.json
```

## Lancer avec Docker Compose

Sur un robot, Docker telecharge automatiquement l'image si elle n'existe pas encore localement:

```bash
docker compose pull
docker compose up -d
```

Voir les logs:

```bash
docker compose logs -f freefox
```

Pour developper localement depuis le code source, utiliser l'override de build:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

Voir le dashboard:

```text
http://IP_DU_ROBOT:8765
```

Depuis le robot, pour trouver l'IP:

```bash
hostname -I
```

## Arreter

```bash
docker compose down
```

La base SQLite et les tokens restent dans:

```text
/var/lib/freefox
./secrets
```

## Redemarrage automatique

Le compose utilise:

```yaml
restart: unless-stopped
```

Les containers redemarrent donc apres reboot ou crash, sauf si vous les arretez explicitement avec:

```bash
docker compose down
```

## Tester sans casser systemd

Pour tester Docker sans toucher au service systemd:

```bash
sudo systemctl stop freefox
docker compose up
```

Si le test ne convient pas:

```bash
docker compose down
sudo systemctl start freefox
```

La methode Docker ne supprime pas systemd.

## Points d'attention

- Le dashboard n'a pas encore d'authentification: ne pas l'exposer sur Internet.
- Si plusieurs robots ont la meme IP sur des reseaux isoles, chaque dashboard reste accessible uniquement depuis le reseau du robot.
- Pour superviser plusieurs robots en meme temps avec des IP conflictuelles, il faudra plus tard un serveur central ou un agent qui pousse l'etat vers une API centrale.
- Le container doit pouvoir lire le dossier de bags et ecrire dans `/var/lib/freefox`.
- Avec OAuth2, gardez `freefox-token.json` protege.

## Commandes utiles

Etat:

```bash
docker compose ps
```

Logs service:

```bash
docker compose logs -f freefox
```

Logs dashboard:

```bash
docker compose logs -f dashboard
```

Shell dans le container:

```bash
docker compose exec freefox sh
```

Voir la file:

```bash
docker compose exec freefox python scripts/queue_status.py /var/lib/freefox/queue.db
```

## Publication GHCR

Le workflow GitHub Actions `.github/workflows/docker-publish.yml` publie l'image:

```text
ghcr.io/thoukam/freefox
```

Architectures publiees:

```text
linux/amd64
linux/arm64
```

Declenchements:

- push sur `main`
- tag Git `v*`, par exemple `v0.1.0`
- lancement manuel depuis GitHub Actions

Tags Docker produits:

- `latest` sur la branche principale
- nom de branche, par exemple `main`
- SHA court, par exemple `sha-abc1234`
- version semver si tag Git, par exemple `0.1.0` et `0.1`
- tag manuel optionnel via `workflow_dispatch`

Exemple release:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Sur le robot, choisir l'image:

```text
FREEFOX_IMAGE=ghcr.io/thoukam/freefox:0.1.0
```

Apres la premiere publication, verifier la visibilite du package dans GitHub:

```text
GitHub -> Packages -> freefox -> Package settings -> Change visibility -> Public
```

Si le package reste prive, le robot devra faire un `docker login ghcr.io` avant `docker compose pull`.
