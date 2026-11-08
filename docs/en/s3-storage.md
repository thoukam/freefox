**English** · [Français](../fr/s3-storage.md)

# AWS S3 and MinIO-compatible storage

Install the optional extra with `pip install -e ".[s3]"`, then select `storage.backend: s3`.
The bucket must already exist. FreeFox does not create buckets, IAM policies or retention rules.

```yaml
storage:
  backend: s3
s3:
  bucket: robot-bags
  object_prefix: freefox
  region: eu-west-3
  endpoint_url: ""          # leave empty for AWS, explicit URL for MinIO
  addressing_style: auto    # path is the default with a custom endpoint
  ca_bundle: /etc/freefox/minio-ca.pem
  use_date_subfolder: true
```

## External credentials

FreeFox uses the standard boto3 credential chain and refuses keys in the YAML:

- the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` variables, plus `AWS_SESSION_TOKEN` if needed,
- an external shared profile (`AWS_PROFILE`, `~/.aws/credentials`, `~/.aws/config`),
- web identity (`AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_ROLE_ARN`),
- task, container or instance roles with refreshable credentials.

Under systemd, put the variables in `/etc/freefox/aws.env`, owned by root and readable by the service
group (`0640`). In a container, prefer a read-only secret or volume, or a workload role. Never commit
these files. Mount a private MinIO CA read-only as well. Never disable TLS verification.

## Validation

```bash
AWS_PROFILE=robot .venv/bin/python scripts/s3_smoke.py \
  --config config/local.s3.yaml --file /tmp/test.mcap
```

The script checks the object's size and BLAKE3. Use an isolated test prefix.

## Behaviour

- **Durable multipart upload**: the service sends each bag as a multipart upload. The `UploadId` and
  the confirmed parts are persisted in SQLite, so an upload can resume after a restart without
  sending finished parts again.
- **Metadata**: the BLAKE3 digest and size are stored in object metadata (`freefox-blake3`,
  `freefox-size`) and checked again after completion.
- **Part size**: at least 5 MiB, increased automatically to stay under S3's 10,000-part limit.
- **Duplicates**: if an object with the same size and BLAKE3 already exists, the transfer is marked
  done without uploading.
- **Conflicts**: if an object exists at the same key with different content, FreeFox does not
  overwrite it. The transfer moves to `conflict` and needs an operator.
- **Logs**: signatures, keys and tokens in error messages are redacted.

## Testing resume

1. Run FreeFox with `storage.backend: s3` and drop in a file larger than 50 MiB.
2. Stop the service during the upload (`systemctl stop freefox` or `Ctrl+C`).
3. Start it again: the entry is requeued and continues from the parts already confirmed.
4. Check with `freefox-status` that the entry ends up `done`.
