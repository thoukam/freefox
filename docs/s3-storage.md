# Stockage AWS S3 et MinIO-compatible

Installez l’extra optionnel avec `pip install -e ".[s3]"`, puis sélectionnez `storage.backend: s3`.
Le bucket doit exister; FreeFox ne crée ni bucket, ni politique IAM, ni règle de rétention.

```yaml
storage:
  backend: s3
s3:
  bucket: robot-bags
  object_prefix: freefox
  region: eu-west-3
  endpoint_url: ""          # omettre pour AWS, URL explicite pour MinIO
  addressing_style: auto    # path est le défaut avec un endpoint personnalisé
  ca_bundle: /etc/freefox/minio-ca.pem
  use_date_subfolder: true
```

## Credentials externes

FreeFox utilise la chaîne standard boto3 sans accepter de clé dans le YAML:

- variables `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` et éventuellement `AWS_SESSION_TOKEN`;
- profil partagé externe (`AWS_PROFILE`, `~/.aws/credentials`, `~/.aws/config`);
- web identity (`AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_ROLE_ARN`);
- rôles de tâche/conteneur ou d’instance avec credentials rafraîchissables.

Sous systemd, placez les variables dans `/etc/freefox/aws.env`, appartenant à root et lisible par le
groupe du service (`0640`). Dans un conteneur, préférez un secret/volume en lecture seule ou un rôle
de workload. Ne committez jamais ces fichiers. Un CA privé MinIO est également monté en lecture seule;
la vérification TLS ne doit pas être désactivée.

## Validation

```bash
AWS_PROFILE=robot .venv/bin/python scripts/s3_smoke.py \
  --config config/local.s3.yaml --file /tmp/test.mcap
```

Le script confirme l’objet par taille et BLAKE3. Utilisez un préfixe de test isolé. Pour tester reprise,
conflit et interruptions, suivez `specs/001-add-s3-storage/quickstart.md`.
