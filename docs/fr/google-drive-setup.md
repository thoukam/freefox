[English](../en/google-drive-setup.md) · **Français**

# Configuration Google Drive

Ce guide explique comment connecter FreeFox à Google Drive.

> **À savoir avant de commencer.** Les comptes de service sont pratiques pour les robots, mais ils
> n'ont pas de quota de stockage propre. Pour uploader avec un compte de service, le dossier cible doit
> se trouver dans un **Shared Drive Google Workspace**. Si vous partagez simplement un dossier
> « My Drive » personnel avec un compte de service, la création de dossiers peut fonctionner, mais
> l'upload échoue avec :
>
> ```text
> Service Accounts do not have storage quota.
> ```
>
> Pour un compte Google personnel, utilisez **OAuth2** (option A).

## Option A : OAuth2 avec un Drive personnel

C'est l'option recommandée pour tester FreeFox sur votre PC.

### 1. Activer l'API Google Drive

1. Ouvrir la Google Cloud Console.
2. Créer un projet ou sélectionner un projet existant.
3. Activer l'API Google Drive.

### 2. Configurer l'écran de consentement OAuth

1. Aller dans `APIs and services -> OAuth consent screen`.
2. Mettre l'application en mode `Testing` si nécessaire.
3. Ajouter votre compte Google dans `Test users`.

Si cette étape est oubliée, Google peut afficher :

```text
Access blocked: freefox has not completed the Google verification process
```

### 3. Créer un client OAuth « Desktop »

1. Aller dans `APIs and services -> Credentials`.
2. Cliquer sur `Create credentials`, puis `OAuth client ID`.
3. Type d'application : `Desktop app`.
4. Télécharger le JSON et le ranger localement :

```bash
mkdir -p secrets
mv ~/Downloads/client_secret_*.json secrets/freefox-oauth-client.json
```

Le dossier `secrets/` est ignoré par git.

### 4. Créer le dossier Drive cible

1. Ouvrir Google Drive et créer un dossier, par exemple `freefox-test`.
2. Ouvrir le dossier et copier son ID depuis l'URL.

```text
https://drive.google.com/drive/folders/1AbCDefGhIJklMNopQRstuVwxyz?usp=drive_link
                                       └──────── ID du dossier ───────┘
```

Ne copiez que l'ID, sans `?usp=drive_link`.

### 5. Configurer FreeFox

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

### 6. Lancer le smoke test

```bash
FREEFOX_TOKEN_PATH=./secrets/freefox-token.json \
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

Au premier lancement, un navigateur s'ouvre pour l'autorisation Google, puis le token est sauvegardé
dans `FREEFOX_TOKEN_PATH`. Le script envoie un petit fichier de test vers :

```text
<robot_id>/smoke-tests/<timestamp>/freefox-gdrive-smoke.mcap
```

Si tout fonctionne, l'upload se termine et l'entrée passe en `done` dans la file.

> **Robot sans écran ?** Générez le token sur une machine avec navigateur, puis copiez
> `freefox-token.json` sur le robot. Voir [docker-deployment.md](docker-deployment.md#oauth2-et-token).

## Option B : compte de service avec Shared Drive

Recommandée pour un déploiement robot ou flotte quand le dossier cible est dans un Shared Drive
Google Workspace.

### 1. Créer le compte de service

1. Dans la Google Cloud Console, activer l'API Google Drive sur le projet.
2. Aller dans `IAM and admin -> Service accounts`, puis `Create service account`.
3. Nom suggéré : `freefox-uploader`. Description : « Upload des bags ROS 2 vers Google Drive ».
4. **Ne sélectionnez aucun rôle projet.** FreeFox n'a pas besoin de rôle IAM : l'accès est donné en
   partageant le dossier Drive avec l'e-mail du compte de service.

### 2. Créer une clé JSON

1. Ouvrir le compte de service, onglet `Keys`.
2. `Add key -> Create new key`, format `JSON`.

N'utilisez pas une simple clé API Google : FreeFox a besoin d'un JSON OAuth2 ou compte de service.

### 3. Installer la clé

Tests locaux :

```bash
mkdir -p secrets
mv ~/Downloads/your-google-key.json secrets/freefox-service-account.json
```

Service systemd :

```bash
sudo install -m 600 secrets/freefox-service-account.json /etc/freefox/credentials.json
```

Si le service ne tourne pas en root, donnez la propriété du fichier à son utilisateur
(`sudo chown <utilisateur> /etc/freefox/credentials.json`).

### 4. Partager le dossier

1. Créer ou ouvrir un Shared Drive, puis un dossier dedans.
2. Copier l'ID du dossier depuis l'URL.
3. Partager le dossier avec l'e-mail du compte de service, rôle `Content manager` (ou `Editor`) :

```text
freefox-uploader@your-project-id.iam.gserviceaccount.com
```

### 5. Tester

```bash
.venv/bin/python scripts/gdrive_smoke.py --config config/local.gdrive.yaml
```

## Dépannage

En cas d'erreur de permission, vérifiez que :

- l'API Google Drive est activée,
- le chemin du fichier JSON est correct,
- le dossier Drive est bien partagé avec le compte utilisé, avec un rôle suffisant,
- `target_folder_id` contient uniquement l'ID, pas l'URL complète.

`Service Accounts do not have storage quota.` : le dossier est dans un Drive personnel. Utilisez
OAuth2 ou un Shared Drive.

Quota Google dépassé : FreeFox met le transfert en attente et réessaie après
`upload.quota_retry_delay` secondes, sans le compter comme un échec.

Si le script semble bloqué, vérifiez la connexion réseau et les logs affichés.
