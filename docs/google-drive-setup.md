# Configuration Google Drive

Ce guide explique comment connecter FreeFox a Google Drive.

Point important: les comptes de service sont tres pratiques pour les robots, mais Google Drive leur impose une limite importante. Pour uploader dans Google Drive avec un compte de service, il faut generalement utiliser un Shared Drive Google Workspace, ou une configuration d'organisation plus avancee. Si vous partagez simplement un dossier "My Drive" personnel avec un compte de service, la creation de dossiers peut fonctionner, mais l'upload de fichiers peut echouer avec:

```text
Service Accounts do not have storage quota.
```

Pour un compte Google Drive personnel, utilisez plutot OAuth2.

## Option A: OAuth2 avec un Drive personnel

C'est l'option recommandee pour tester FreeFox sur votre PC.

### 1. Activer Google Drive API

1. Ouvrir Google Cloud Console.
2. Creer un projet ou selectionner un projet existant.
3. Activer l'API Google Drive.

### 2. Configurer l'ecran de consentement OAuth

1. Aller dans `APIs and services -> OAuth consent screen`.
2. Mettre l'application en mode `Testing` si necessaire.
3. Ajouter votre compte Google dans `Test users`.

Si cette etape est oubliee, Google peut afficher:

```text
Access blocked: freefox has not completed the Google verification process
```

### 3. Creer un client OAuth Desktop

1. Aller dans `APIs and services -> Credentials`.
2. Cliquer sur `Create credentials`.
3. Choisir `OAuth client ID`.
4. Type d'application: `Desktop app`.
5. Telecharger le JSON.

Stocker le fichier localement:

```bash
mkdir -p secrets
mv ~/Downloads/client_secret_*.json secrets/freefox-oauth-client.json
```

Le dossier `secrets/` est ignore par git.

### 4. Creer le dossier Drive cible

1. Ouvrir Google Drive.
2. Creer un dossier, par exemple `freefox-test`.
3. Ouvrir le dossier.
4. Copier l'ID du dossier dans l'URL.

Exemple d'URL:

```text
https://drive.google.com/drive/folders/1AbCDefGhIJklMNopQRstuVwxyz?usp=drive_link
```

L'ID du dossier est uniquement:

```text
1AbCDefGhIJklMNopQRstuVwxyz
```

Ne copiez pas:

```text
?usp=drive_link
```

### 5. Creer une configuration locale

Creer `config/local.gdrive.yaml`:

```bash
cp config/config.example.yaml config/local.gdrive.yaml
```

Exemple:

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
  credentials_file: /home/yves/freefox/secrets/freefox-oauth-client.json
  target_folder_id: "ID_DU_DOSSIER_GOOGLE_DRIVE"
  use_date_subfolder: true

queue_db: /var/lib/freefox/queue.db
log_level: INFO
```

Remplacer `ID_DU_DOSSIER_GOOGLE_DRIVE` par l'ID copie depuis Google Drive.

### 6. Lancer le smoke test Google Drive

```bash
FREEFOX_TOKEN_PATH=/home/yves/freefox/secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Au premier lancement, FreeFox ouvre un navigateur pour l'autorisation Google. Le token OAuth est ensuite sauvegarde dans `FREEFOX_TOKEN_PATH`.

Le script envoie un petit fichier de test vers:

```text
<robot_id>/smoke-tests/<timestamp>/freefox-gdrive-smoke.mcap
```

Exemple:

```text
pc-test/smoke-tests/20260604T210000Z/freefox-gdrive-smoke.mcap
```

Si tout fonctionne, vous verrez un upload termine et une entree `done` dans la file.

## Option B: compte de service avec Shared Drive

Cette option est recommandee pour un deploiement robot/flotte quand le dossier cible se trouve dans un Shared Drive Google Workspace.

### 1. Creer un projet Google Cloud

1. Ouvrir Google Cloud Console.
2. Creer un nouveau projet ou selectionner un projet existant.
3. Activer l'API Google Drive.

### 2. Creer un compte de service

1. Aller dans `IAM and admin -> Service accounts`.
2. Cliquer sur `Create service account`.
3. Utiliser un nom clair, par exemple:

```text
freefox-uploader
```

4. L'ID du compte peut aussi etre:

```text
freefox-uploader
```

5. Description possible:

```text
Upload des bags ROS 2 vers Google Drive pour FreeFox.
```

6. A l'etape des permissions optionnelles, ne selectionnez pas de role projet.
7. Terminer la creation.

FreeFox n'a pas besoin d'un role IAM Google Cloud large. L'acces se donne en partageant le dossier Google Drive cible avec l'email du compte de service.

### 3. Creer une cle JSON

1. Ouvrir le compte de service.
2. Aller dans l'onglet `Keys`.
3. Cliquer sur `Add key -> Create new key`.
4. Choisir `JSON`.
5. Telecharger le fichier JSON.

Ne creez pas une cle API Google simple. FreeFox a besoin d'un JSON OAuth2 ou compte de service.

### 4. Stocker la cle localement

Pour les tests locaux:

```bash
mkdir -p secrets
mv ~/Downloads/your-google-key.json secrets/freefox-service-account.json
```

Pour une installation systemd:

```bash
sudo mkdir -p /etc/freefox
sudo cp secrets/freefox-service-account.json /etc/freefox/credentials.json
sudo chmod 600 /etc/freefox/credentials.json
```

### 5. Partager le dossier Drive

1. Ouvrir Google Drive.
2. Creer ou ouvrir un Shared Drive.
3. Creer un dossier, par exemple `freefox-test`.
4. Copier l'ID du dossier depuis l'URL.
5. Partager le dossier avec l'email du compte de service en role `Editor` ou `Content manager`.

L'email ressemble a:

```text
freefox-uploader@your-project-id.iam.gserviceaccount.com
```

### 6. Tester

```bash
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

## Depannage

Si vous avez une erreur de permission, verifier:

- L'API Google Drive est activee.
- Le chemin du fichier JSON est correct.
- Le dossier Drive est bien partage avec le compte utilise.
- Le role Drive est suffisant.
- `target_folder_id` contient seulement l'ID du dossier, pas l'URL complete.

Si vous voyez:

```text
Service Accounts do not have storage quota.
```

Le dossier est probablement dans un Drive personnel. Utilisez OAuth2 ou un Shared Drive.

Si le script semble bloque, verifiez la connexion reseau et les logs affiches par la commande.
