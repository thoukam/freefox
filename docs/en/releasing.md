**English** · [Français](../fr/releasing.md)

# Releasing

FreeFox is released from GitHub. Publishing a GitHub release triggers two workflows:

| Workflow | Result |
|---|---|
| `publish-pypi.yml` | Builds the package and uploads it to [PyPI](https://pypi.org/project/freefox/) |
| `docker-publish.yml` | Builds and pushes `ghcr.io/thoukam/freefox:<version>` for amd64 and arm64 |

## One-time setup: PyPI Trusted Publishing

Trusted Publishing lets GitHub Actions upload to PyPI without storing any API token.

1. Create an account on <https://pypi.org> and enable two-factor authentication.
2. Go to **Your account → Publishing → Add a new pending publisher** and fill in:
   - PyPI project name: `freefox`
   - Owner: `thoukam`
   - Repository name: `freefox`
   - Workflow name: `publish-pypi.yml`
   - Environment name: `pypi`
3. On GitHub, go to **Settings → Environments → New environment** and name it `pypi`.
   Optionally, add yourself as a required reviewer so every upload waits for your approval.

The first successful upload creates the `freefox` project on PyPI. After that, the pending
publisher becomes a normal trusted publisher.

## Every release

1. Make sure `main` is green in CI.
2. Set the version in `freefox/__init__.py` (`__version__ = "X.Y.Z"`), following
   [Semantic Versioning](https://semver.org/):
   - `Z` for fixes only,
   - `Y` for new features that stay backward compatible,
   - `X` for breaking changes (before 1.0, a breaking change bumps `Y`).
3. In `CHANGELOG.md` and `CHANGELOG.fr.md`, rename *Unreleased* to `[X.Y.Z] - YYYY-MM-DD`,
   add a new empty *Unreleased* section and update the links at the bottom.
4. Commit through a pull request: `chore: release X.Y.Z`.
5. On GitHub, go to **Releases → Draft a new release**:
   - tag: `vX.Y.Z`, created on `main`,
   - title: `vX.Y.Z`,
   - description: paste the CHANGELOG section.
6. Click **Publish release**. Then check the **Actions** tab: both workflows must succeed.
   If the tag and `__version__` differ, the PyPI workflow stops before uploading anything.

## Check the release

```bash
python3 -m venv /tmp/ff && /tmp/ff/bin/pip install "freefox[s3]==X.Y.Z"
/tmp/ff/bin/freefox --help
docker pull ghcr.io/thoukam/freefox:X.Y.Z
```

A version uploaded to PyPI can never be replaced. If something is wrong, fix it and release
`X.Y.Z+1`. You can also *yank* the bad version on PyPI so that `pip` stops choosing it.

## Testing the build locally

```bash
.venv/bin/pip install -e ".[dev]"
rm -rf dist && .venv/bin/python -m build && .venv/bin/twine check dist/*
```
