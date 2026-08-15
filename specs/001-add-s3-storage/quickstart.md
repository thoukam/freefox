# Quickstart Validation: S3-Compatible Storage

## Prerequisites

- Python 3.10 or newer on Linux AMD64 or ARM64.
- A checkout with the feature implemented and a writable temporary bag/queue directory.
- For offline validation: development dependencies only.
- For live validation: the S3 extra plus an operator-provisioned AWS bucket or MinIO service and
  externally supplied credentials. Never place credentials in repository files.

Refer to [configuration.md](contracts/configuration.md) for settings,
[storage-backend.md](contracts/storage-backend.md) for delivery behavior, and
[data-model.md](data-model.md) for durable state.

## 1. Offline suite

```bash
python -m pip install -e '.[dev,s3]'
pytest
```

Expected: all tests run without network, Google Drive, SSH, ROS, AWS, or MinIO access. Coverage must
include configuration validation, lazy boto3 import, per-item dispatch, migration, typed failures,
multipart sizing/checkpoint/reconciliation, restart recovery, ambiguous completion, deduplication,
conflict state, integrity confirmation, and deletion safety.

## 2. AWS S3 smoke test

Export credentials through a standard AWS source, prepare a temporary config with `storage.backend:
s3`, the provisioned bucket, optional region/prefix, and no custom endpoint, then run the provided S3
smoke command documented by the implementation.

Expected: a completed test bag is queued before transfer, appears at the configured robot/date key,
has `freefox-blake3` and `freefox-size` metadata, is confirmed complete, and becomes `done`. With
deletion disabled the local bag remains. No credentials or signed request material appear in output.

## 3. MinIO-compatible smoke test

Use the same workflow with a custom HTTPS `endpoint_url`, path addressing, the provisioned bucket,
and an external credential source. Supply a CA bundle when the service uses a private CA.

Expected: the same queue, path, metadata, confirmation, and local-custody behavior as AWS S3. No
provider-specific configuration beyond the documented endpoint/addressing options is required.

## 4. Interruption and restart

Use a bag large enough for several multipart parts. Interrupt connectivity after at least one part is
recorded, stop FreeFox, inspect the SQLite queue to confirm the upload ID and completed parts remain,
restart while the endpoint is still unavailable, then restore connectivity.

Expected: the bag remains local; the item returns to `queued`; the original multipart upload is
reconciled; already matching parts are not retransmitted; delivery resumes within one configured
retry interval; only a fully confirmed object becomes `done`.

Repeat with the provider committing completion while the response is lost. Expected: FreeFox uses
final-object inspection and does not create or upload a duplicate object.

## 5. Existing object outcomes

Upload a test bag, retain its local copy, and queue it again for the same key and identity.

Expected: inspection reports `identical`, the item completes without another transfer, and enabled
integrity verification checks both size and BLAKE3 metadata.

Next, place different content at the intended key and queue the test bag.

Expected: the remote object remains unchanged; the item becomes terminal `conflict`; the local bag
remains even when deletion is enabled; restart and failed-item requeue do not retry it; logs state
that operator action is required without exposing credentials.

Finally, queue two different bags that resolve to the same backend destination key and allow two
workers to claim them concurrently.

Expected: destination-key processing is serialized; at most one upload establishes the object; the
other item re-inspects and becomes `conflict` unless its size and BLAKE3 identity match. Different
content is never overwritten and neither local bag is deleted before its own verified completion.


## 6. Backend binding and migration

Queue unfinished items under Google Drive or rsync, change the active configuration to S3, and add a
new bag.

Expected: old items retain and use their original backend/destination while the new item uses S3.

Upgrade a copy of a legacy database with queued, uploading, failed, and Drive-session rows while its
legacy backend is known.

Expected: migration is transactional and idempotent, preserves all delivery/retry/session state, and
binds every row to that legacy backend. Repeat with ambiguous ownership; startup must stop with an
actionable error and leave the database unchanged.

## 7. Regression and safety checks

Run existing valid Google Drive and rsync configurations unchanged. Exercise successful upload,
transient failure, deduplication, restart, integrity mismatch, and opt-in deletion.

Expected: selection, remote paths, retries, sessions/partials, integrity, and deletion behavior remain
unchanged. Unsupported backend values fail at startup.

Search repository-managed examples, the queue database's printable content, and captured success,
authentication-failure, TLS-failure, and network-failure logs for the test credentials and tokens.

Expected: zero secret values or signed-request material are present; logs still identify the bag,
bucket/key or safe endpoint context, failure category, and retry/operator disposition.

## 8. Deployment matrix

Run the offline suite and one opt-in S3 smoke scenario in supported systemd and container deployments
on Linux AMD64 and ARM64. Send SIGTERM during an active multipart upload.

Expected: dependencies install on both architectures, startup does not require Internet for local
collection/queue operation, signals stop within the deployment timeout, checkpoint state survives,
and the upload resumes safely after restart.

## 9. Acceptance matrix and first-upload timing

Run the SC-001/SC-002 matrix against AWS and MinIO with one object below the multipart threshold and
one object requiring at least three parts, integrity enabled and disabled, interruptions before
transfer/after one part/after committed completion, one multipart restart, identical and conflicting
objects, and concurrent same-key contenders. Record every case; all must preserve the local bag until
verified completion and none may report an incomplete object as successful.

For SC-005, begin timing only after credentials, account/server, and bucket provisioning are complete.
Start from the documented clean configuration and stop when the first test bag reaches verified
`done`. Run once for AWS and once for MinIO; record elapsed time, platform, and any undocumented
operator intervention. Each run must complete in under 15 minutes.
