# Contributing to VALENCE

Thank you for your interest in contributing to VALENCE GRC. This document explains how to get started and what we expect from pull requests.

## Before you begin

1. Read [docs/adr/README.md](docs/adr/README.md) to understand architectural constraints.
2. Run `./scripts/verify_public_repo.sh` — it enforces [ADR-0008](docs/adr/0008-repository-publication-boundaries.md) and blocks demo media, internal roadmaps, and secrets from being committed.
3. Never commit `.env`, database files, or generated `output/` artifacts.

## Development setup

```bash
./scripts/setup_dev.sh
cp .env.example .env
source .venv/bin/activate
./run.sh
```

## Code standards

| Tool | Command |
|------|---------|
| Formatter / linter | `ruff check src tests` |
| Type checker | `mypy src/grc_dashboard` |
| Tests | `pytest tests/ -q` |

- Match existing naming, import style, and module layout.
- Keep changes focused—one logical change per pull request.
- Add tests when fixing bugs or introducing behavior that can regress.

## Pull request process

1. Fork the repository and create a feature branch from `main`.
2. Ensure CI passes locally (lint, mypy, pytest, public-repo verify).
3. Open a pull request using the provided template.
4. A maintainer will review within a few business days.

## Reporting issues

- **Bugs**: Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
- **Features**: Use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
- **Security**: Do **not** open public issues. Email details per [SECURITY.md](SECURITY.md).

## Architecture changes

Significant design changes require a new ADR in `docs/adr/` before implementation. Follow the numbering scheme and update [docs/adr/README.md](docs/adr/README.md).
