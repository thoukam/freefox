# Configuration Contract: S3-Compatible Storage

## Backend selection

`storage.backend` accepts exactly `gdrive`, `rsync`, or `s3` and defaults to the existing `gdrive`
behavior when omitted. Unsupported values cause an actionable startup error; FreeFox never silently
falls back to another backend. The selected value applies only to newly queued items.

Existing Google Drive and rsync keys, defaults, environment overrides, and behavior remain valid.
An installation that never selects `s3` must not import boto3 or require the optional S3 extra.

## S3 YAML surface

```yaml
storage:
  backend: s3

s3:
  bucket: robot-bags                 # required when backend is s3
  object_prefix: freefox             # optional, default ""
  region: eu-west-3                  # optional
  endpoint_url: https://minio.example.net  # optional; omit for AWS S3
  profile: robot-uploader            # optional AWS shared-config profile
  addressing_style: path             # auto | path | virtual; default auto for AWS, path for custom endpoints
  ca_bundle: /etc/freefox/minio-ca.pem     # optional trusted CA bundle
  use_date_subfolder: true           # default true
```

All fields are non-secret. `bucket` must be non-empty. `object_prefix` is normalized by stripping
leading/trailing slashes and rejecting empty path segments, `.` and `..`. `endpoint_url`, when set,
must be an absolute HTTP(S) URL with a host; TLS certificate verification is always enabled for
HTTPS. `addressing_style` accepts only `auto`, `path`, or `virtual`. `ca_bundle`, when set, must name
a readable file. Invalid settings fail startup before queue processing begins.

With no `endpoint_url`, the client uses standard AWS S3 resolution and automatic addressing. With a
custom endpoint, operations target that S3-compatible service and default to path addressing. All
requests use Signature Version 4. FreeFox does not create buckets or change bucket policy,
encryption, lifecycle, retention, or IAM configuration.

## Credentials

FreeFox delegates credential resolution to the standard boto3/AWS provider chain. Supported sources
include environment variables, the optional named profile and external shared credentials/config
files, web identity, and container or instance roles. Refreshable credentials remain owned by the
SDK.

FreeFox YAML and examples must not accept access-key, secret-key, session-token, signed-request, or
inline credentials fields. Those values must never be stored in SQLite or emitted in logs. Error
messages may identify the profile, bucket, endpoint host, region, object key, and credential source
category, but must redact authorization material, query signatures, and token values.

## Destination binding and upgrades

At enqueue time FreeFox stores the selected backend and a canonical, non-secret destination snapshot
with the queue item. Later configuration changes affect only new items; workers construct or select
the backend from each claimed item's binding.

When upgrading a database whose rows predate backend binding, startup must be given enough context
to bind those rows to the deployment's active legacy backend. A known existing `gdrive` or `rsync`
configuration is sufficient. If ownership is ambiguous—especially when the current selection is
`s3`—startup stops and explains how to identify the legacy backend; it does not redirect old items.

## Dependency and deployment contract

S3 support is installed with the project `s3` extra (`boto3>=1.28`). Selecting `s3` without that
extra produces an actionable startup error. The client path must support Python 3.10+, Linux AMD64
and ARM64, systemd services, and containers. Credential/config/CA files are supplied through normal
host paths or read-only mounts; secrets are not baked into images.
