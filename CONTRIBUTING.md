**English** · [Français](CONTRIBUTING.fr.md)

# Contributing to FreeFox

Thank you for wanting to make FreeFox better. Contributions of every size are welcome, and
issues and pull requests can be written in **English or French**.

## Ways to help

- **Use it and report back.** Field reports from real robots (hardware, network, bag sizes) are gold.
- **Report bugs** with the [bug report template](https://github.com/thoukam/freefox/issues/new/choose).
- **Improve the docs.** Fix unclear steps, add examples, translate the French guides into English.
- **Pick an issue** labelled [`good first issue`](https://github.com/thoukam/freefox/labels/good%20first%20issue)
  or [`help wanted`](https://github.com/thoukam/freefox/labels/help%20wanted).
- **Build a roadmap item**: Prometheus metrics, dashboard auth, new backends, upload rules…
  Please open an issue first so we can agree on the design.

## Development setup

Requirements: Linux, Python 3.10+, `rsync` (for the rsync backend).

```bash
git clone https://github.com/<you>/freefox && cd freefox
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,s3]"
.venv/bin/python -m pytest
```

> **On a machine with ROS 2 sourced?** ROS adds its own pytest plugins to `PYTHONPATH`, and they
> can break collection. Run the tests in a clean shell or with
> `env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_timeout`.

Useful scripts:

| Command | Purpose |
|---|---|
| `scripts/local_smoke.py` | End-to-end run against a local folder, no cloud account needed |
| `scripts/dashboard.py --config <cfg>` | Local dashboard on `http://127.0.0.1:8765` |
| `scripts/queue_status.py <queue.db>` | Inspect the SQLite queue |
| `scripts/gdrive_smoke.py`, `scripts/s3_smoke.py` | Opt-in live checks against real storage |

Read [docs/en/architecture.md](docs/en/architecture.md) before touching the queue, the workers or a backend.

## Making a change

1. Fork the repo and create a branch from `main`: `feat/prometheus-metrics`, `fix/rsync-timeout`, `docs/...`.
2. Keep pull requests focused: one feature or fix per PR.
3. Add or update tests. Tests must not need network access or real credentials. Use fakes (see
   `tests/conftest.py`).
4. Update the docs and `CHANGELOG.md` (under *Unreleased*) when behaviour or configuration changes.
   Documents exist in English and French (`X.md` / `X.fr.md`, `docs/en/` / `docs/fr/`). Update both
   if you can, or say in the PR that a translation is missing and someone will help.
5. Make sure the checks pass: `ruff format freefox scripts tests`, `ruff check freefox scripts tests`
   and `pytest`. The CI runs the same commands.
6. Open the pull request and fill in the template.

### Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat(s3): support SSE-KMS encryption
fix(watcher): ignore files removed before they become stable
docs: translate the Docker guide to English
```

### Code guidelines

- Code is formatted with [ruff](https://docs.astral.sh/ruff/) (line length 100). Run `ruff format` before committing.
- Target Python 3.10 and use type hints on public functions.
- Optional SDKs (boto3, …) are imported lazily, inside the backend.
- Never log or store secrets. Redact provider error messages (see `s3._safe_message`).
- Keep the safety guarantees: no data loss, no silent overwrite, idempotent retries.
- Prefer clear, readable code over clever one-liners. Code is read far more often than it is written.

## Reporting security issues

Please **do not** open a public issue. See [SECURITY.md](SECURITY.md).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be kind, and assume good intent.

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
