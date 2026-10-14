# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's
**Security → Report a vulnerability** on this repository (private advisory), and include what you found,
how to reproduce it and which version (`VERSION` file) you tested.

You will get an answer within a few days. Fixes are released as a new version and noted in `CHANGELOG.md`.

## How secrets are handled

- `DJANGO_SECRET_KEY` and `ENGINE_API_TOKEN` live in the `.env` file, never in the code and never in git.
  Outside development (`DJANGO_DEBUG=False`) the web app refuses to start if either is empty, a known
  placeholder or shorter than 32 characters.
- The installed desktop app generates both on first run (`secrets.token_urlsafe(50)`) and stores them in
  `config\.env` in its data folder.
- The engine reads its token from the environment variable named in `engine.yaml` (`web.token_env`); the token
  is never written in `engine.yaml`.
- Tokens are not written to logs.

## What is exposed on the network

- The web console listens on `127.0.0.1` by default.
- The engine's live view (`render.stream_host`) listens on `127.0.0.1` by default. It has **no login**.
  If you share it with the network, restrict it with a firewall rule.
- Snapshots are served only to signed-in users, never as public files.

## Data

The system stores events, snapshots and the employee list (code, name, department). It stores no photos of
employees and no biometric templates. The engine never sends a name: only an operator assigns a person to an event.
