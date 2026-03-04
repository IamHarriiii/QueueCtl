# queuectl - Background Job Queue System

[![CI](https://github.com/IamHarriiii/Queuectl/actions/workflows/ci.yml/badge.svg)](https://github.com/IamHarriiii/Queuectl/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-2.0.0-orange.svg)](CHANGELOG.md)

A production-grade CLI-based background job queue system with worker processes, retry logic with exponential backoff, Dead Letter Queue (DLQ), webhooks, cron scheduling, job dependencies, web dashboard, and Docker support.

## 🎯 Features

### Core
- ✅ **Job Queue Management** — Enqueue, cancel, schedule, and batch-enqueue jobs
- ✅ **Multiple Workers** — Concurrent worker processes with pool support
- ✅ **Automatic Retries** — Failed jobs retry with exponential backoff
- ✅ **Dead Letter Queue** — Permanently failed jobs moved to DLQ
- ✅ **Persistent Storage** — SQLite with WAL mode survives restarts
- ✅ **Safety Timeout** — Auto-recovery of jobs from crashed workers (5 min)
- ✅ **Job Output Logging** — Capture stdout, stderr, and exit codes
- ✅ **Configurable** — Runtime configuration via CLI
- ✅ **Clean CLI Interface** — 16 intuitive commands with `--json-output` support

### v2.0.0 Enhancements
- ✅ **Job Priority Queues** — Low/medium/high with priority inheritance
- ✅ **Job Dependencies** — DAG-based dependencies with cycle detection
- ✅ **Worker Pools** — Route jobs to specialized workers (e.g., GPU, CPU, IO pool)
- ✅ **Job Tags** — Categorize and filter jobs by tags
- ✅ **Cron Scheduling** — Schedule recurring jobs with cron expressions
- ✅ **Batch Enqueue** — Enqueue multiple jobs from a JSON file
- ✅ **Webhook Notifications** — HTTP callbacks with HMAC signing & rate limiting
- ✅ **Metrics & Statistics** — Track execution time, success rate, worker utilization
- ✅ **Audit Trail** — Full state transition history for every job
- ✅ **Web Dashboard** — Real-time monitoring with WebSocket, API token auth
- ✅ **Command Validation** — Block dangerous patterns (rm -rf /, fork bombs)
- ✅ **Database Migrations** — Safe schema upgrades with rollback support
- ✅ **Docker Support** — Dockerfile + docker-compose for deployment
- ✅ **CI/CD** — GitHub Actions pipeline for lint + test + Docker build
- ✅ **Shell Completions** — Bash/Zsh/Fish autocomplete

## 📋 Requirements

- Python 3.8+
- Dependencies: click, requests, flask, flask-cors, flask-socketio, croniter

## 🚀 Setup Instructions

### 1. Clone and Install

```bash
git clone https://github.com/IamHarriiii/Queuectl.git
cd Queuectl
pip install -r requirements.txt
pip install -e .
```

### 2. Run Migrations

```bash
queuectl migrate run
```

### 3. Verify Installation

```bash
queuectl --version   # queuectl, version 2.0.0
queuectl --help
```

### Docker Setup (Alternative)

```bash
docker-compose up -d
```

This starts the web dashboard on port 5000 and 3 worker processes.

## 💻 Usage Examples

### Enqueue Jobs

```bash
# Simple job
queuectl enqueue '{"command":"echo Hello World"}'

# Using --command flag with priority and timeout
queuectl enqueue --command "echo hello" --priority high --timeout 60

# With tags and worker pool
queuectl enqueue --command "train_model.py" --priority high --tags "ml,batch" --pool gpu

# With delay
queuectl enqueue --command "cleanup.sh" --delay 3600

# With dependencies
queuectl enqueue --command "step2.py" --depends-on "job-step1"

# Batch enqueue from file
queuectl batch jobs.json
```

### Cron Scheduling

```bash
# Schedule 5 future runs of a backup job
queuectl schedule --command "python backup.py" --cron "0 2 * * *" --count 5

# Schedule hourly health check
queuectl schedule --command "curl http://localhost/health" --cron "0 * * * *" --count 24
```

### Worker Management

```bash
# Start 3 workers
queuectl worker start --count 3

# Start workers for a specific pool
queuectl worker start --count 2 --pool gpu

# Stop all workers
queuectl worker stop
```

### Queue Status & Listing

```bash
# Check status
queuectl status
queuectl status --json-output

# List jobs with filters
queuectl list --state pending --priority high
queuectl list --tag nightly --limit 50
queuectl list --json-output

# View job logs
queuectl logs job123

# View audit trail
queuectl audit job123
```

### Job Lifecycle Operations

```bash
# Cancel a job
queuectl cancel job123

# Retry from Dead Letter Queue
queuectl dlq list
queuectl dlq retry job123
```

### Webhook Management

```bash
# Add webhook for job events
queuectl webhook add --url https://example.com/hook --events "job.completed,job.failed"

# Add webhook with secret (HMAC authentication)
queuectl webhook add --url https://api.example.com/webhook --events "*" --secret "mysecret123"

# List, toggle, test webhooks
queuectl webhook list
queuectl webhook toggle webhook-abc123 --disable
queuectl webhook test --url https://example.com/hook
```

### Metrics & Monitoring

```bash
# Show metrics dashboard
queuectl metrics show --period 24

# Export metrics as JSON/CSV
queuectl metrics export --format json --output metrics.json

# Launch web dashboard
queuectl dashboard --port 8080
```

### Configuration

```bash
queuectl config list
queuectl config set max-retries 5
queuectl config set job-timeout 600
queuectl config set command-validation true
queuectl config set webhook-rate-limit 100
```

### Shell Completions

```bash
queuectl completions --shell bash >> ~/.bashrc
queuectl completions --shell zsh >> ~/.zshrc
```

## 🏗️ Architecture Overview

### Components

```
┌─────────────┐
│   CLI       │  16 commands with --json-output
└──────┬──────┘
       │
┌──────▼──────┐     ┌──────────────┐
│   Queue     │────▶│ Dependencies │  DAG resolution
└──────┬──────┘     └──────────────┘
       │
┌──────▼──────┐     ┌──────────────┐
│  Storage    │────▶│  Audit Log   │  State transitions
└──────┬──────┘     └──────────────┘
       │
┌──────▼──────┐     ┌──────────────┐     ┌──────────────┐
│  Workers    │────▶│  Webhooks    │────▶│  Metrics     │
└──────┬──────┘     └──────────────┘     └──────────────┘
       │
┌──────▼──────┐
│  Executor   │  subprocess with validation
└─────────────┘

┌─────────────┐
│  Web Dashboard  │  Flask + Socket.IO (optional)
└─────────────┘
```

### Job Lifecycle

```
[ENQUEUE] ──→ PENDING ──→ PROCESSING ──→ COMPLETED ✓
                 ↑             ↓
                 │        FAILED (attempts < max_retries)
                 │             ↓
                 └─────── (exponential backoff wait)
                               ↓
                          DEAD (DLQ) ✗

Cancellation: PENDING/PROCESSING ──→ CANCELLED ✗
```

### Worker Coordination

**Atomic Job Claiming** (priority-aware, pool-filtered):
```sql
UPDATE jobs 
SET state='processing', worker_id=?, locked_at=CURRENT_TIMESTAMP
WHERE id IN (
    SELECT id FROM jobs
    WHERE (state='pending' OR (state='processing' AND locked_at < datetime('now', '-5 minutes')))
    AND (run_at IS NULL OR run_at <= CURRENT_TIMESTAMP)
    AND cancelled_at IS NULL
    AND (pool IS NULL OR pool = ?)
    ORDER BY priority DESC, created_at ASC
    LIMIT 1
)
```

## 🔧 Configuration Options

| Key | Default | Description |
|-----|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts before DLQ |
| `backoff_base` | 2 | Base for exponential backoff calculation |
| `job_timeout` | 300 | Job execution timeout in seconds |
| `worker_poll_interval` | 1 | Worker polling interval in seconds |
| `priority_inheritance` | true | Auto-upgrade dependency priorities |
| `command_validation` | true | Block dangerous command patterns |
| `webhook_rate_limit` | 100 | Max webhook calls per minute |

## 📊 Project Structure

```
queuectl/
├── queuectl/
│   ├── __init__.py        # Package init, v2.0.0
│   ├── cli.py             # 16 CLI commands (Click)
│   ├── queue.py           # Queue operations
│   ├── worker.py          # Workers, pools, dependency checking
│   ├── storage.py         # SQLite layer, audit log, validation
│   ├── config.py          # Configuration management
│   ├── models.py          # Job model, states, priorities
│   ├── dependencies.py    # DAG dependency resolver
│   ├── metrics.py         # Metrics tracking & export
│   ├── webhooks.py        # Webhook dispatch, rate limiting, HMAC
│   ├── migrations.py      # Database migration system
│   ├── utils.py           # Utility functions
│   └── web/
│       ├── app.py         # Flask dashboard with API auth
│       └── templates/     # Dashboard HTML templates
├── tests/
│   ├── test_scenarios.py          # Core integration tests
│   ├── test_phase1_enhancements.py # Priority & metrics tests
│   ├── test_phase2.py             # Dependency tests
│   ├── test_phase3.py             # Webhook & timeout tests
│   └── test_unit.py               # Pytest unit tests
├── .github/workflows/ci.yml   # GitHub Actions CI/CD
├── Dockerfile                  # Docker container
├── docker-compose.yml          # Multi-service deployment
├── ARCHITECTURE.md             # Detailed architecture docs
├── CHANGELOG.md                # Version history
├── SECURITY.md                 # Security considerations
├── requirements.txt            # Python dependencies
└── setup.py                    # Package setup
```

## 🧪 Testing

```bash
# Run all tests
python tests/test_scenarios.py
python tests/test_phase1_enhancements.py
python tests/test_phase2.py
python tests/test_phase3.py

# Run pytest unit tests
pip install pytest
pytest tests/test_unit.py -v
```

## 🐛 Known Limitations

1. **Single Machine Only** — SQLite doesn't support distributed deployment
2. **`shell=True`** — Mitigated by command validation, but not fully sandboxed
3. **No Authentication on CLI** — Assumes trusted local environment
4. **SQLite Concurrency** — Limited write concurrency under very high load

See [SECURITY.md](SECURITY.md) for security considerations.

## 🎥 Demo 

https://drive.google.com/file/d/1xGuwrG4USCyO1zYnsmwxv8DplZ3bvC3A/view?usp=sharing

## 📄 License

This project is created for educational purposes as part of a backend developer internship assignment.

## 👤 Author

**HARINARAYANAN U**  
hari.narayanan1402@gmail.com  
https://github.com/IamHarriiii

---
