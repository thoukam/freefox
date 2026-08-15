# Research: S3-Compatible Storage

## S3 client and dependency

**Decision**: Reuse the existing optional `boto3>=1.28` extra and its low-level S3 client, loaded
lazily only for `storage.backend: s3`. Use explicit create, upload-part, list-parts, complete, abort,
and head operations rather than a high-level transfer manager.

**Rationale**: Explicit operations expose the upload ID and part ETags FreeFox must persist across
process restarts. Boto3 supports AWS credential discovery and S3-compatible endpoints, is pure
Python on supported platforms, and is already declared by the project.

**Alternatives considered**: The high-level boto3 transfer manager hides restart state; the MinIO
SDK adds another provider-specific dependency and does not improve AWS credential integration;
AWS CRT acceleration adds an unnecessary native dependency and ARM64 packaging risk.

## Multipart sizing and restart recovery

**Decision**: Use multipart upload above the effective part size. Compute that size as at least
5 MiB, at least the configured chunk size, and large enough to keep the upload at or below 10,000
parts. Persist the upload ID immediately and each successful part number, ETag, and size atomically.
On restart, list provider parts, reconcile them with persisted state, and upload only missing or
invalid parts.

**Rationale**: This supports the clarified cross-restart resumption requirement without holding the
entire rosbag in memory or resending confirmed parts. S3 requires the ordered part-number/ETag list
for completion.

**Alternatives considered**: Encoding all state in the existing Drive session URI is fragile and
unnormalized; storing only an upload ID loses progress details; always restarting wastes bandwidth.

## Expired sessions and ambiguous completion

**Decision**: If the provider reports an invalid or missing multipart session, first inspect the
final object. Accept it only when size and FreeFox digest metadata match. Otherwise clear only the
S3 session/parts atomically and start a new upload. After an ambiguous complete response, inspect
the final object before retrying or creating any new session.

**Rationale**: A completion response can be lost after the provider commits the object. Inspecting
first prevents duplicate transfer and never mistakes a partial upload for a completed object.

**Alternatives considered**: Blindly restarting can duplicate work; treating a lost response as
success violates verified delivery; keeping a permanently invalid session stalls the queue.

## Integrity, deduplication, and conflict identity

**Decision**: Store `freefox-blake3` and `freefox-size` as S3 object user metadata. Before upload and
after completion, use object inspection to compare exact object size and metadata. Matching content
is idempotent success; an existing key with different or missing identity is a terminal conflict.
Never use a multipart ETag as the whole-file checksum.

**Rationale**: BLAKE3 plus size matches current FreeFox semantics and is portable across AWS S3 and
MinIO. Multipart ETags do not represent a whole-object MD5.

**Alternatives considered**: Filename or size alone cannot establish identity; automatic overwrite
or rename contradicts the clarified conflict policy; provider-specific checksum features can be
supplemental but are not consistently portable across MinIO deployments.

## Failure classification and retry ownership

**Decision**: Add backend-neutral exception categories for transient network/service failures,
throttling/quota, remote conflicts, invalid sessions, and permanent configuration failures. Split
authentication into transient credential-service failures (such as unavailable STS, metadata,
web-identity, or refresh services), which retry with bounded backoff, and permanent invalid-credential
or authorization failures, which stop automatically with actionable context. Classify TLS trust or
hostname validation failures as permanent configuration failures without disabling verification.
Backends translate provider errors; the worker applies queue policy by type. Keep SDK-internal retries
limited so they do not multiply FreeFox's durable retry delays.

**Rationale**: Current message substring matching and Drive-specific log text cannot safely classify
S3 errors. Typed errors provide deterministic tests and actionable provider-neutral logs.

**Alternatives considered**: Extending string matching is locale/version fragile; allowing both SDK
and worker retries without coordination causes long, unpredictable stalls.

## Credentials, endpoints, and TLS

**Decision**: Use the standard AWS credential provider chain without passing secret values from
FreeFox YAML. Support a non-secret optional profile, region, endpoint URL, addressing style, and CA
bundle. Use Signature Version 4 and keep TLS certificate verification enabled. Default to AWS S3
when no endpoint is given; use path addressing by default for custom MinIO endpoints and automatic
addressing for AWS.

**Rationale**: The standard chain supports environment credentials, external shared files, web
identity, and container/instance roles with refresh. Explicit endpoints and path addressing cover
common MinIO deployments while preserving secure defaults.

**Alternatives considered**: YAML access/secret keys violate repository safety; disabling TLS is an
unsafe unattended default; hidden endpoint discovery conflicts with explicit configuration.

## Per-item backend binding and migration

**Decision**: Add an immutable backend field to every queue item and dispatch through a backend
registry. Snapshot non-secret destination identity with provider resume state. Migrate legacy rows
transactionally to the deployment's known active legacy backend without changing status, retries,
or session state. If startup under S3 cannot determine a legacy row's original backend, require an
explicit legacy backend choice or stop with an actionable error.

**Rationale**: The clarified requirement prevents configuration changes from redirecting queued
bags. Existing rows predate S3 and cannot safely be guessed as S3.

**Alternatives considered**: A process-wide backend redirects old work; silently assigning S3 risks
data misdelivery; refusing all migrations would break existing deployments unnecessarily.

## Queue representation

**Decision**: Keep the existing queue table and add normalized S3 multipart upload and part tables
with foreign keys. Preserve the Drive session URI for compatibility. Add a terminal conflict status
excluded from automatic failed-item requeue.

**Rationale**: Normalized rows allow atomic part persistence and precise reconciliation. A distinct
conflict state prevents unattended startup from repeatedly retrying a deliberate safety stop.

**Alternatives considered**: A JSON blob is simpler initially but makes atomic updates and recovery
validation weaker; overloading failed conflicts with current automatic requeue behavior.

## Test and deployment strategy

**Decision**: Keep the default pytest suite fully offline using fake S3 clients and temporary SQLite
databases. Provide opt-in smoke validation against AWS S3 and MinIO. Exercise Python 3.10+ on Linux
AMD64 and ARM64. Install the S3 extra in artifacts intended to offer the backend, while lazy imports
preserve lightweight non-S3 installations.

**Rationale**: This satisfies deterministic development, compatibility, and first-class platform
requirements without requiring secrets or network access for ordinary tests.

**Alternatives considered**: Making live cloud tests mandatory is unreliable and secret-dependent;
including provider imports eagerly would break existing minimal installations.
