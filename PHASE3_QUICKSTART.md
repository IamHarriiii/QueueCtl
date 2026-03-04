# 🚀 queuectl v2.0.0 - Quick Start Guide

This guide covers the new features introduced in v2.0.0.

## What's New

| Feature | Command |
|---------|---------|
| Priority + timeout | `queuectl enqueue --command "echo hi" --priority high --timeout 60` |
| Worker pools | `queuectl worker start --pool gpu` |
| Job tags | `queuectl enqueue --command "train.py" --tags "ml,batch"` |
| Cron scheduling | `queuectl schedule --command "backup.py" --cron "0 2 * * *"` |
| Batch enqueue | `queuectl batch jobs.json` |
| Webhooks | `queuectl webhook add --url https://... --events "job.completed"` |
| Job logs | `queuectl logs job123` |
| Audit trail | `queuectl audit job123` |
| Metrics | `queuectl metrics show` |
| JSON output | `queuectl status --json-output` |
| Web dashboard | `queuectl dashboard --port 5000` |
| Docker | `docker-compose up -d` |

## Step 1: Upgrade Database

```bash
queuectl migrate run
queuectl migrate status
```

## Step 2: Try the New Enqueue

```bash
# Old way still works
queuectl enqueue '{"command":"echo hello"}'

# New --command flag (much easier!)
queuectl enqueue --command "echo hello" --priority high --timeout 60

# With tags and pool
queuectl enqueue --command "train_model.py" --tags "ml,gpu" --pool gpu

# With dependencies
queuectl enqueue --command "step2.sh" --depends-on "job-step1"
```

## Step 3: Worker Pools

```bash
# Start general workers
queuectl worker start --count 3

# Start GPU pool workers (only process --pool gpu jobs)
queuectl worker start --count 1 --pool gpu
```

## Step 4: Cron Scheduling

```bash
# Schedule a nightly backup (next 7 runs)
queuectl schedule --command "python backup.py" --cron "0 2 * * *" --count 7

# Schedule hourly health check
queuectl schedule --command "curl localhost/health" --cron "0 * * * *" --count 24
```

## Step 5: Batch Enqueue

Create a `jobs.json` file:
```json
[
  {"command": "echo job1", "priority": 2},
  {"command": "echo job2", "priority": 0, "tags": "batch"},
  {"command": "echo job3", "timeout": 30}
]
```

```bash
queuectl batch jobs.json
```

## Step 6: Webhooks

```bash
# Add webhook with HMAC authentication
queuectl webhook add --url https://api.example.com/hook \
  --events "job.completed,job.failed" \
  --secret "my-webhook-secret"

# List and test
queuectl webhook list
queuectl webhook test --url https://api.example.com/hook
```

## Step 7: Monitoring

```bash
# View job logs
queuectl logs job123

# View audit trail (state transitions)
queuectl audit job123

# Metrics
queuectl metrics show --period 24

# Web dashboard (with API auth)
export QUEUECTL_API_TOKEN=my-secret-token
queuectl dashboard --port 5000
```

## Step 8: Docker Deployment

```bash
docker-compose up -d
# Dashboard: http://localhost:5000
# Workers: 3 processes auto-started
```

## Step 9: JSON Output for Scripting

```bash
# Pipe to jq for processing
queuectl status --json-output | jq '.jobs.pending'
queuectl list --state completed --json-output | jq '.[].id'
```

## Configuration Reference

```bash
queuectl config set max-retries 5
queuectl config set command-validation true    # Block dangerous commands
queuectl config set priority-inheritance true  # Auto-upgrade dep priorities
queuectl config set webhook-rate-limit 100     # Max webhook calls/min
```

## Shell Completions

```bash
queuectl completions --shell bash >> ~/.bashrc
queuectl completions --shell zsh >> ~/.zshrc
source ~/.zshrc  # reload
```

---

For full documentation, see [README.md](README.md).
