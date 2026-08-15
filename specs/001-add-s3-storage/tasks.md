---

description: "Dependency-ordered implementation tasks for S3-compatible storage"
---

# Tasks: S3-Compatible Storage

**Input**: Design documents from `/specs/001-add-s3-storage/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Required by the feature acceptance criteria and the constitution for queue migration,
restart recovery, retry classification, integrity, configuration, compatibility, and deletion safety.
Story tests must be written first and observed failing before the corresponding implementation.

**Organization**: Tasks are grouped by user story so each story produces an independently testable
increment. Shared schema, backend contracts, and test infrastructure are completed first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no dependency on another
  incomplete task in the same phase.
- **[Story]**: Maps work to User Story 1–4 from `spec.md`.
- Every task names the exact file or files it changes.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare reusable offline S3 test infrastructure and operator-facing documentation
locations without changing runtime behavior.

- [X] T001 Create deterministic fake S3 client, paginator, error, and call-recording fixtures in tests/conftest.py
- [X] T002 [P] Add the S3 optional-extra installation and test commands to docs/installation.md
- [X] T003 [P] Add S3-compatible storage discovery text to the project description and keywords in pyproject.toml and README.md without duplicating installation instructions

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Introduce the durable routing model and provider-neutral contracts needed by every user
story.

**Critical**: No user story implementation begins until this phase passes its offline tests.

- [X] T004 [P] Add failing tests for backend binding, destination snapshots, conflict state, multipart rows, restart preservation, and idempotent schema migration in tests/test_s3_queue.py
- [X] T005 [P] Add failing tests for S3 configuration defaults, normalization, validation, unsupported backends, and lazy optional dependency behavior in tests/test_s3_config.py
- [X] T006 Define backend names, destination snapshots, remote inspection/upload results, progress/checkpoint callbacks, and typed provider-neutral exceptions in freefox/backends/__init__.py
- [X] T007 Extend QueueEntry, queue statuses, additive schema migration, immutable backend/destination insertion, and conflict-safe query behavior in freefox/queue.py
- [X] T008 Add normalized s3_multipart_uploads and s3_multipart_parts schema plus atomic create, reconcile, upsert, load, and clear operations in freefox/queue.py
- [X] T009 Add typed S3Config parsing, prefix/endpoint/addressing/CA validation, conservative defaults, and `storage.backend: s3` acceptance in freefox/config.py
- [X] T010 Replace the single process-wide backend construction path with a lazy per-destination backend registry in freefox/backends/factory.py
- [X] T011 Bind new queue items to the selected backend and canonical non-secret destination snapshot while constructing immutable remote paths in freefox/service.py
- [X] T012 Run the foundational queue and configuration tests and resolve all failures in tests/test_s3_queue.py and tests/test_s3_config.py

**Checkpoint**: Queue rows can safely retain routing and multipart state, configuration is validated,
and backend construction can remain lazy.

---

## Phase 3: User Story 1 - Upload Rosbags to S3-Compatible Storage (Priority: P1) — MVP

**Goal**: Upload a completed rosbag to AWS S3 or MinIO through the normal collection workflow,
confirm exact remote identity, and route only newly queued work to S3.

**Independent Test**: Configure a fake AWS or MinIO destination, queue a completed bag, and verify
the expected bucket/key, metadata, confirmed `done` state, and unchanged local file. Repeat with an
identical existing object and a conflicting object.

### Tests for User Story 1

- [X] T013 [P] [US1] Add failing tests for AWS and custom-endpoint client construction, path addressing, lazy boto3 import, and safe object inspection in tests/test_s3_backend.py
- [X] T014 [P] [US1] Add failing tests for single-request and fresh multipart uploads, ordered parts, metadata, progress, confirmation, deduplication, and conflicts in tests/test_s3_backend.py
- [X] T015 [P] [US1] Add failing worker tests for per-entry S3 dispatch, concurrent same-key serialization, identical and conflicting contenders, verified completion, terminal conflict, and deletion only after confirmation in tests/test_s3_worker.py

### Implementation for User Story 1

- [X] T016 [US1] Implement lazy boto3 client construction for AWS and MinIO-compatible endpoints with SigV4, addressing style, CA verification, bounded SDK retries, and safe inspection in freefox/backends/s3.py
- [X] T017 [US1] Implement streaming single-request and fresh multipart upload, effective part sizing, BLAKE3/size metadata, ordered completion, and post-upload HeadObject confirmation in freefox/backends/s3.py
- [X] T018 [US1] Implement identical-object success and different-or-unverifiable-object conflict behavior without overwrite or automatic rename in freefox/backends/s3.py
- [X] T019 [US1] Dispatch each claimed item through its bound backend, serialize work by canonical backend destination key, re-inspect after acquiring the key guard, consume typed results, mark conflicts terminally, and gate local deletion on verified success in freefox/worker.py
- [X] T020 [P] [US1] Add complete non-secret AWS and MinIO configuration examples in config/config.example.yaml and config/config.docker.example.yaml
- [X] T021 [US1] Wire registry lifecycle, S3 destination snapshots, and backend-specific robot/date object-key construction into freefox/service.py
- [X] T022 [US1] Run the User Story 1 offline tests and verify the independent AWS/MinIO fake-client scenarios in tests/test_s3_backend.py and tests/test_s3_worker.py

**Checkpoint**: The S3 backend is a usable MVP for uninterrupted AWS and MinIO-compatible uploads,
including verified deduplication and safe conflicts.

---

## Phase 4: User Story 2 - Survive Connectivity Interruptions Safely (Priority: P1)

**Goal**: Preserve local custody and multipart progress across network failures and service restarts,
then resume or safely replace only an unusable session.

**Independent Test**: Interrupt a multipart upload after confirmed parts, recreate the queue and
worker, restore connectivity, and verify reuse of the upload ID and valid parts, eventual confirmed
delivery, and no premature local deletion.

### Tests for User Story 2

- [X] T023 [P] [US2] Add failing tests for persisted upload IDs/parts, restart reconciliation, mismatched remote parts, and upload-session replacement in tests/test_s3_queue.py
- [X] T024 [P] [US2] Add failing tests for interrupted transfers, expired sessions, lost completion responses, source mutation, and no retransmission of valid parts in tests/test_s3_backend.py
- [X] T025 [P] [US2] Add failing tests distinguishing transient credential-service failures from invalid credentials and authorization denial, plus network, throttling, TLS validation, permanent configuration, invalid-session, and conflict dispositions and retry timing in tests/test_s3_worker.py

### Implementation for User Story 2

- [X] T026 [US2] Integrate S3 multipart creation and per-part completion with atomic queue checkpoints and durable progress updates in freefox/backends/s3.py and freefox/queue.py
- [X] T027 [US2] Implement ListParts reconciliation that reuses only matching number/ETag/size tuples and retransmits missing or invalid parts in freefox/backends/s3.py
- [X] T028 [US2] Handle invalid sessions and ambiguous completion by inspecting the final object before atomically clearing checkpoints or starting a replacement session in freefox/backends/s3.py
- [X] T029 [US2] Detect local size or digest changes against the multipart source identity and fail safely without accepting stale remote content in freefox/backends/s3.py
- [X] T030 [US2] Translate botocore failures into backend-neutral categories, retry transient credential-service failures with bounded backoff, stop invalid-credential, authorization, and TLS-validation failures actionably, and apply durable policy for all other categories in freefox/backends/s3.py and freefox/worker.py
- [X] T031 [US2] Preserve backend, destination, digest, upload ID, and completed parts when recovering interrupted uploading rows during queue initialization in freefox/queue.py
- [X] T032 [US2] Run restart, interruption, reconciliation, retry, and deletion-safety tests in tests/test_s3_queue.py, tests/test_s3_backend.py, and tests/test_s3_worker.py

**Checkpoint**: Connectivity loss and process restart cannot lose custody, discard valid multipart
progress, or report an incomplete object as successful.

---

## Phase 5: User Story 3 - Retain Existing Google Drive Operation (Priority: P2)

**Goal**: Preserve Google Drive and rsync configuration and delivery behavior while safely migrating
legacy queue rows to immutable backend ownership.

**Independent Test**: Run existing Drive and rsync regression scenarios unchanged, then migrate a
legacy database containing queued/uploading/failed/session rows and verify preserved state and
correct legacy dispatch. Confirm ambiguous ownership blocks startup without modifying the database.

### Tests for User Story 3

- [X] T033 [P] [US3] Add failing compatibility tests for unchanged Google Drive and rsync configuration, paths, sessions/partials, retries, integrity, and deletion behavior in tests/test_core.py
- [X] T034 [P] [US3] Add failing migration tests for known gdrive/rsync ownership, all legacy statuses, idempotency, rollback, and ambiguous ownership in tests/test_s3_queue.py
- [X] T035 [P] [US3] Add failing mixed-backend queue tests proving old items retain their backend while newly queued items use S3 in tests/test_s3_worker.py

### Implementation for User Story 3

- [X] T036 [US3] Adapt Google Drive and rsync implementations to the provider-neutral result/error contract without changing established behavior in freefox/backends/gdrive.py and freefox/backends/rsync.py
- [X] T037 [US3] Implement transactional legacy-row binding from explicit deployment context while preserving status, retries, timing, progress, digest, and Drive session URI in freefox/queue.py
- [X] T038 [US3] Pass validated legacy-backend migration context at startup and stop with an actionable error when ownership is ambiguous in freefox/service.py and freefox/config.py
- [X] T039 [US3] Ensure startup failed-item requeue excludes conflicts and per-entry dispatch supports coexisting gdrive, rsync, and s3 work in freefox/worker.py and freefox/service.py
- [X] T040 [US3] Run Google Drive, rsync, migration, and mixed-backend regression tests in tests/test_core.py, tests/test_s3_queue.py, and tests/test_s3_worker.py

**Checkpoint**: Existing deployments upgrade without configuration changes or delivery-state loss,
and ambiguous migrations fail closed.

---

## Phase 6: User Story 4 - Configure Credentials Without Repository Secrets (Priority: P2)

**Goal**: Authenticate through external AWS credential sources and provide actionable failures and
logs without persisting or exposing secrets.

**Independent Test**: Supply credentials through environment/profile/role-style fake providers and
verify access; then trigger authentication and network failures and confirm the local bag remains and
captured configuration, SQLite content, and logs contain no credential or signed-request values.

### Tests for User Story 4

- [X] T041 [P] [US4] Add failing tests for environment, profile, web-identity/container-role handoff, refreshable sessions, and absent credentials in tests/test_s3_config.py
- [X] T042 [P] [US4] Add failing secret-canary tests across parsed config, destination JSON, SQLite rows, success logs, authentication errors, network errors, and TLS certificate-validation errors in tests/test_s3_security.py

### Implementation for User Story 4

- [X] T043 [US4] Use the standard boto3 credential provider chain without accepting or persisting inline secret fields in freefox/backends/s3.py and freefox/config.py
- [X] T044 [US4] Sanitize provider exceptions and structured destination logging to redact tokens, authorization headers, and signed query material in freefox/backends/s3.py and freefox/worker.py
- [X] T045 [P] [US4] Document external environment, shared-profile, web-identity, container-role, read-only file/mount, and private-CA setup in docs/s3-storage.md
- [X] T046 [US4] Run credential-source, missing-credential, error-redaction, repository-secret, and SQLite-secret tests in tests/test_s3_config.py and tests/test_s3_security.py

**Checkpoint**: Operators can authenticate without repository secrets, and success/failure paths do
not store or emit credential material.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Complete live validation, deployment coverage, diagnostics, and documentation shared by
all stories.

- [ ] T047 [P] Add an opt-in AWS/MinIO smoke CLI covering the SC-001/SC-002 matrix for small and multipart bags, integrity on/off, three interruption stages, restart, identical retry, conflict, and concurrent same-key contenders in scripts/s3_smoke.py
- [X] T048 [P] Add S3 extra installation, read-only credential/CA mounts, and architecture-safe settings to Dockerfile, docker-compose.yml, docker-compose.build.yml, and docs/docker-deployment.md
- [X] T049 [P] Add host-service S3 dependency, credential-file permissions, environment/profile examples, and signal/restart validation to install.sh, systemd/freefox.service, and docs/installation.md
- [X] T050 Add non-secret queue health, backend context, retry disposition, conflict, and stalled multipart diagnostics in freefox/service.py, freefox/worker.py, and scripts/queue_status.py
- [X] T051 Run the complete offline pytest suite and resolve regressions across tests/test_core.py, tests/test_s3_config.py, tests/test_s3_queue.py, tests/test_s3_backend.py, tests/test_s3_worker.py, and tests/test_s3_security.py
- [ ] T052 Execute and record the offline, AWS, MinIO, restart, conflict, migration, secret-inspection, systemd/container, AMD64, and ARM64 outcomes in specs/001-add-s3-storage/quickstart.md; time clean AWS and MinIO configuration-to-confirmed-upload runs and verify each completes within 15 minutes excluding account, bucket, and server provisioning

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately.
- **Foundational (Phase 2)**: Depends on Setup and blocks every user story.
- **User Story 1 (Phase 3)**: Depends on Foundational and is the MVP.
- **User Story 2 (Phase 4)**: Depends on the S3 upload path delivered by User Story 1.
- **User Story 3 (Phase 5)**: Depends on Foundational per-entry routing; it may run alongside User
  Story 1 after T010–T011, but final mixed-backend validation depends on User Story 1.
- **User Story 4 (Phase 6)**: Depends on User Story 1 client construction; its tests and documentation
  can begin after Foundational.
- **Polish (Phase 7)**: Depends on every story selected for release; T052 follows T047–T051.

### User Story Completion Order

```text
Setup -> Foundational -> US1 (MVP) -> US2
                         |          |
                         +-> US3 ---+
                         +-> US4 ---+-> Polish
```

### Within Each Story

- Write and run the story's test tasks first; confirm they fail for the intended missing behavior.
- Implement data/state behavior before orchestration that consumes it.
- Implement backend behavior before worker/service integration.
- Run the story validation task before declaring the checkpoint complete.
- Never delete a local bag in a test or implementation path before verified remote completion.

## Parallel Opportunities

- T002 and T003 can run alongside T001.
- T004 and T005 can run in parallel; after their failing assertions exist, T006 and T009 affect
  separate files and can proceed in parallel.
- T013–T015 can run in parallel before User Story 1 implementation.
- T023–T025 can run in parallel before User Story 2 implementation.
- T033–T035 can run in parallel before User Story 3 implementation.
- T041 and T042 can run in parallel before User Story 4 implementation; T045 can proceed alongside
  T043–T044.
- T047–T049 affect independent script/deployment/documentation areas and can run in parallel.

## Parallel Examples

### User Story 1

```text
Task T013: AWS/MinIO client and inspection tests in tests/test_s3_backend.py
Task T015: Per-entry dispatch, same-key serialization, and deletion-safety tests in tests/test_s3_worker.py
Task T020: Non-secret examples in config/config.example.yaml and config/config.docker.example.yaml
```

### User Story 2

```text
Task T023: Multipart persistence tests in tests/test_s3_queue.py
Task T024: Restart and ambiguous-completion tests in tests/test_s3_backend.py
Task T025: Retry classification tests in tests/test_s3_worker.py
```

### User Story 3

```text
Task T033: Google Drive/rsync compatibility tests in tests/test_core.py
Task T034: Legacy migration tests in tests/test_s3_queue.py
Task T035: Mixed-backend routing tests in tests/test_s3_worker.py
```

### User Story 4

```text
Task T041: External credential-source tests in tests/test_s3_config.py
Task T042: Secret-canary tests in tests/test_s3_security.py
Task T045: Operator credential documentation in docs/s3-storage.md
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational phases.
2. Complete User Story 1 through T022.
3. Stop and validate AWS and MinIO-compatible happy paths, exact identity, deduplication, conflicts,
   and deletion safety independently.
4. Demonstrate the S3 backend without claiming restart-resumption readiness until User Story 2 is
   complete.

### Incremental Delivery

1. **US1**: Verified AWS/MinIO uploads with immutable per-item routing.
2. **US2**: Durable multipart recovery under unreliable connectivity and restarts.
3. **US3**: Upgrade-safe Google Drive/rsync compatibility and mixed queues.
4. **US4**: Credential-source coverage, redaction hardening, and operator guidance.
5. **Polish**: Live provider, deployment, architecture, diagnostics, and complete quickstart evidence.

## Notes

- Tasks modifying the same file are deliberately ordered even when their tests can be written in
  parallel.
- Live AWS/MinIO checks remain opt-in; the default suite must stay fully offline.
- Commit populated secret files, access keys, session tokens, signed URLs, and captured authorization
  headers under no circumstances.
- `tasks.md` ends at implementation and validation; release or deployment authorization is separate.
