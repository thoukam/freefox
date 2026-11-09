**English** · [Français](../fr/google-drive-setup.md)

# Google Drive setup

This guide shows how to connect FreeFox to Google Drive.

> **Read this first.** Service accounts are handy for robots, but they have no storage quota of their
> own. To upload with a service account, the target folder must live in a **Google Workspace Shared
> Drive**. If you only share a personal "My Drive" folder with a service account, folder creation may
> work, but uploads fail with:
>
> ```text
> Service Accounts do not have storage quota.
> ```
>
> For a personal Google account, use **OAuth2** (option A).

## Option A: OAuth2 with a personal Drive

This is the recommended option for trying FreeFox on your PC.

### 1. Enable the Google Drive API

1. Open the Google Cloud Console.
2. Create a project or select an existing one.
3. Enable the Google Drive API.

### 2. Configure the OAuth consent screen

1. Go to `APIs and services -> OAuth consent screen`.
2. Set the app to `Testing` mode if needed.
3. Add your Google account under `Test users`.

If you skip this step, Google may show:

```text
Access blocked: freefox has not completed the Google verification process
```

### 3. Create a "Desktop" OAuth client

1. Go to `APIs and services -> Credentials`.
2. Click `Create credentials`, then `OAuth client ID`.
3. Application type: `Desktop app`.
4. Download the JSON and store it locally:

```bash
mkdir -p secrets
mv ~/Downloads/client_secret_*.json secrets/freefox-oauth-client.json
```

The `secrets/` folder is ignored by git.

### 4. Create the target Drive folder

1. Open Google Drive and create a folder, for example `freefox-test`.
2. Open the folder and copy its ID from the URL.

For example, in this URL:

`https://drive.google.com/drive/folders/`**`1AbCDefGhIJklMNopQRstuVwxyz`**`?usp=drive_link`

the folder ID is **`1AbCDefGhIJklMNopQRstuVwxyz`**: the part after `folders/`, without `?usp=drive_link`.

### 5. Configure FreeFox

```bash
cp config/config.example.yaml config/local.gdrive.yaml
```

```yaml
robot_id: pc-test

watch:
  directory: /tmp/freefox-bags
  stable_seconds: 2.0

storage:
  backend: gdrive

drive:
  credentials_file: ./secrets/freefox-oauth-client.json
  target_folder_id: "1AbCDefGhIJklMNopQRstuVwxyz"
  use_date_subfolder: true

queue_db: /var/lib/freefox/queue.db
```

### 6. Run the smoke test

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

On the first run, a browser opens for Google consent, and the token is saved to
`FREEFOX_TOKEN_PATH`. The script uploads a small test file to:

```text
<robot_id>/smoke-tests/<timestamp>/freefox-gdrive-smoke.mcap
```

If everything works, the upload completes and the queue entry becomes `done`.

> **Headless robot?** Generate the token on a machine with a browser, then copy
> `freefox-token.json` to the robot. See [docker-deployment.md](docker-deployment.md#oauth2-and-token).

## Option B: service account with a Shared Drive

Recommended for robot or fleet deployments when the target folder is in a Google Workspace Shared
Drive.

### 1. Create the service account

1. In the Google Cloud Console, enable the Google Drive API on the project.
2. Go to `IAM and admin -> Service accounts`, then `Create service account`.
3. Suggested name: `freefox-uploader`. Description: "Uploads ROS 2 bags to Google Drive".
4. **Do not grant any project role.** FreeFox needs no IAM role: you grant access by sharing the
   Drive folder with the service account's e-mail.

### 2. Create a JSON key

1. Open the service account, `Keys` tab.
2. `Add key -> Create new key`, format `JSON`.

Do not use a plain Google API key. FreeFox needs an OAuth2 or service-account JSON file.

### 3. Install the key

Local tests:

```bash
mkdir -p secrets
mv ~/Downloads/your-google-key.json secrets/freefox-service-account.json
```

systemd service:

```bash
sudo install -m 600 secrets/freefox-service-account.json /etc/freefox/credentials.json
```

If the service does not run as root, make its user the owner of the file
(`sudo chown <user> /etc/freefox/credentials.json`).

### 4. Share the folder

1. Create or open a Shared Drive, then a folder inside it.
2. Copy the folder ID from the URL.
3. Share the folder with the service account e-mail as `Content manager` (or `Editor`):

```text
freefox-uploader@your-project-id.iam.gserviceaccount.com
```

### 5. Test

```bash
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

## Troubleshooting

If you get a permission error, check that:

- the Google Drive API is enabled,
- the JSON file path is correct,
- the Drive folder is shared with the account in use, with a sufficient role,
- `target_folder_id` holds only the ID, not the full URL.

`Service Accounts do not have storage quota.` means the folder is in a personal Drive. Use OAuth2 or
a Shared Drive.

Google quota exceeded: FreeFox defers the transfer and retries after `upload.quota_retry_delay`
seconds, without counting it as a failure.

If the script seems stuck, check the network connection and the logs it prints.
