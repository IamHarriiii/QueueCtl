<div align="center">

# QueueCtl

**A production-grade CLI job queue with workers, retries, webhooks, cron scheduling, and a real-time dashboard.**

[![CI](https://github.com/IamHarriiii/Queuectl/actions/workflows/ci.yml/badge.svg)](https://github.com/IamHarriiii/Queuectl/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/queuectl?color=blue&label=PyPI)](https://pypi.org/project/queuectl/)
[![Python](https://img.shields.io/pypi/pyversions/queuectl)](https://pypi.org/project/queuectl/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/queuectl?color=brightgreen)](https://pypi.org/project/queuectl/)

[Installation](#-installation) · [Quick Start](#-quick-start) · [Features](#-features) · [Documentation](#-documentation) · [Contributing](#-contributing)

</div>

---

## Why queuectl?

Most job queues require Redis, RabbitMQ, or a separate broker. **queuectl doesn't.** It's a single `pip install` — powered by SQLite — that gives you everything you need to run background jobs on a single machine.

```bash
pip install queuectl
queuectl enqueue --command "python train_model.py" --priority high --tags "ml"
queuectl worker start --count 4
```

That's it. No Redis. No Docker. No config files. Just a CLI that works.

---

## ✨ Features

<table>
<tr>
<td width="50%">

**🔧 Core Engine**
- Atomic job claiming (no duplicates)
- Exponential backoff retries
- Dead Letter Queue for permanent failures
- Job timeout with auto-recovery
- SQLite + WAL mode (zero config)

</td>
<td width="50%">

**🚀 Advanced**
- Priority queues (low / medium / high)
- DAG-based job dependencies
- Worker pools (GPU, CPU, IO)
- Job tagging & filtering
- Cron scheduling

</td>
</tr>
<tr>
<td width="50%">

**📡 Integrations**
- Webhook notifications (HMAC signed)
- Real-time web dashboard
- JSON output for scripting
- Shell completions (bash/zsh/fish)
- Docker & docker-compose

</td>
<td width="50%">

**🛡️ Production Ready**
- 86 tests across 5 test suites
- Command validation (blocks `rm -rf /`)
- API token authentication
- Audit trail for every job
- GitHub Actions CI/CD

</td>
</tr>
</table>

---

## 📦 Installation

```bash
pip install queuectl
```

Or install from source:

```bash
git clone https://github.com/IamHarriiii/Queuectl.git
cd Queuectl
pip install -e ".[all]"   # includes dev + realtime extras
queuectl migrate run
```

<details>
<summary><b>🐳 Docker</b></summary>

```bash
git clone https://github.com/IamHarriiii/Queuectl.git
cd Queuectl
docker-compose up -d
# Dashboard → http://localhost:5000
# 3 workers auto-started
```

</details>

---

## 🚀 Quick Start

### 1. Enqueue a job

```bash
queuectl enqueue --command "echo Hello World"
```

### 2. Start workers

```bash
queuectl worker start --count 3
```

### 3. Check status

```bash
queuectl status
```

```
==================================================
QUEUE STATUS
==================================================

Jobs:
  Pending:        0
  Processing:     1
  Completed:     12
  Failed:         0
  Dead (DLQ):     0
  --------------------
  Total:         13

Active Workers: 3
==================================================
```

### 4. Open the dashboard

```bash
queuectl dashboard
# → http://localhost:5000
```

---

## 📖 Documentation

### Enqueue Jobs

```bash
# With priority, timeout, tags, and pool
queuectl enqueue --command "python train.py" \
  --priority high \
  --timeout 3600 \
  --tags "ml,nightly" \
  --pool gpu

# With dependencies
queuectl enqueue --command "step2.py" --depends-on "job-step1"

# Delayed execution (1 hour from now)
queuectl enqueue --command "cleanup.sh" --delay 3600

# Batch from file
queuectl batch jobs.json

# JSON input (legacy)
queuectl enqueue '{"command":"echo hi", "priority": 2}'
```

### Cron Scheduling

```bash
# Nightly backup at 2am (next 30 runs)
queuectl schedule --command "python backup.py" --cron "0 2 * * *" --count 30

# Hourly health check
queuectl schedule --command "curl localhost/health" --cron "0 * * * *" --count 24
```

### Worker Pools

```bash
# General workers
queuectl worker start --count 3

# GPU pool — only processes jobs with --pool gpu
queuectl worker start --count 1 --pool gpu
```

### Monitoring

```bash
queuectl logs job123          # stdout + stderr + exit code
queuectl audit job123         # full state transition history
queuectl metrics show         # success rate, avg time, throughput
queuectl list --state failed  # filter by state, tag, priority
```

### Webhooks

```bash
# HMAC-signed webhook with rate limiting
queuectl webhook add \
  --url https://api.example.com/hook \
  --events "job.completed,job.failed" \
  --secret "my-webhook-secret"
```

<details>
<summary><b>Webhook payload example</b></summary>

```json
{
  "event": "job.completed",
  "job_id": "abc-123",
  "command": "echo hello",
  "state": "completed",
  "exit_code": 0,
  "timestamp": "2026-03-04T08:00:00"
}
```

Headers include `X-Webhook-Signature` with HMAC-SHA256 signature.

</details>

### JSON Output for Scripting

```bash
# Pipe to jq
queuectl status --json-output | jq '.jobs.pending'
queuectl list --json-output | jq '.[] | select(.state=="failed")'
```

### Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `max_retries` | 3 | Max retry attempts before DLQ |
| `backoff_base` | 2 | Exponential backoff base |
| `job_timeout` | 300 | Execution timeout (seconds) |
| `worker_poll_interval` | 1 | Poll interval (seconds) |
| `command_validation` | true | Block dangerous commands |
| `priority_inheritance` | true | Deps inherit parent priority |
| `webhook_rate_limit` | 100 | Max webhook calls/minute |

```bash
queuectl config set max-retries 5
queuectl config list
```

---

## 🏗️ Architecture

```
                    ┌──────────────────────┐
                    │      CLI (16 cmds)   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐
     │    Queue     │  │  Scheduler  │  │  Dashboard  │
     │  (enqueue,   │  │   (cron)    │  │  (Flask +   │
     │   cancel)    │  │             │  │  Socket.IO) │
     └────────┬─────┘  └──────┬──────┘  └─────────────┘
              │               │
     ┌────────▼───────────────▼──────┐
     │         Storage (SQLite)      │
     │  WAL mode · Atomic claims     │
     │  Audit log · Migrations       │
     └────────────────┬──────────────┘
                      │
     ┌────────────────▼──────────────┐
     │       Worker Processes        │
     │  Pool routing · Dep checking  │
     │  Timeout · Retry · Webhooks   │
     └──────────────────────────────┘
```

**Job Lifecycle:**
```
ENQUEUE → PENDING → PROCESSING → COMPLETED ✓
              ↑          ↓
              └── FAILED (retry with backoff)
                     ↓
                  DEAD (DLQ) ✗
```

---

## 🧪 Testing

86 tests across 5 test suites:

```bash
pytest tests/test_unit.py -v           # 69 unit tests
python tests/test_scenarios.py         #  6 integration tests
python tests/test_phase1_enhancements.py  #  4 priority/metrics tests
python tests/test_phase2.py            #  3 dependency tests
python tests/test_phase3.py            #  4 webhook/timeout tests
```

---

## 📂 Project Structure

```
queuectl/
├── queuectl/
│   ├── cli.py             # 16 CLI commands
│   ├── queue.py            # Job queue operations
│   ├── worker.py           # Worker processes + pools
│   ├── storage.py          # SQLite layer + audit log
│   ├── dependencies.py     # DAG dependency resolver
│   ├── webhooks.py         # Webhook dispatch + HMAC
│   ├── metrics.py          # Stats tracking + export
│   ├── migrations.py       # Schema migration system
│   ├── models.py           # Job model + states
│   ├── config.py           # Configuration management
│   ├── utils.py            # Utilities
│   └── web/                # Flask dashboard
├── tests/                  # 5 test suites (86 tests)
├── .github/workflows/      # CI + PyPI auto-publish
├── Dockerfile              # Container support
├── docker-compose.yml      # Multi-service deployment
├── pyproject.toml          # Modern packaging
└── setup.py                # Legacy packaging
```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a PR.

```bash
git clone https://github.com/IamHarriiii/Queuectl.git
cd Queuectl
pip install -e ".[dev]"
pytest tests/test_unit.py -v
```

See the [open issues](https://github.com/IamHarriiii/Queuectl/issues) for things to work on.

---

## 📜 License

MIT © [HARINARAYANAN U](https://github.com/IamHarriiii)

---

<div align="center">

**If you find this useful, please ⭐ the repo!**

[Report a Bug](https://github.com/IamHarriiii/Queuectl/issues/new?template=bug_report.md) · [Request a Feature](https://github.com/IamHarriiii/Queuectl/issues/new?template=feature_request.md)

</div>
