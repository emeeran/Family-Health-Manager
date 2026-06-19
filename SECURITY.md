# Security Policy

Family Health Manager stores sensitive personal health information (PHI) for you
and your family. This document explains the security model and how to report
vulnerabilities.

## Supported Versions

Only the latest release receives security updates. Self-hosted deployments
should track `main` and redeploy via the `.deb` package.

## Security Model

- **Encryption at rest** — uploaded files and 2FA secrets are encrypted with
  Fernet (AES-128-CBC + HMAC), using a dedicated `ENCRYPTION_KEY` kept separate
  from the JWT signing key, so key rotation never renders files unrecoverable.
- **Authentication** — JWT access/refresh tokens with refresh-token rotation and
  replay detection; optional TOTP two-factor authentication.
- **Transport** — intended to run behind the bundled Caddy reverse proxy, which
  terminates TLS and sets security headers (HSTS, frame-options, CSP).
- **Process hardening** — the systemd unit runs as an unprivileged user with
  `NoNewPrivileges`, `ProtectSystem=strict`, and `PrivateTmp`.
- **Rate limiting** — global and stricter auth-endpoint limits to blunt brute
  force and credential-stuffing attacks.

See [`docs/`](docs/) for the full design and threat model.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security problems.**

Report vulnerabilities privately by opening a
[private security advisory](https://github.com/security/advisories/new) or
emailing the maintainer directly. Include:

- A description of the issue and its impact.
- Steps to reproduce (proof of concept, logs, or screenshots).
- Any affected versions.

You will receive an acknowledgement within 72 hours. Please allow reasonable
time for a fix to be developed before any public disclosure.

## Scope

**In scope:** the application code in this repository, its authentication,
encryption, and packaging.

**Out of scope:** the underlying operating system, your Ollama or cloud AI
provider, or misconfiguration of your deployment (weak secrets, exposed ports,
missing TLS).
