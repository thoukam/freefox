# Storage Backend Contract

## Purpose

Workers dispatch each queue item through a registry keyed by its immutable backend identifier. The
contract keeps custody, verification, retry, and logging rules provider-neutral while allowing S3
to persist multipart state. Existing Google Drive and rsync adapters retain their established remote
path and upload behavior.

## Operations and results

Each backend must support these logical operations, whether implemented as protocol methods or
adapter helpers:

1. **Inspect** a destination using the requested path, expected size, and optional BLAKE3 digest.
   Return exactly one result: `missing`, `identical`, or `conflict`. Filename or size alone is not
   sufficient for `identical` when integrity verification is enabled.
2. **Upload** a local path using its immutable destination snapshot, chunk sizing, expected size and
   digest, progress callback, and persisted resumable checkpoint. Never read the whole bag into
   memory.
3. **Confirm** the final remote object. Return success only after the provider confirms existence and
   enabled integrity checks match. The worker marks the queue item done; the backend cannot authorize
   local deletion independently.
4. **Reconcile or clear resumable state** atomically through queue-owned checkpoint operations.
   Progress callbacks describe only provider-confirmed bytes.

An upload result contains the provider-safe location, confirmed size, confirmed content identity
when verification is enabled, and whether an existing identical object satisfied the request.

Before inspection or upload, the worker acquires a process-wide guard keyed by canonical backend
destination identity. It re-inspects after acquiring the guard. This ensures concurrent queue items
cannot both establish different content at one key: the first may upload, while later contenders are
resolved as identical success or terminal conflict. The guard does not replace remote confirmation.


## Failure categories

Backends translate provider exceptions into these stable categories; logs include bag/entry and
non-secret destination context plus the disposition:

| Category | Worker disposition |
|---|---|
| Transient network/service | Preserve local/checkpoint state and defer for the configured transient interval. |
| Throttling or quota | Preserve state and defer for the configured quota interval. |
| Transient credential service | Preserve state and retry with bounded backoff when STS, metadata, web-identity, or credential refresh services are temporarily unavailable. |
| Invalid credentials/authorization | Preserve the bag and fail with actionable credential/access context; never log secrets. |
| Permanent configuration | Preserve the bag and fail without blind provider retries. |
| Invalid resumable session | Inspect the final object, then complete, conflict, or atomically clear/restart as appropriate. |
| Remote conflict | Mark terminal `conflict`; never overwrite, rename, delete locally, or automatically retry. |

SDK-internal retries are bounded so they do not multiply the durable worker retry policy. Unknown
errors use the existing bounded retry path and preserve local custody.

TLS trust or hostname validation errors are permanent configuration failures. TLS verification is
never disabled automatically. A network interruption during connection establishment remains a
transient network failure rather than a certificate failure.

## S3 object identity

The object key is the immutable `remote_path`. Each upload writes user metadata:

- `freefox-blake3`: lowercase BLAKE3 digest when verification is enabled.
- `freefox-size`: decimal source size.

`HeadObject` establishes identity from exact content length plus both metadata values. An object with
matching identity is idempotent success. An existing key with different or missing required identity
is a conflict. Multipart ETags are opaque part identifiers and are never whole-object checksums.

## S3 multipart lifecycle

- Use a single request only where the implementation can still confirm the final object safely;
  otherwise use explicit `CreateMultipartUpload`, `UploadPart`, `ListParts`,
  `CompleteMultipartUpload`, `AbortMultipartUpload`, and `HeadObject` operations.
- Effective part size is the maximum of 5 MiB, the configured chunk size, and the smallest size that
  keeps the object within 10,000 parts. Only the final part may be smaller than 5 MiB.
- Persist the upload ID before sending parts and persist every returned part number/ETag/size before
  treating its bytes as durable progress.
- On restart, list remote parts and reconcile them with the checkpoint. Reuse only parts whose number,
  ETag, and expected size agree; upload the rest.
- Complete with the ordered provider ETags. If completion is ambiguous or the upload ID is invalid,
  inspect the final key before starting or retrying any upload.
- Start a replacement multipart session only when the old session is unusable and the final key is
  missing. Clear the old upload and part records together. Best-effort abort is allowed but failure
  to abort must not discard local custody or falsely complete the item.
- After completion, confirm size and metadata with `HeadObject`; only then return success.

## Backend compatibility

Google Drive keeps its resumable session URI and BLAKE3 metadata semantics. Rsync keeps its partial
transfer behavior. Adapters may internally bridge their existing `exists`, `find_duplicate`, and
`upload` methods to the new inspection/result/error model, but their configuration, remote paths,
retry outcomes, integrity checks, and deletion safety must not regress.
