# Deploiement Docker

Cette methode ajoute Docker comme option de deploiement sans supprimer l'installation systemd existante.

L'idee:

```text
robot
  docker compose
    freefox     -> surveille /bags et upload vers Google Drive
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
- les secrets Google dans `secrets/`
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

drive:
  credentials_file: /etc/freefox/secrets/freefox-oauth-client.json
  target_folder_id: "ID_DU_DOSSIER_GOOGLE_DRIVE"

queue_db: /var/lib/freefox/queue.db
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
