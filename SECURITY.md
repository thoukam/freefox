**English** · [Français](SECURITY.fr.md)

# Security Policy

## Supported versions

FreeFox is in active development. Security fixes go into the latest release and `main`.

| Version | Supported |
|---|---|
| 0.2.x | ✅ |
| < 0.2 | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately, either through
[GitHub private vulnerability reporting](https://github.com/thoukam/freefox/security/advisories/new)
or by e-mail to **thoukamy@gmail.com**, with:

- a description of the issue and its impact,
- steps to reproduce, or a proof of concept,
- the FreeFox version, backend and deployment mode (systemd or Docker).

You will get an acknowledgement within **72 hours**. We will keep you informed while we work on
a fix and credit you in the release notes if you wish.

## Security notes for operators

- **Dashboard:** it has no authentication yet. Bind it to `127.0.0.1`, or expose it only on a
  trusted network or behind a VPN or authenticated reverse proxy. Never expose it to the Internet.
- **Credentials:** keep `secrets/`, OAuth tokens and `/etc/freefox/aws.env` out of version control,
  with `0600`/`0640` permissions. S3 keys are refused in YAML by design.
- **Queue database:** `queue.db` holds resumable session URIs, which can grant temporary upload
  access. Keep it on local, protected storage.
- **TLS:** never disable certificate verification. Use `s3.ca_bundle` for a private CA.
