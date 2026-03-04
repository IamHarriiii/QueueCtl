# Changelog

All notable changes to queuectl are documented in this file.

## [2.0.0] - 2026-03-04

### Added
- **CLI Integration** — All 16 commands unified in `cli.py` (enqueue, batch, schedule, cancel, logs, audit, status, list, dlq, config, migrate, metrics, webhook, dashboard, completions, worker)
- **`--command` flag** — `queuectl enqueue --command "echo hello"` as alternative to JSON
- **`--json-output` flag** — Machine-readable output on status, list, logs, dlq, metrics, config, webhook commands
- **Batch enqueue** — `queuectl batch jobs.json` to enqueue multiple jobs at once
- **Cron scheduling** — `queuectl schedule --cron "0 2 * * *"` for recurring jobs
- **Worker pools** — `queuectl worker start --pool gpu` + `queuectl enqueue --pool gpu`
- **Job tags** — `queuectl enqueue --tags "batch,nightly"` + `queuectl list --tag batch`
- **Audit trail** — `queuectl audit job123` shows all state transitions
- **Job logs viewer** — `queuectl logs job123` shows stdout/stderr/exit code
- **Shell completions** — `queuectl completions --shell zsh`
- **Webhook HMAC signing** — SHA-256 signatures for payload authentication
- **Webhook rate limiting** — Token bucket limiter (configurable per minute)
- **Command validation** — Block dangerous patterns (rm -rf /, fork bombs, mkfs)
- **Web dashboard auth** — API token authentication via `QUEUECTL_API_TOKEN` env var
- **Audit log table** — Records all job state transitions with timestamps
- **Database migration v6** — Adds audit_log table and tag/pool indexes
- **Dependency-aware workers** — Check `DependencyResolver.are_dependencies_met()` before execution
- **Webhook dispatch in worker** — Fires webhooks on job.started/completed/failed/timeout events
- **Docker support** — `Dockerfile` + `docker-compose.yml` with dashboard, workers, GPU pool
- **GitHub Actions CI** — Lint + test matrix (Python 3.8-3.12) + Docker build
- **SECURITY.md** — Security considerations documentation
- **Pytest unit tests** — Comprehensive unit test suite with fixtures

### Changed
- **Version** — 1.0.0 → 2.0.0
- **Author** — "Your Name" → "HARINARAYANAN U"
- **Storage** — All methods now use context manager pattern (`with self._get_conn()`)
- **SQLite mode** — WAL journal mode + busy_timeout for better concurrency
- **Logging** — Replaced all `print()` with Python `logging` module
- **Models** — Added `__repr__`, `get_tags_list()`, `has_tag()`, `is_retryable()`
- **Config** — Added `priority_inheritance`, `command_validation`, `webhook_rate_limit` keys
- **Config.get_all()** — Now merges defaults with stored values
- **Claim query** — Now filters by worker pool (`AND (pool IS NULL OR pool = ?)`)
- **requirements.txt** — Added missing `click`, `requests`, `croniter`
- **setup.py** — Full metadata, classifiers, dev extras, all install_requires

### Fixed
- Enhanced CLI commands (`cli_enhanced.py`, `cli_webhooks.py`) were never registered in main CLI — now fully integrated
- `requirements.txt` was missing `click` and `requests` — added
- `setup.py` author was placeholder — set to "HARINARAYANAN U"

## [1.0.0] - Initial Release

### Features
- Core job queue with SQLite persistence
- Multi-worker processing with atomic job claiming
- Retry logic with exponential backoff
- Dead Letter Queue (DLQ)
- Job priority (low/medium/high)
- Job dependencies with DAG resolution
- Job cancellation
- Metrics tracking
- Webhook notifications
- Database migrations (v2-v5)
- Web dashboard with Socket.IO
- Configurable settings via CLI
