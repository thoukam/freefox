# Feature Specification: S3-Compatible Storage

**Feature Branch**: `001-add-s3-storage`

**Created**: 2026-08-15

**Status**: Draft

**Input**: User description: "Add AWS S3 and MinIO-compatible storage as an additional configurable backend while preserving safe local custody, retry behavior, credentials, and existing Google Drive behavior."

## Clarifications

### Session 2026-08-15

- Q: When FreeFox restarts during a multipart S3 upload, must it resume the existing remote upload rather than begin a new one? → A: Resume the existing multipart upload across restarts; safely restart only if that session is unusable.
- Q: What must FreeFox do when the intended S3 object key already contains different content? → A: Mark the upload as a non-retryable conflict, preserve the local bag, and require operator action.
- Q: If the configured storage backend changes while bags are still queued, where should those existing queued bags be uploaded? → A: Existing queued bags retain their original backend; only newly queued bags use the new selection.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload Rosbags to S3-Compatible Storage (Priority: P1)

A robot operator selects S3-compatible storage, supplies a bucket and authorized credentials outside
the repository, and has completed rosbags delivered to the configured destination while FreeFox
continues to manage them through its normal collection workflow.

**Why this priority**: This is the feature's primary value: operators can use AWS S3 or MinIO as a
storage destination without replacing FreeFox or changing their rosbag collection process.

**Independent Test**: Configure a reachable S3-compatible destination, place a completed test bag in
the watched location, and verify that the bag appears at the expected destination, is confirmed as
complete, and is recorded as successfully delivered.

**Acceptance Scenarios**:

1. **Given** valid AWS S3 destination settings and credentials, **When** a completed rosbag is
   collected, **Then** FreeFox uploads it to the configured bucket and confirms successful delivery.
2. **Given** valid MinIO endpoint settings and credentials, **When** a completed rosbag is collected,
   **Then** FreeFox uploads it through the same operator workflow and confirms successful delivery.
3. **Given** multiple supported backends are available, **When** the operator selects S3-compatible
   storage in configuration, **Then** only that destination handles newly queued uploads.

4. **Given** unfinished items queued for another backend, **When** the operator selects S3-compatible
   storage, **Then** those existing items retain their original backend and only subsequently queued
   bags use S3-compatible storage.
5. **Given** two queued bags resolve to the same backend destination key, **When** workers process
   them concurrently, **Then** at most one upload establishes the object and the other item completes
   only if content-identical or becomes a non-retryable conflict.

---

### User Story 2 - Survive Connectivity Interruptions Safely (Priority: P1)

A robot continues collecting bags while its storage endpoint is unreachable. FreeFox retains each
local bag and its queued work, retries safely, and completes delivery after connectivity returns.

**Why this priority**: Robots commonly operate with intermittent connectivity; avoiding bag loss is
a non-negotiable FreeFox guarantee.

**Independent Test**: Interrupt connectivity during an upload, restart FreeFox if desired, restore
the endpoint, and verify that the same queued bag is eventually delivered exactly once as a complete
object while the local source remains present until confirmation.

**Acceptance Scenarios**:

1. **Given** an unavailable S3-compatible endpoint, **When** a bag becomes ready, **Then** it remains
   locally present and queued for a later retry.
2. **Given** an upload interrupted after partial progress, **When** connectivity returns, **Then**
   FreeFox resumes or safely retries without treating partial remote data as successful delivery.
3. **Given** FreeFox restarts while an upload is incomplete, **When** service operation resumes,
   **Then** the pending bag remains recoverable and eligible for delivery.
4. **Given** local deletion after upload is enabled, **When** delivery has not yet been confirmed,
   **Then** the local bag is not deleted.

---

### User Story 3 - Retain Existing Google Drive Operation (Priority: P2)

An operator with an existing Google Drive deployment upgrades FreeFox without changing
configuration and continues to collect and upload rosbags as before.

**Why this priority**: Adding a backend must not disrupt deployed robots or require avoidable
migration work.

**Independent Test**: Run the existing Google Drive configuration and regression scenarios after
adding S3 support and verify unchanged selection, queue, upload, retry, integrity, and deletion
behavior.

**Acceptance Scenarios**:

1. **Given** a previously valid Google Drive configuration, **When** the updated FreeFox starts,
   **Then** it selects Google Drive and processes bags with the existing behavior.
2. **Given** a Google Drive upload failure, **When** normal retry rules apply, **Then** S3 support does
   not alter its queued state, retry result, or local-file safety.
3. **Given** an unsupported backend value, **When** configuration is loaded, **Then** FreeFox rejects
   it with an actionable error instead of silently choosing another backend.

---

### User Story 4 - Configure Credentials Without Repository Secrets (Priority: P2)

A robot operator supplies S3-compatible credentials through the deployment environment without
placing secret values in version-controlled configuration examples or application artifacts.

**Why this priority**: Credential safety is necessary for real deployments and is mandated by the
FreeFox constitution.

**Independent Test**: Start FreeFox with externally supplied credentials, verify successful access,
and inspect repository files and normal logs to confirm that secret values are absent.

**Acceptance Scenarios**:

1. **Given** credentials supplied through a supported external mechanism, **When** FreeFox starts,
   **Then** it can authenticate without credentials being stored in repository-managed files.
2. **Given** missing or invalid credentials, **When** an upload is attempted, **Then** the failure is
   actionable, the bag stays local, and no secret value is logged.

### Edge Cases

- The endpoint is reachable but the target bucket does not exist or access is denied.
- Connectivity drops before any data, during transfer, or after transfer but before confirmation.
- A retry finds a complete object already present from an earlier attempt.
- A conflicting object at the intended destination key is left unchanged; the upload becomes a
  non-retryable conflict, the local bag is preserved, and logs identify required operator action.
- The local bag changes after it is queued or while delivery preparation is occurring.
- The bag is larger than a single-request upload and the service restarts mid-transfer.
- The configured endpoint uses TLS with a certificate validation failure.
- Bucket names, endpoint URLs, regions, object prefixes, or backend values are malformed.
- Two queued items resolve to the same destination key; delivery is serialized for that backend
  destination key so different content cannot race to overwrite an object.
- Integrity verification is enabled but destination metadata is missing or mismatched.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: FreeFox MUST offer S3-compatible storage as an additional selectable backend without
  removing Google Drive or other currently supported backends.
- **FR-002**: Operators MUST be able to select exactly one upload backend through the normal FreeFox
  configuration and receive an actionable startup error for an unsupported selection. Each upload
  item MUST retain the backend selected when that item enters the queue; changing configuration
  MUST affect only items queued afterward.
- **FR-003**: S3-compatible configuration MUST accept the destination bucket and MUST support an
  optional object prefix, region, and custom endpoint needed for MinIO-compatible services.
- **FR-004**: Omitting a custom endpoint MUST select standard AWS S3 behavior; providing one MUST
  direct operations to that S3-compatible endpoint.
- **FR-005**: FreeFox MUST obtain S3-compatible credentials from documented external credential
  sources and MUST NOT require secret values in repository-managed configuration examples.
- **FR-006**: FreeFox MUST NOT emit access keys, secret keys, session credentials, or signed request
  material in normal or error logs.
- **FR-007**: A completed rosbag selected for S3-compatible delivery MUST enter the existing durable
  upload lifecycle before remote delivery is attempted.
- **FR-008**: Network unavailability and other retryable destination failures MUST preserve the local
  bag and queued work and MUST schedule a safe later retry.
- **FR-009**: Multipart upload identity and completed-part state MUST persist across service restarts.
  FreeFox MUST resume the existing remote upload after restart and MAY begin a new upload only when
  the prior session is unusable, without accepting an incomplete remote object as success.
- **FR-010**: FreeFox MUST mark an upload successful only after the destination confirms that the
  complete object exists at the intended bucket and key.
- **FR-011**: FreeFox MUST NOT delete a local bag before FR-010 is satisfied and all enabled integrity
  checks have passed; deletion MUST remain governed by the existing opt-in setting.
- **FR-012**: When integrity verification is enabled, FreeFox MUST confirm remote content identity
  using the bag's digest and size before completing or deduplicating delivery.
- **FR-013**: A retry that discovers an already complete, content-identical object MUST complete
  safely without uploading a duplicate. If the intended key contains different content, FreeFox
  MUST NOT overwrite it or choose a different key automatically; it MUST preserve the local bag,
  mark the item as a non-retryable conflict, and report that operator action is required. FreeFox
  MUST serialize concurrent queue items targeting the same backend destination key, or provide an
  equivalent conditional-write guarantee; after the first item establishes the object, every
  contender MUST be resolved by content inspection as identical success or terminal conflict.
- **FR-014**: Destination object organization MUST retain FreeFox's robot and optional date grouping
  semantics so operators can locate bags consistently across backends.
- **FR-015**: Operational logs MUST identify the affected bag, destination context excluding secrets,
  failure category, and whether the item will retry or requires operator action.
- **FR-016**: Existing valid Google Drive configurations MUST continue to select Google Drive without
  requiring new S3 settings or changing established upload behavior.
- **FR-017**: Existing queued items and their retry state MUST remain usable after upgrading to a
  version that supports S3-compatible storage. Upgrade migration MUST bind each pre-upgrade item to
  the backend active for that deployment without losing or resetting its delivery state; if that
  backend cannot be determined safely, startup MUST stop with an actionable error.
- **FR-018**: S3-compatible delivery MUST operate on supported Linux and ARM64 deployments, including
  the existing host-service and container deployment modes.

### Key Entities *(include if feature involves data)*

- **Storage Destination**: The selected backend and its non-secret location settings, including
  bucket, optional object prefix, region, and optional custom endpoint.
- **Credential Source**: An external mechanism that supplies temporary or long-lived authorization
  without making secret values part of repository content.
- **Upload Item**: A local rosbag and its durable delivery state, including destination key, attempts,
  retry timing, progress or resumable state, size, digest, completion, and last error.
- **Remote Object**: The destination representation of a rosbag, identified by bucket and key and
  verified by completion state, size, and content identity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In acceptance testing, 100% of completed test bags uploaded to both an AWS S3 target and
  a MinIO-compatible target arrive at the configured key and pass enabled integrity verification.
- **SC-002**: Across network interruptions at the start, middle, and confirmation stage of delivery,
  100% of test bags remain locally available until confirmed and are delivered after recovery
  without an incomplete object being reported as successful.
- **SC-003**: After an interruption and service restart during a large upload, delivery resumes or
  retries automatically within one configured retry interval after connectivity returns.
- **SC-004**: Existing Google Drive regression scenarios pass without configuration changes and with
  no observed difference in selection, retry, integrity, or local deletion outcomes.
- **SC-005**: Operators can configure either AWS S3 or a MinIO-compatible destination from the
  documented example and complete a first verified test upload in under 15 minutes, excluding
  account or server provisioning time.
- **SC-006**: Repository and log inspection across success, authentication failure, and network
  failure scenarios reveals zero stored or emitted secret credential values.
- **SC-007**: All feature acceptance and regression tests run successfully on Linux ARM64 and AMD64
  targets used by the project.

### Acceptance Test Corpus

The 100% outcomes in SC-001 and SC-002 apply, at minimum, to:

- AWS S3 and one supported MinIO-compatible deployment.
- One object below the multipart threshold and one object requiring at least three parts.
- Integrity verification enabled and disabled.
- Connectivity interruption before transfer, after at least one confirmed part, and after completion
  is committed but before confirmation is received.
- One service restart during multipart transfer.
- One identical-object retry, one different-content key conflict, and one pair of concurrently queued
  items targeting the same key.

Every matrix case MUST retain the local bag until verified completion and MUST NOT report an incomplete object as successful.

## Assumptions

- One storage backend is active for a FreeFox process; simultaneous replication to multiple
  backends is outside this feature's scope.
- S3-compatible means the object storage supports the operations required for safe upload,
  confirmation, metadata retrieval, and multipart transfer; provider-specific archival workflows
  and lifecycle policy management are outside scope.
- Server-side encryption policy, bucket creation, bucket lifecycle rules, object retention, and IAM
  provisioning remain operator responsibilities.
- Existing FreeFox retry timing, local deletion setting, robot/date path organization, and integrity
  policy apply to the new backend unless compatibility requires a stricter safety rule.
- Standard external credential discovery and explicitly documented environment-based credentials are
  acceptable; credentials embedded directly in committed YAML are not.
- The feature depends on access to an operator-provisioned AWS S3 bucket or MinIO-compatible service
  for opt-in integration validation, while the default automated suite remains fully offline.
