# Data Model: S3-Compatible Storage

## Overview

The SQLite upload queue remains the durable source of truth. Each item is permanently bound to the
backend and non-secret destination selected when it is queued. S3 multipart checkpoints are stored
in normalized child tables so a process restart can reconcile local state with the provider before
transferring more data.

## Upload Item

The existing `queue` row retains its current identity, paths, retry, progress, integrity, timing,
Drive session, and error fields. The migration adds:

| Field | Type | Rules |
|---|---|---|
| `backend` | TEXT | One of `gdrive`, `rsync`, or `s3`; immutable after insertion and non-null after migration. |
| `destination_json` | TEXT | Canonical JSON containing only the non-secret destination snapshot; immutable after insertion. |

For S3, `destination_json` contains `bucket`, normalized `object_prefix`, `region`, `endpoint_url`,
`profile`, `addressing_style`, `ca_bundle`, and `use_date_subfolder`. Empty optional values are
represented consistently. It must never contain access keys, secret keys, session tokens, signed
URLs, or authorization headers. Existing `remote_path` is the final backend-relative path; for S3
it is the object key including the configured prefix and robot/date grouping.

`status` accepts the existing `queued`, `uploading`, `done`, and `failed` values plus `conflict`.
`conflict` is terminal and is never selected by `next_ready()` or `requeue_failed()`.

### Upload Item transitions

```text
queued -> uploading -> done
   ^          |
   |          +-> queued       retryable/deferred failure or restart
   |          +-> failed       exhausted retries or permanent non-conflict failure
   |          +-> conflict     destination key contains different/unknown content
   +----------+

failed -> queued               only through the existing explicit/startup retry policy
conflict                       operator action only; never automatic requeue
```

An item may become `done` only after backend confirmation and all enabled integrity checks pass.
Local deletion is permitted only after that transition and only when the existing opt-in setting is
enabled. Resetting an interrupted `uploading` row to `queued` must retain its backend, destination,
digest, S3 upload record, and completed-part records.

## S3 Multipart Upload

Table `s3_multipart_uploads` has at most one active row per queue item.

| Field | Type | Rules |
|---|---|---|
| `queue_id` | INTEGER | Primary key and foreign key to `queue(id)` with cascade delete. |
| `upload_id` | TEXT | Provider multipart identifier; required. |
| `bucket` | TEXT | Must equal the item's destination snapshot. |
| `object_key` | TEXT | Must equal the item's immutable `remote_path`. |
| `part_size` | INTEGER | Effective size, at least 5 MiB except for the final part and large enough for at most 10,000 parts. |
| `source_size` | INTEGER | Local size when the session was created. |
| `source_blake3` | TEXT | Expected BLAKE3 identity; required when verification is enabled. |
| `created_at` | REAL | Unix timestamp. |
| `updated_at` | REAL | Unix timestamp updated with checkpoint changes. |

The upload row is committed immediately after `CreateMultipartUpload` succeeds and before any part
is sent. A changed source size or digest makes the session unusable; the local bag is preserved and
the item fails safely rather than completing against stale identity.

## S3 Completed Part

Table `s3_multipart_parts` records locally confirmed parts.

| Field | Type | Rules |
|---|---|---|
| `queue_id` | INTEGER | Foreign key to `s3_multipart_uploads(queue_id)` with cascade delete. |
| `part_number` | INTEGER | Range 1–10,000; part of the composite primary key. |
| `etag` | TEXT | Provider-returned part ETag; required, including its exact provider representation. |
| `size_bytes` | INTEGER | Positive; may be below 5 MiB only for the final part. |
| `updated_at` | REAL | Unix timestamp of the latest confirmation. |

Primary key: (`queue_id`, `part_number`). Each successful `UploadPart` response is upserted and
committed before progress is reported as durable.

## Reconciliation and completion

On claim or restart, S3 lists provider parts for the stored upload ID. Provider state is authoritative
for whether bytes exist remotely, but a part is reusable only when its number, ETag, and expected
size agree. The transaction replaces stale local part rows with the reconciled set; only missing or
invalid parts are retransmitted.

If the provider says the upload ID is missing or invalid, or if completion returns ambiguously,
FreeFox first inspects the final object:

- Matching object size and `freefox-blake3`/`freefox-size` metadata: mark the item `done` and remove
  multipart checkpoints.
- Missing object: clear the unusable session and parts atomically, then create a new session on the
  next safe attempt.
- Existing object with different or missing identity: mark `conflict`, retain the local bag and
  checkpoint evidence, and require operator action.

Successful multipart completion is followed by `HeadObject`. Only exact size and metadata identity
allow `done`; multipart ETags are never treated as whole-file checksums.

## Migration

Migration runs in one SQLite transaction and is additive:

1. Add nullable `backend` and `destination_json` columns, then create the multipart tables and
   indexes if absent.
2. Bind every legacy row to the deployment's explicitly known legacy backend (`gdrive` or `rsync`)
   and snapshot that backend's non-secret destination settings. Preserve status, retries, retry
   timing, progress, digest, Drive session URI, timestamps, and errors.
3. If any legacy row exists and its original backend cannot be determined safely, roll back and stop
   startup with an actionable error. Never infer `s3` for a legacy row.
4. After all rows are populated, enforce application-level non-null validation for new and loaded
   rows. Re-running the migration is idempotent.

No migration deletes or automatically requeues existing work.
