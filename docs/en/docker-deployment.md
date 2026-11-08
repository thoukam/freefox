**English** · [Français](../fr/docker-deployment.md)

# Docker deployment

Docker is a deployment option in addition to systemd. It does not replace it, and both can live on
the same machine.

```text
robot
  docker compose
    freefox    -> watches /bags and uploads to the configured backend
    dashboard  -> serves http://ROBOT_IP:8765
```

Both containers share the same SQLite database, mounted from the host (`/var/lib/freefox/queue.db`).

## What Docker changes

The FreeFox code is the same. Only the paths the application sees change.

| Robot host | Container |
|---|---|
| `FREEFOX_BAGS_DIR` (e.g. `/home/ros/bags`) | `/bags` |
| `FREEFOX_STATE_DIR` (e.g. `/var/lib/freefox`) | `/var/lib/freefox` |
| `FREEFOX_CONFIG` (e.g. `./config/config.docker.yaml`) | `/etc/freefox/config.yaml` |
| `FREEFOX_SECRETS_DIR` (e.g. `./secrets`) | `/etc/freefox/secrets` (read-only) |

So in the Docker config, `watch.directory` must be `/bags`, and secret paths start with
`/etc/freefox/secrets/`.

## New machine checklist

- Docker and Docker Compose installed
- a local bags folder
- a persistent state folder
- the following local files, **never committed**:

```text
docker-compose.yml
.env
config/config.docker.yaml
secrets/…        # credentials for the chosen backend
```

If the image is already published on GHCR, you do not need to clone the whole repository onto the
robot. These files are enough.

## Preparation

```bash
mkdir -p secrets
sudo mkdir -p /var/lib/freefox
sudo chown -R "$(id -u):$(id -g)" /var/lib/freefox

cp .env.example .env
cp config/config.docker.example.yaml config/config.docker.yaml
```

Example `.env`:

```text
FREEFOX_IMAGE=ghcr.io/thoukam/freefox:latest
FREEFOX_UID=1000
FREEFOX_GID=1000
FREEFOX_BAGS_DIR=/home/ros/bags
FREEFOX_STATE_DIR=/var/lib/freefox
FREEFOX_CONFIG=./config/config.docker.yaml
FREEFOX_SECRETS_DIR=./secrets
FREEFOX_DASHBOARD_PORT=8765
```

Minimal `config/config.docker.yaml`:

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

queue_db: /var/lib/freefox/queue.db
```

Then pick a backend below.

## Google Drive backend

```yaml
storage:
  backend: gdrive

drive:
  credentials_file: /etc/freefox/secrets/freefox-oauth-client.json
  target_folder_id: "GOOGLE_DRIVE_FOLDER_ID"
```

```bash
cp /path/to/freefox-oauth-client.json secrets/freefox-oauth-client.json
```

### OAuth2 and token

A headless robot cannot open a browser, so prepare the token on another machine:

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Then copy `secrets/freefox-token.json` into `./secrets/` on the robot. `docker-compose.yml` already
sets `FREEFOX_TOKEN_PATH: /etc/freefox/secrets/freefox-token.json`.

See also [google-drive-setup.md](google-drive-setup.md).

## rsync on a real robot

Use this to send bags to a monitoring PC, a NAS or an SSH server:

```text
robot -> FreeFox -> rsync over SSH -> destination machine
```

`rsync` and `openssh-client` are already installed in the image. Outside Docker, run
`sudo apt install -y rsync openssh-client`.

### On the destination machine

```bash
sudo mkdir -p /data/freefox
sudo chown -R "$USER:$USER" /data/freefox
```

Files will land under:

```text
/data/freefox/<robot_id>/<YYYY-MM-DD>/<bag.mcap>
/data/freefox/<robot_id>/<YYYY-MM-DD>/<bag.mcap.blake3>
```

### On the robot

Create a dedicated SSH key and authorise it on the destination:

```bash
ssh-keygen -t ed25519 -f ./secrets/freefox_rsync -C "freefox-rsync"
ssh-copy-id -i ./secrets/freefox_rsync.pub user@DESTINATION_IP
ssh -i ./secrets/freefox_rsync user@DESTINATION_IP      # test
```

Test rsync on its own before starting FreeFox:

```bash
echo test > /tmp/freefox-rsync-test.txt
rsync -av --mkpath -e "ssh -i ./secrets/freefox_rsync" \
  /tmp/freefox-rsync-test.txt user@DESTINATION_IP:/data/freefox/test/
```

### Configuration

```yaml
storage:
  backend: rsync

rsync:
  destination: user@DESTINATION_IP:/data/freefox
  ssh_command: "ssh -i /etc/freefox/secrets/freefox_rsync -o StrictHostKeyChecking=accept-new"
  options:
    - --archive
    - --partial
    - --inplace
    - --mkpath
    - --info=progress2
  use_date_subfolder: true

upload:
  verify_blake3: true
  deduplicate_by_hash: true
```

The local key `./secrets/freefox_rsync` is visible in the container as
`/etc/freefox/secrets/freefox_rsync`. With BLAKE3 enabled, FreeFox sends a `<filename>.blake3`
sidecar next to each bag, so it can detect duplicates without reading the remote bag again.

### Verification

```bash
docker compose up -d
docker compose logs -f freefox
ssh user@DESTINATION_IP "find /data/freefox -type f | sort | tail -20"
docker compose exec freefox python scripts/queue_status.py /var/lib/freefox/queue.db --limit 10
```

For a successful transfer, the `STATUT` (status) column shows `done` and the `INTEGRITE` (integrity) column shows `OK`.

## S3 / MinIO backend

The image includes the S3 extra, for both `linux/amd64` and `linux/arm64`. Mount AWS files or a
private CA read-only into `/etc/freefox/secrets`, or inject `AWS_*` variables from your secret
manager. Never put keys in the YAML.

```yaml
storage:
  backend: s3
s3:
  bucket: robot-bags
  endpoint_url: https://minio.example.net
  addressing_style: path
  ca_bundle: /etc/freefox/secrets/minio-ca.pem
```

Details: [s3-storage.md](s3-storage.md).

## Start, stop, restart

```bash
docker compose pull          # fetch the GHCR image
docker compose up -d
docker compose logs -f freefox
```

Dashboard: `http://ROBOT_IP:8765` (`hostname -I` shows the IP).

To develop from source, use the build override. Docker Compose merges it with the main file:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

Stop:

```bash
docker compose down
```

The SQLite database and tokens stay in `/var/lib/freefox` and `./secrets`. Because of
`restart: unless-stopped`, the containers restart after a reboot or a crash unless you stop them
explicitly.

## Try it without breaking systemd

```bash
sudo systemctl stop freefox
docker compose up
# if you are not happy with it:
docker compose down
sudo systemctl start freefox
```

## Things to watch

- The dashboard has no authentication yet. Do not expose it on the Internet.
- The container must be able to read the bags folder and write to `/var/lib/freefox`
  (`FREEFOX_UID` / `FREEFOX_GID`).
- With OAuth2, keep `freefox-token.json` protected.
- Each dashboard only sees its own robot. Monitoring a fleet, including robots with clashing IPs on
  isolated networks, will need a central server. It is on the roadmap.

## Useful commands

| Command | Purpose |
|---|---|
| `docker compose ps` | Container status |
| `docker compose logs -f freefox` | Service logs |
| `docker compose logs -f dashboard` | Dashboard logs |
| `docker compose exec freefox sh` | Shell inside the container |
| `docker compose exec freefox python scripts/queue_status.py /var/lib/freefox/queue.db` | Queue status |

## GHCR publishing

The `.github/workflows/docker-publish.yml` workflow publishes `ghcr.io/thoukam/freefox` for
`linux/amd64` and `linux/arm64`.

It runs on a push to `main`, on a `v*` tag, or manually from GitHub Actions, and produces these
Docker tags:

- `latest` on the default branch,
- the branch name (`main`),
- the short SHA (`sha-abc1234`),
- the semver version for a Git tag (`0.2.0`, `0.2`),
- an optional manual tag (`workflow_dispatch`).

To publish a release:

```bash
git tag v0.2.0
git push origin v0.2.0
```

On the robot, pin the version in `.env`: `FREEFOX_IMAGE=ghcr.io/thoukam/freefox:0.2.0`.

If the GHCR package is private, the robot must run `docker login ghcr.io` before
`docker compose pull`. To make it public: `GitHub -> Packages -> freefox -> Package settings ->
Change visibility`.
