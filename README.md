# Telegram University Content Collector

Production-oriented Python system for collecting educational files from authorized Telegram channels, preparing them for text extraction, OCR, classification, storage, and reporting.

Current implementation status: local/testable implementation is complete for configuration, logging, Telegram login wiring, incremental collection, file download/hash/deduplication, database persistence, PDF extraction, OCR hooks, classification validation, storage organization, reporting, lock protection, retry helpers, deployment examples, a JSON web API, and a connected admin frontend.

The only acceptance item not verifiable in this workspace is a live authorized Telegram channel test. Run `python -m app.cli telegram-login` on the client VPS, then test `collect --channel <name> --limit 5` with an authorized channel.

## Phase Plan

1. Project skeleton, configuration, logging.
2. Telegram authentication and persistent session.
3. Read one configured Telegram channel.
4. Incremental message tracking.
5. File downloading.
6. SHA-256 duplicate detection.
7. Database persistence.
8. PDF text extraction.
9. Arabic OCR.
10. Classification service.
11. Unclassified validation.
12. Storage organization.
13. Reports.
14. Queue/workers if required.
15. FloodWait, retry, and locking.
16. Full integration tests.
17. VPS deployment.
18. Live test with one authorized channel.
19. Final documentation.

## Quick Start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m app.cli health-check
pytest
```

## Commands

```bash
python -m app.cli health-check
python -m app.cli init-db
python -m app.cli telegram-login
python -m app.cli collect --channel database --limit 5
python -m app.cli process
python -m app.cli report
python -m app.cli serve --host 127.0.0.1 --port 8000
```

The web app includes CRUD controls for channels, subjects, messages, files, classifications, and runs, plus report metrics, manual process/collect actions, and a demo seed action.

For production MySQL, run Alembic:

```bash
alembic upgrade head
```

## Configuration

Channels are loaded from `config/channels.yaml`; adding a channel should only require editing that file.

Subjects are loaded from `config/subjects.yaml`; later classification stages will only accept subject codes defined there.

Secrets belong in `.env` or the VPS secret manager, never in Git.

## Local Infrastructure

```bash
docker compose up -d mysql redis
```

Docker is optional. You can use a local MySQL install, such as Homebrew on macOS, or run MySQL and Redis with Compose for an isolated demo environment. Redis is included for future worker expansion. The current baseline keeps processing synchronous and cron-driven to avoid unnecessary queue complexity.
