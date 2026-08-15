<!--
Sync Impact Report
- Version change: template (unratified) -> 1.0.0
- Modified principles: all five placeholders resolved as Principles I-V
- Added sections: Architecture and Deployment Constraints; Development and Quality Gates
- Removed sections: none (template placeholders resolved)
- Follow-up TODOs: none
-->
# FreeFox Constitution

## Core Principles

### I. Durable Local-First Custody
FreeFox MUST discover completed rosbags and maintain upload state without Internet access. A bag
MUST enter the persistent SQLite queue before delivery is attempted, and queue state MUST survive
crashes, reboots, and backend outages. FreeFox MUST NOT delete or overwrite a local bag until the
destination confirms delivery and all enabled integrity checks succeed. Local deletion MUST remain
opt-in and disabled by default. Changes to stability detection, queue transitions, migrations, or
restart recovery MUST demonstrate that interruption cannot silently lose custody of a bag.

Rationale: the local copy and durable queue are the system of record until delivery is complete.

### II. Retryable, Verified Delivery
Every backend MUST make uploads resumable when supported, or safely retryable and idempotent
otherwise. Temporary network, quota, authentication-service, and remote-service failures MUST
preserve the queued item and retry with bounded backoff; they MUST NOT count as success. Interrupted
state, such as a Drive session URI or rsync partial file, MUST be retained or safely reconstructed
when practical. Completion MUST require backend confirmation. When integrity verification is
enabled, FreeFox MUST compare BLAKE3 digest and size through backend metadata or a sidecar before
marking an item done or deleting its source. Duplicate detection MUST establish content identity,
not rely on filename alone.

Rationale: unreliable robot links are normal, and a remote file is useful only if it is complete.

### III. Unattended Operational Reliability
FreeFox MUST run continuously without an operator. Startup MUST recover transient upload states;
SIGTERM and SIGINT MUST stop watchers and workers within the deployment manager's timeout; worker
failures MUST be isolated where practical. Environmental failures MUST produce actionable logs
with the affected file or queue entry, backend context, retry disposition, and cause, without
exposing credentials. Periodic logs MUST expose queue health and stalled retry states. Failures
MUST remain inspectable through the persistent queue and standard output for journald and container
log collectors.

Rationale: remote robots require diagnosable behavior through long periods without intervention.

### IV. Explicit Configuration and Secret Safety
Configuration MUST remain a small, documented YAML surface with conservative defaults and only
documented environment overrides. New settings MUST have validation, a clear default or required
value error, and an example. Behavior MUST NOT depend on hidden network discovery or mutable global
state. Credentials, tokens, private keys, and populated secret files MUST never be committed,
embedded in images, or logged. Deployments MUST receive secrets through external read-only files
or an equivalently explicit secret mechanism.

Rationale: explicit configuration makes deployments reproducible and external secrets keep
repository history and diagnostics safe to share.

### V. Simplicity, Compatibility, and Stable Behavior
Reliability MUST take precedence over unnecessary abstraction, services, and dependencies. A new
runtime dependency MUST provide an operational benefit unavailable reasonably from the standard
library or existing dependencies. Linux and ARM64 MUST be first-class targets for code,
dependencies, filesystem behavior, and images. Existing CLI, configuration, queue, backend,
remote-path, and deployment behavior MUST remain compatible unless a change provides explicit
justification, migration guidance, and regression coverage. Architecture changes MUST preserve
the clear flow from watcher to persistent queue to workers to the selected backend.

Rationale: a compact, stable agent is easier to deploy and repair across robot fleets.

## Architecture and Deployment Constraints

- `CollectorService`, `FileWatcher`, `UploadQueue`, `UploadWorkerPool`, and factory-selected storage
  backends define the current boundaries. New boundaries require a concrete reliability need.
- SQLite schema changes MUST migrate in place and preserve existing queued work. Destructive queue
  migrations are prohibited.
- The watcher MUST use Linux facilities efficiently when available and retain a local fallback. A
  file MUST NOT be queued as complete while changing or known to be open.
- Backends MUST implement the shared contract without weakening durability, retry, progress,
  duplicate-detection, or integrity semantics.
- systemd is the primary host integration; containers are supported. The CLI MUST handle service
  signals, log to standard streams, avoid daemon self-management, and use explicit paths for state,
  bags, configuration, and secrets that support hardening and mounts.
- Published images and dependencies MUST support `linux/amd64` and `linux/arm64`. Linux-specific
  behavior such as `/proc` checks MUST fail conservatively when isolation limits it.
- The collector MUST NOT require the dashboard, ROS libraries, or Internet access to start,
  discover bags, maintain its queue, or report local status.

## Development and Quality Gates

- Behavior changes MUST include risk-proportionate tests. Queue transitions, restart recovery,
  retry classification, resumption, integrity, stability detection, configuration, and deletion
  safety require regression tests whenever affected.
- The default suite MUST run offline without Drive, SSH, ROS, or external services. Opt-in
  integration smoke tests MAY supplement deterministic unit tests and local fakes.
- Bug fixes MUST add a test that fails under old behavior when practical. Otherwise the change MUST
  document why and provide reproducible manual verification.
- Reviews MUST check local custody, retry safety, verification before deletion, migrations,
  dependencies, ARM64/Linux support, diagnostic logs, and secret exposure.
- Breaking behavior requires explicit justification, user-visible migration instructions, and
  tests for the new contract. Undocumented breakage is prohibited.

## Governance

This constitution is FreeFox's highest-priority engineering policy. Specifications, plans, tasks,
reviews, and implementations MUST demonstrate compliance. When rules conflict, preserving local
bag custody and verified delivery takes precedence.

Amendments MUST document their reason and operational impact, update the Sync Impact Report, and
receive maintainer approval. Removing or incompatibly redefining a guarantee requires a MAJOR
version bump; a new principle or material expansion requires MINOR; clarification requires PATCH.

Every feature and release review MUST check compliance. An exception MUST identify the rule,
necessity, risk controls, and removal or reassessment condition. New complexity and dependencies
require explicit justification. Gaps affecting custody, integrity, deletion safety, or credentials
MUST block release.

**Version**: 1.0.0 | **Ratified**: 2026-08-15 | **Last Amended**: 2026-08-15
