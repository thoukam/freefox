# Implementation Plan: S3-Compatible Storage

**Branch**: `001-add-s3-storage` | **Date**: 2026-08-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-add-s3-storage/spec.md`

## Summary

Add an optional S3-compatible backend for AWS S3 and MinIO using explicit multipart operations so
upload identity and completed parts can survive restarts. Extend the persistent queue with immutable
per-item backend binding and normalized S3 multipart state, dispatch each item to its bound backend,
and require remote size plus BLAKE3 metadata confirmation before completion or local deletion.
Preserve Google Drive and rsync behavior through backward-compatible migrations and regression tests.

## Technical Context

**Language/Version**: Python 3.10 or newer

**Primary Dependencies**: Existing PyYAML, BLAKE3, Google client libraries, and watchdog; optional
`boto3>=1.28`/botocore for S3, imported only when the S3 backend is selected

**Storage**: Local SQLite queue in WAL mode; AWS S3 or MinIO object storage; existing Google Drive
and rsync destinations

**Testing**: pytest with offline fakes/unit tests by default; opt-in AWS S3 and MinIO smoke tests

**Target Platform**: Linux AMD64 and ARM64 under systemd or containers

**Project Type**: Single-process CLI/service with watcher, durable queue, worker pool, and pluggable
storage backends

**Performance Goals**: Stream files without loading a rosbag into memory; support objects up to the
S3 multipart limit; avoid retransmitting already confirmed parts after restart; retain the existing
configured worker concurrency

**Constraints**: Fully local collection and queue operation without Internet; no local deletion
before verified confirmation; multipart parts at least 5 MiB except the final part and no more than
10,000 parts; no credentials in YAML examples, SQLite, logs, images, or repository; TLS verification
remains enabled; operations targeting the same backend destination key are serialized before remote
inspection/upload; default automated tests require no provider access

**Scale/Scope**: One selected backend for newly queued work, while unfinished items for multiple
historical backends may coexist; one remote object per rosbag; individual objects through 5 TiB;
small unattended robot deployments using the existing SQLite queue and worker-count controls

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Pre-research evaluation | Post-design evaluation |
|------|-------------------------|------------------------|
| Durable local-first custody | PASS: queue state remains authoritative and deletion stays opt-in. | PASS: backend binding and multipart state persist in SQLite; confirmation precedes deletion. |
| Retryable, verified delivery | PASS: resumable multipart and BLAKE3/size confirmation are required. | PASS: part reconciliation, ambiguous-completion HEAD, typed retries, deduplication, and conflicts are defined. |
| Unattended reliability | PASS: restart recovery and actionable failures are in scope. | PASS: terminal conflicts, provider-neutral error classes, state recovery, and non-secret logging are designed. |
| Explicit configuration and secrets | PASS: S3 selection and non-secret settings are explicit. | PASS: the standard external credential chain is used; secret fields are excluded from config and state. |
| Simplicity and compatibility | PASS: the existing optional boto3 extra and backend boundary are reused. | PASS: no second S3 SDK or service is added; migrations and Google Drive/rsync regression coverage are required. |
| Linux/ARM64 and deployment | PASS: both are acceptance targets. | PASS: pure-Python boto3 path, systemd standard streams, container mounts/roles, and architecture validation are covered. |
| Offline tests and behavior stability | PASS: default suite stays offline and existing behavior is protected. | PASS: fake-client tests cover S3 decisions; live provider tests remain opt-in. |

No gate violation requires an exception. The design deliberately adds normalized multipart tables and
a backend registry because the clarified requirements cannot be met safely by the existing single
opaque session string and process-wide backend instance.

## Project Structure

### Documentation (this feature)

```text
specs/001-add-s3-storage/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── configuration.md
│   └── storage-backend.md
└── tasks.md                 # generated later by $speckit-tasks
```

### Source Code (repository root)

```text
freefox/
├── backends/
│   ├── __init__.py          # backend-neutral result/errors and protocol
│   ├── factory.py           # lazy backend registry construction
│   ├── gdrive.py            # compatibility-preserved adapter
│   ├── rsync.py             # compatibility-preserved adapter
│   └── s3.py                # S3/MinIO inspection and multipart transfer
├── config.py                # S3 settings and backend validation
├── queue.py                 # backend binding and multipart persistence
├── service.py               # path creation, migration context, registry wiring
├── worker.py                # per-entry dispatch and typed failure policy
└── integrity.py

config/
├── config.example.yaml
└── config.docker.example.yaml

docs/
└── s3-storage.md

scripts/
└── s3_smoke.py

tests/
├── conftest.py
├── test_core.py
├── test_s3_backend.py
├── test_s3_config.py
├── test_s3_queue.py
├── test_s3_security.py
└── test_s3_worker.py
```

**Structure Decision**: Keep FreeFox as one Python package and extend its established backend,
configuration, queue, service, and worker boundaries. The S3 implementation is isolated in one
backend module; durable provider state belongs in the existing SQLite queue layer. Tests remain in
the current single pytest suite, split by concern as S3 coverage grows.

## Phase 0: Research Summary

Research decisions are recorded in [research.md](research.md). All technical unknowns are resolved:
low-level boto3 multipart operations, normalized restart state, standard credential discovery,
portable BLAKE3 metadata, provider-neutral failure categories, and migration behavior.

## Phase 1: Design Summary

- [data-model.md](data-model.md) defines queue binding, multipart upload/part records, migration, and
  state transitions.
- [contracts/configuration.md](contracts/configuration.md) defines the user-visible YAML and external
  credential contract.
- [contracts/storage-backend.md](contracts/storage-backend.md) defines inspection, upload,
  resumption, integrity, conflict, and error semantics.
- [quickstart.md](quickstart.md) defines offline, AWS, MinIO, restart, conflict, migration, deployment,
  and regression validation.
- Transient credential-service failures are retryable with bounded backoff; invalid credentials and
  authorization denial are actionable permanent failures. TLS trust/hostname validation failures are
  permanent configuration failures and never disable certificate verification automatically.

## Complexity Tracking

No constitution violations require justification.
