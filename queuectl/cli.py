"""
CLI interface for queuectl
Fully integrated command-line interface for all queue operations
Includes: enqueue, worker, status, list, dlq, config, cancel, metrics,
          migrate, webhook, logs, batch, completions
"""
import click
import json
import sys
import os
from pathlib import Path
from typing import Optional

from .storage import Storage
from .config import Config
from .queue import Queue
from .worker import WorkerManager
from .models import JobState, JobPriority


# Initialize storage, config, and queue (lazy loaded)
_storage = None
_config = None
_queue = None


def get_storage():
    """Get or create storage instance"""
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


def get_config():
    """Get or create config instance"""
    global _config
    if _config is None:
        _config = Config(get_storage())
    return _config


def get_queue():
    """Get or create queue instance"""
    global _queue
    if _queue is None:
        _queue = Queue(get_storage(), get_config())
    return _queue


def _output_json(data):
    """Output data as formatted JSON"""
    click.echo(json.dumps(data, indent=2, default=str))


# ============================================================================
# MAIN CLI GROUP
# ============================================================================

@click.group()
@click.version_option(version="2.0.0", prog_name="queuectl")
def cli():
    """queuectl - A production-grade CLI-based background job queue system"""
    pass


# ============================================================================
# ENQUEUE COMMAND (enhanced with --command, --priority, --timeout)
# ============================================================================

@cli.command()
@click.argument('job_json', required=False)
@click.option('--command', '-c', help='Job command (alternative to JSON)')
@click.option('--priority', '-p', type=click.Choice(['low', 'medium', 'high']),
              default='medium', help='Job priority')
@click.option('--max-retries', '-r', type=int, help='Maximum retry attempts')
@click.option('--timeout', '-t', type=int, help='Job timeout in seconds')
@click.option('--tags', help='Comma-separated tags for the job')
@click.option('--pool', help='Worker pool to assign the job to')
@click.option('--delay', type=int, help='Delay in seconds before job runs')
@click.option('--depends-on', help='Comma-separated job IDs this job depends on')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def enqueue(job_json, command, priority, max_retries, timeout, tags, pool, delay, depends_on, json_out):
    """
    Enqueue a new job

    Examples:
      queuectl enqueue '{"command":"echo hello"}'
      queuectl enqueue --command "echo hello" --priority high --timeout 60
      queuectl enqueue --command "sleep 5" --tags "batch,nightly" --pool gpu
    """
    try:
        if job_json:
            job_data = json.loads(job_json)
        elif command:
            job_data = {'command': command}
        else:
            click.echo("✗ Either job_json argument or --command option is required", err=True)
            sys.exit(1)

        # Apply CLI options
        job_data['priority'] = JobPriority.from_string(priority)

        if max_retries is not None:
            job_data['max_retries'] = max_retries
        if timeout is not None:
            job_data['timeout'] = timeout
        if tags:
            job_data['tags'] = tags
        if pool:
            job_data['pool'] = pool

        queue = get_queue()

        if delay:
            job = queue.schedule_job(job_data, delay)
        else:
            job = queue.enqueue(job_data)

        if job:
            # Handle dependencies
            if depends_on:
                try:
                    from .dependencies import DependencyResolver
                    resolver = DependencyResolver(get_storage())
                    dep_ids = [d.strip() for d in depends_on.split(',')]
                    for dep_id in dep_ids:
                        resolver.add_dependency(job.id, dep_id)
                except Exception as e:
                    click.echo(f"⚠ Job enqueued but dependency setup failed: {e}", err=True)

            if json_out:
                _output_json(job.to_dict())
            else:
                click.echo(f"✓ Job enqueued successfully")
                click.echo(f"  ID: {job.id}")
                click.echo(f"  Command: {job.command}")
                click.echo(f"  Priority: {job.get_priority_name()}")
                if job.timeout:
                    click.echo(f"  Timeout: {job.timeout}s")
                if tags:
                    click.echo(f"  Tags: {tags}")
                if pool:
                    click.echo(f"  Pool: {pool}")
                if delay:
                    click.echo(f"  Delayed: {delay}s")
                if depends_on:
                    click.echo(f"  Depends on: {depends_on}")
                click.echo(f"  State: {job.state}")
        else:
            click.echo(f"✗ Failed to enqueue job (ID may already exist)", err=True)
            sys.exit(1)

    except json.JSONDecodeError as e:
        click.echo(f"✗ Invalid JSON: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# BATCH ENQUEUE COMMAND
# ============================================================================

@cli.command('batch')
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def batch_enqueue(file_path, json_out):
    """
    Enqueue multiple jobs from a JSON file

    The file should contain a JSON array of job objects.

    Example: queuectl batch jobs.json
    """
    try:
        with open(file_path, 'r') as f:
            jobs_data = json.load(f)

        if not isinstance(jobs_data, list):
            click.echo("✗ File must contain a JSON array of job objects", err=True)
            sys.exit(1)

        queue = get_queue()
        results = []
        success_count = 0
        fail_count = 0

        for job_data in jobs_data:
            try:
                job = queue.enqueue(job_data)
                if job:
                    success_count += 1
                    results.append({'id': job.id, 'status': 'enqueued'})
                else:
                    fail_count += 1
                    results.append({'id': job_data.get('id', 'unknown'), 'status': 'failed'})
            except Exception as e:
                fail_count += 1
                results.append({'id': job_data.get('id', 'unknown'), 'status': 'error', 'error': str(e)})

        if json_out:
            _output_json({'total': len(jobs_data), 'success': success_count, 'failed': fail_count, 'results': results})
        else:
            click.echo(f"✓ Batch enqueue complete: {success_count} succeeded, {fail_count} failed out of {len(jobs_data)} jobs")
            for r in results:
                status_icon = "✓" if r['status'] == 'enqueued' else "✗"
                click.echo(f"  {status_icon} {r['id']}: {r['status']}")

    except json.JSONDecodeError as e:
        click.echo(f"✗ Invalid JSON in file: {e}", err=True)
        sys.exit(1)


# ============================================================================
# WORKER COMMANDS
# ============================================================================

@cli.group()
def worker():
    """Worker management commands"""
    pass


@worker.command()
@click.option('--count', default=1, help='Number of workers to start')
@click.option('--pool', help='Worker pool name (only process matching jobs)')
def start(count, pool):
    """
    Start worker processes

    Example: queuectl worker start --count 3 --pool gpu
    """
    storage = get_storage()
    config = get_config()

    manager = WorkerManager(storage, config, pool=pool)
    manager.start_workers(count)


@worker.command()
def stop():
    """
    Stop running workers

    Creates a stop file that workers detect and shutdown gracefully.
    """
    stop_file = Path.home() / ".queuectl" / "stop"
    stop_file.touch()
    click.echo("✓ Stop signal sent to all workers")
    click.echo("  Workers will finish current jobs and shutdown")
    click.echo(f"  (Stop file: {stop_file})")


# ============================================================================
# STATUS COMMAND (enhanced with cancelled jobs)
# ============================================================================

@cli.command()
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def status(json_out):
    """
    Show queue status

    Example: queuectl status
    Example: queuectl status --json-output
    """
    queue = get_queue()
    config = get_config()
    status_info = queue.get_status()

    if json_out:
        status_info['config'] = config.get_all()
        _output_json(status_info)
        return

    click.echo("=" * 50)
    click.echo("QUEUE STATUS")
    click.echo("=" * 50)

    jobs = status_info['jobs']
    click.echo(f"\nJobs:")
    click.echo(f"  Pending:    {jobs.get('pending', 0):>5}")
    click.echo(f"  Processing: {jobs.get('processing', 0):>5}")
    click.echo(f"  Completed:  {jobs.get('completed', 0):>5}")
    click.echo(f"  Failed:     {jobs.get('failed', 0):>5}")
    click.echo(f"  Cancelled:  {jobs.get('cancelled', 0):>5}")
    click.echo(f"  Dead (DLQ): {jobs.get('dead', 0):>5}")
    click.echo(f"  {'-' * 20}")
    click.echo(f"  Total:      {status_info['total_jobs']:>5}")

    click.echo(f"\nActive Workers: {status_info['active_workers']}")

    all_config = config.get_all()
    click.echo(f"\nConfiguration:")
    for key, value in sorted(all_config.items()):
        click.echo(f"  {key}: {value}")

    click.echo("=" * 50)


# ============================================================================
# LIST COMMAND (enhanced with priority, tags filtering)
# ============================================================================

@cli.command('list')
@click.option('--state', '-s',
              type=click.Choice(['pending', 'processing', 'completed', 'failed', 'dead', 'cancelled']),
              help='Filter by job state')
@click.option('--priority', '-p', type=click.Choice(['low', 'medium', 'high']),
              help='Filter by priority')
@click.option('--tag', help='Filter by tag')
@click.option('--pool', help='Filter by worker pool')
@click.option('--limit', default=20, help='Maximum number of jobs to display')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def list_jobs(state, priority, tag, pool, limit, json_out):
    """
    List jobs with optional filtering

    Example: queuectl list --state pending --priority high
    Example: queuectl list --tag nightly --json-output
    """
    queue = get_queue()
    jobs = queue.list_jobs(state)

    # Filter by priority
    if priority:
        priority_int = JobPriority.from_string(priority)
        jobs = [j for j in jobs if j.priority == priority_int]

    # Filter by tag
    if tag:
        jobs = [j for j in jobs if j.tags and tag in j.tags.split(',')]

    # Filter by pool
    if pool:
        jobs = [j for j in jobs if hasattr(j, 'pool') and j.pool == pool]

    if json_out:
        _output_json([j.to_dict() for j in jobs[:limit]])
        return

    if not jobs:
        filters = []
        if state:
            filters.append(f"state '{state}'")
        if priority:
            filters.append(f"priority '{priority}'")
        if tag:
            filters.append(f"tag '{tag}'")
        filter_str = " and ".join(filters) if filters else ""
        click.echo(f"No jobs found" + (f" with {filter_str}" if filter_str else ""))
        return

    jobs = jobs[:limit]

    click.echo("=" * 120)
    click.echo(f"{'ID':<20} {'STATE':<12} {'PRIORITY':<10} {'COMMAND':<30} {'ATTEMPTS':<10} {'TAGS':<15} {'CREATED':<20}")
    click.echo("=" * 120)

    for job in jobs:
        job_id = job.id[:18] + '..' if len(job.id) > 20 else job.id
        command = job.command[:28] + '..' if len(job.command) > 30 else job.command
        created = job.created_at[:19] if job.created_at else 'N/A'
        priority_name = job.get_priority_name()
        tags_str = (job.tags[:13] + '..') if job.tags and len(job.tags) > 15 else (job.tags or '-')

        click.echo(f"{job_id:<20} {job.state:<12} {priority_name:<10} {command:<30} {job.attempts:<10} {tags_str:<15} {created:<20}")

    if len(jobs) == limit:
        click.echo(f"\n(Showing first {limit} jobs, use --limit to see more)")

    click.echo("=" * 120)


# ============================================================================
# LOGS COMMAND (job output pagination)
# ============================================================================

@cli.command()
@click.argument('job_id')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def logs(job_id, json_out):
    """
    View job execution output (stdout, stderr, exit code)

    Example: queuectl logs job123
    """
    queue = get_queue()
    job = queue.get_job(job_id)

    if not job:
        click.echo(f"✗ Job {job_id} not found", err=True)
        sys.exit(1)

    if json_out:
        _output_json({
            'id': job.id,
            'command': job.command,
            'state': job.state,
            'exit_code': job.exit_code,
            'stdout': job.stdout,
            'stderr': job.stderr,
        })
        return

    click.echo("=" * 60)
    click.echo(f"JOB LOGS: {job.id}")
    click.echo("=" * 60)
    click.echo(f"Command:   {job.command}")
    click.echo(f"State:     {job.state}")
    click.echo(f"Exit Code: {job.exit_code if job.exit_code is not None else 'N/A'}")
    click.echo(f"Attempts:  {job.attempts}/{job.max_retries}")

    if job.stdout:
        click.echo(f"\n--- STDOUT ---")
        click.echo(job.stdout)

    if job.stderr:
        click.echo(f"\n--- STDERR ---")
        click.echo(job.stderr)

    if not job.stdout and not job.stderr:
        click.echo(f"\n(No output captured yet)")

    click.echo("=" * 60)


# ============================================================================
# CANCEL COMMAND
# ============================================================================

@cli.command()
@click.argument('job_id')
def cancel(job_id):
    """
    Cancel a pending or processing job

    Example: queuectl cancel job123
    """
    storage = get_storage()
    success = storage.cancel_job(job_id)

    if success:
        click.echo(f"✓ Job {job_id} cancelled successfully")
    else:
        click.echo(f"✗ Failed to cancel job {job_id} (not found or already completed)", err=True)
        sys.exit(1)


# ============================================================================
# DLQ COMMANDS
# ============================================================================

@cli.group()
def dlq():
    """Dead Letter Queue management"""
    pass


@dlq.command('list')
@click.option('--limit', default=20, help='Maximum number of jobs to display')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def dlq_list(limit, json_out):
    """
    List jobs in Dead Letter Queue

    Example: queuectl dlq list
    """
    queue = get_queue()
    dead_jobs = queue.list_dlq()

    if json_out:
        _output_json([j.to_dict() for j in dead_jobs[:limit]])
        return

    if not dead_jobs:
        click.echo("No jobs in Dead Letter Queue")
        return

    dead_jobs = dead_jobs[:limit]

    click.echo("=" * 110)
    click.echo(f"{'ID':<20} {'COMMAND':<30} {'ATTEMPTS':<10} {'EXIT CODE':<10} {'STDERR':<20} {'CREATED':<20}")
    click.echo("=" * 110)

    for job in dead_jobs:
        job_id = job.id[:18] + '..' if len(job.id) > 20 else job.id
        command = job.command[:28] + '..' if len(job.command) > 30 else job.command
        created = job.created_at[:19] if job.created_at else 'N/A'
        stderr_short = (job.stderr[:18] + '..') if job.stderr and len(job.stderr) > 20 else (job.stderr or 'N/A')
        exit_code = str(job.exit_code) if job.exit_code is not None else 'N/A'

        click.echo(f"{job_id:<20} {command:<30} {job.attempts:<10} {exit_code:<10} {stderr_short:<20} {created:<20}")

    click.echo("=" * 110)


@dlq.command()
@click.argument('job_id')
def retry(job_id):
    """
    Retry a job from Dead Letter Queue

    Example: queuectl dlq retry job1
    """
    queue = get_queue()
    success = queue.retry_job(job_id)

    if success:
        click.echo(f"✓ Job {job_id} moved from DLQ back to pending")
    else:
        click.echo(f"✗ Failed to retry job {job_id} (not found or not in DLQ)", err=True)
        sys.exit(1)


# ============================================================================
# CONFIG COMMANDS
# ============================================================================

@cli.group()
def config():
    """Configuration management"""
    pass


@config.command('set')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """
    Set configuration value

    Example: queuectl config set max-retries 5
    """
    cfg = get_config()
    db_key = key.replace('-', '_')

    if not cfg.is_valid_key(db_key):
        click.echo(f"✗ Unknown config key: {key}", err=True)
        click.echo(f"  Valid keys: {', '.join(sorted(cfg.VALID_KEYS))}", err=True)
        sys.exit(1)

    try:
        if value.lower() in ('true', 'false'):
            parsed_value = value.lower() == 'true'
        else:
            parsed_value = int(value)
    except ValueError:
        try:
            parsed_value = float(value)
        except ValueError:
            parsed_value = value

    cfg.set(db_key, parsed_value)
    click.echo(f"✓ Configuration updated: {key} = {parsed_value}")


@config.command('get')
@click.argument('key')
def config_get(key):
    """
    Get configuration value

    Example: queuectl config get max-retries
    """
    cfg = get_config()
    db_key = key.replace('-', '_')

    if not cfg.is_valid_key(db_key):
        click.echo(f"✗ Unknown config key: {key}", err=True)
        click.echo(f"  Valid keys: {', '.join(sorted(cfg.VALID_KEYS))}", err=True)
        sys.exit(1)

    value = cfg.get(db_key)
    click.echo(f"{key}: {value}")


@config.command('list')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def config_list(json_out):
    """
    List all configuration values

    Example: queuectl config list
    """
    cfg = get_config()
    all_config = cfg.get_all()

    if json_out:
        _output_json(all_config)
        return

    click.echo("=" * 40)
    click.echo("CONFIGURATION")
    click.echo("=" * 40)

    for key, value in sorted(all_config.items()):
        click.echo(f"  {key}: {value}")

    click.echo("=" * 40)


# ============================================================================
# MIGRATE COMMANDS
# ============================================================================

@cli.group()
def migrate():
    """Database migration commands"""
    pass


@migrate.command('run')
def migrate_run():
    """
    Run pending database migrations

    Example: queuectl migrate run
    """
    from .migrations import MigrationManager

    storage = get_storage()
    manager = MigrationManager(storage.db_path)

    current_version = manager.get_current_version()
    click.echo(f"Current schema version: {current_version}")

    pending = manager.get_pending_migrations()

    if not pending:
        click.echo("✓ No pending migrations")
        return

    click.echo(f"Found {len(pending)} pending migration(s)")

    for migration in pending:
        click.echo(f"  - Version {migration.version}: {migration.description}")

    result = manager.migrate()

    if result['success']:
        click.echo(f"✓ {result['message']}")
        click.echo(f"  New schema version: {result['current_version']}")
    else:
        click.echo(f"✗ Migration failed: {result['message']}", err=True)
        sys.exit(1)


@migrate.command('status')
def migrate_status():
    """
    Show migration status

    Example: queuectl migrate status
    """
    from .migrations import MigrationManager

    storage = get_storage()
    manager = MigrationManager(storage.db_path)

    current_version = manager.get_current_version()
    history = manager.get_migration_history()
    pending = manager.get_pending_migrations()

    click.echo("=" * 70)
    click.echo("MIGRATION STATUS")
    click.echo("=" * 70)
    click.echo(f"\nCurrent Version: {current_version}")
    click.echo(f"Pending Migrations: {len(pending)}")

    if history:
        click.echo("\nApplied Migrations:")
        for entry in history:
            click.echo(f"  v{entry['version']}: {entry['description']}")
            click.echo(f"           Applied: {entry['applied_at']}")

    if pending:
        click.echo("\nPending Migrations:")
        for migration in pending:
            click.echo(f"  v{migration.version}: {migration.description}")

    click.echo("=" * 70)


# ============================================================================
# METRICS COMMANDS
# ============================================================================

@cli.group()
def metrics():
    """Metrics and statistics commands"""
    pass


@metrics.command('show')
@click.option('--period', default=24, help='Period in hours')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def metrics_show(period, json_out):
    """
    Show job queue metrics

    Example: queuectl metrics show --period 24
    """
    from .metrics import MetricsTracker

    storage = get_storage()
    tracker = MetricsTracker(storage)

    stats = tracker.get_job_stats(period_hours=period)
    worker_util = tracker.get_worker_utilization(period_hours=period)

    if json_out:
        _output_json({**stats, **worker_util})
        return

    click.echo("=" * 60)
    click.echo(f"METRICS (Last {period} hours)")
    click.echo("=" * 60)

    click.echo("\nJob Statistics:")
    click.echo(f"  Jobs Processed:        {stats['jobs_processed']}")
    click.echo(f"  Success Rate:          {stats['success_rate']}%")
    click.echo(f"  Avg Execution Time:    {stats['avg_execution_time']:.2f}s")
    click.echo(f"  Avg Retries:           {stats['avg_retries']:.2f}")

    click.echo("\nWorker Utilization:")
    click.echo(f"  Avg Active Workers:    {worker_util['avg_active_workers']}")
    click.echo(f"  Max Active Workers:    {worker_util['max_active_workers']}")

    click.echo("=" * 60)


@metrics.command('export')
@click.option('--period', default=24, help='Period in hours')
@click.option('--format', 'fmt', type=click.Choice(['json', 'csv']), default='json', help='Export format')
@click.option('--output', type=click.Path(), help='Output file (default: stdout)')
def metrics_export(period, fmt, output):
    """
    Export metrics data

    Example: queuectl metrics export --period 24 --format json --output metrics.json
    """
    from .metrics import MetricsTracker

    storage = get_storage()
    tracker = MetricsTracker(storage)

    data = tracker.export_metrics(period_hours=period, format=fmt)

    if output:
        Path(output).write_text(data)
        click.echo(f"✓ Metrics exported to {output}")
    else:
        click.echo(data)


# ============================================================================
# WEBHOOK COMMANDS
# ============================================================================

@cli.group()
def webhook():
    """Webhook management commands"""
    pass


@webhook.command('add')
@click.option('--url', required=True, help='Webhook URL')
@click.option('--events', required=True, help='Comma-separated events (or * for all)')
@click.option('--secret', help='Optional webhook secret for authentication')
def webhook_add(url, events, secret):
    """
    Add a new webhook

    Events: job.started, job.completed, job.failed, job.timeout, job.cancelled, *

    Example: queuectl webhook add --url https://example.com/hook --events "job.completed,job.failed"
    """
    import uuid as _uuid
    from .webhooks import WebhookManager, WebhookEvent

    storage = get_storage()
    manager = WebhookManager(storage)

    event_list = [e.strip() for e in events.split(',')]

    valid_events = WebhookEvent.all_events() + ['*']
    for event in event_list:
        if event not in valid_events:
            click.echo(f"✗ Invalid event: {event}", err=True)
            click.echo(f"  Valid events: {', '.join(valid_events)}", err=True)
            sys.exit(1)

    webhook_id = f"webhook-{_uuid.uuid4().hex[:8]}"

    if manager.add_webhook(webhook_id, url, event_list, secret):
        click.echo(f"✓ Webhook added successfully")
        click.echo(f"  ID: {webhook_id}")
        click.echo(f"  URL: {url}")
        click.echo(f"  Events: {', '.join(event_list)}")
    else:
        click.echo(f"✗ Failed to add webhook", err=True)
        sys.exit(1)


@webhook.command('list')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def webhook_list(json_out):
    """
    List all webhooks

    Example: queuectl webhook list
    """
    from .webhooks import WebhookManager

    storage = get_storage()
    manager = WebhookManager(storage)
    webhooks = manager.list_webhooks()

    if json_out:
        _output_json(webhooks)
        return

    if not webhooks:
        click.echo("No webhooks configured")
        return

    click.echo("=" * 100)
    click.echo(f"{'ID':<25} {'URL':<40} {'EVENTS':<20} {'ENABLED':<10}")
    click.echo("=" * 100)

    for wh in webhooks:
        wh_id = wh['id'][:23] + '..' if len(wh['id']) > 25 else wh['id']
        url = wh['url'][:38] + '..' if len(wh['url']) > 40 else wh['url']
        events_str = ', '.join(wh['events'])
        events_str = events_str[:18] + '..' if len(events_str) > 20 else events_str
        enabled = '✓' if wh['enabled'] else '✗'

        click.echo(f"{wh_id:<25} {url:<40} {events_str:<20} {enabled:<10}")

    click.echo("=" * 100)


@webhook.command('remove')
@click.argument('webhook_id')
def webhook_remove(webhook_id):
    """
    Remove a webhook

    Example: queuectl webhook remove webhook-abc123
    """
    from .webhooks import WebhookManager

    storage = get_storage()
    manager = WebhookManager(storage)

    if manager.remove_webhook(webhook_id):
        click.echo(f"✓ Webhook {webhook_id} removed")
    else:
        click.echo(f"✗ Webhook {webhook_id} not found", err=True)
        sys.exit(1)


@webhook.command('toggle')
@click.argument('webhook_id')
@click.option('--enable/--disable', default=True, help='Enable or disable webhook')
def webhook_toggle(webhook_id, enable):
    """
    Enable or disable a webhook

    Example: queuectl webhook toggle webhook-abc123 --disable
    """
    from .webhooks import WebhookManager

    storage = get_storage()
    manager = WebhookManager(storage)

    if manager.toggle_webhook(webhook_id, enable):
        state = "enabled" if enable else "disabled"
        click.echo(f"✓ Webhook {webhook_id} {state}")
    else:
        click.echo(f"✗ Webhook {webhook_id} not found", err=True)
        sys.exit(1)


@webhook.command('test')
@click.option('--url', required=True, help='Webhook URL to test')
def webhook_test(url):
    """
    Test a webhook URL

    Example: queuectl webhook test --url https://example.com/webhook
    """
    import requests
    from datetime import datetime

    payload = {
        'event': 'test',
        'job': {
            'id': 'test-job-123',
            'command': 'echo test',
            'state': 'completed',
            'exit_code': 0
        },
        'timestamp': datetime.utcnow().isoformat()
    }

    try:
        click.echo(f"Sending test webhook to {url}...")
        response = requests.post(url, json=payload, timeout=10)

        click.echo(f"✓ Response received")
        click.echo(f"  Status Code: {response.status_code}")
        click.echo(f"  Response: {response.text[:200]}")

        if 200 <= response.status_code < 300:
            click.echo(f"✓ Webhook test successful")
        else:
            click.echo(f"⚠ Webhook returned non-2xx status code", err=True)

    except Exception as e:
        click.echo(f"✗ Request failed: {e}", err=True)
        sys.exit(1)


# ============================================================================
# SCHEDULE COMMAND (cron-like)
# ============================================================================

@cli.command()
@click.option('--command', '-c', required=True, help='Command to run')
@click.option('--cron', required=True, help='Cron expression (e.g., "*/5 * * * *")')
@click.option('--count', default=1, help='Number of future runs to schedule')
@click.option('--priority', '-p', type=click.Choice(['low', 'medium', 'high']),
              default='medium', help='Job priority')
@click.option('--timeout', '-t', type=int, help='Job timeout in seconds')
def schedule(command, cron, count, priority, timeout):
    """
    Schedule recurring jobs with cron expressions

    Example: queuectl schedule --command "python backup.py" --cron "0 2 * * *" --count 5
    """
    try:
        from croniter import croniter
        from datetime import datetime

        base = datetime.utcnow()
        cron_iter = croniter(cron, base)

        queue = get_queue()
        scheduled = 0

        for i in range(count):
            next_run = cron_iter.get_next(datetime)
            delay = (next_run - base).total_seconds()

            job_data = {
                'command': command,
                'priority': JobPriority.from_string(priority),
                'tags': f'scheduled,cron:{cron}',
            }
            if timeout:
                job_data['timeout'] = timeout

            job = queue.schedule_job(job_data, int(delay))
            if job:
                scheduled += 1
                click.echo(f"  ✓ Scheduled: {job.id} at {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        click.echo(f"\n✓ Scheduled {scheduled} job(s) with cron: {cron}")

    except ImportError:
        click.echo("✗ croniter package required. Install with: pip install croniter", err=True)
        sys.exit(1)
    except (ValueError, KeyError) as e:
        click.echo(f"✗ Invalid cron expression: {e}", err=True)
        sys.exit(1)


# ============================================================================
# DASHBOARD COMMAND
# ============================================================================

@cli.command()
@click.option('--host', default='0.0.0.0', help='Dashboard host')
@click.option('--port', default=5000, help='Dashboard port')
@click.option('--debug', is_flag=True, help='Enable debug mode')
def dashboard(host, port, debug):
    """
    Launch the web dashboard

    Example: queuectl dashboard --port 8080
    """
    try:
        from .web.app import run_dashboard
        click.echo(f"🌐 Starting dashboard at http://{host}:{port}")
        run_dashboard(host=host, port=port, debug=debug)
    except ImportError as e:
        click.echo(f"✗ Dashboard dependencies missing: {e}", err=True)
        click.echo("  Install with: pip install flask flask-cors flask-socketio", err=True)
        sys.exit(1)


# ============================================================================
# COMPLETIONS COMMAND (shell completions)
# ============================================================================

@cli.command()
@click.option('--shell', type=click.Choice(['bash', 'zsh', 'fish']), required=True,
              help='Shell type')
def completions(shell):
    """
    Generate shell completion script

    Example: queuectl completions --shell bash >> ~/.bashrc
    Example: queuectl completions --shell zsh >> ~/.zshrc
    """
    shell_map = {
        'bash': '_QUEUECTL_COMPLETE=bash_source',
        'zsh': '_QUEUECTL_COMPLETE=zsh_source',
        'fish': '_QUEUECTL_COMPLETE=fish_source',
    }

    env_var = shell_map[shell]
    click.echo(f"# queuectl {shell} completion")
    click.echo(f"# Add this to your shell config:")
    click.echo(f'eval "$({env_var} queuectl)"')


# ============================================================================
# AUDIT COMMAND (job history)
# ============================================================================

@cli.command()
@click.argument('job_id')
@click.option('--json-output', 'json_out', is_flag=True, help='Output as JSON')
def audit(job_id, json_out):
    """
    View audit trail for a job (state transitions)

    Example: queuectl audit job123
    """
    storage = get_storage()

    try:
        history = storage.get_audit_log(job_id)
    except Exception:
        click.echo(f"✗ Audit log not available. Run migrations first: queuectl migrate run", err=True)
        sys.exit(1)

    if json_out:
        _output_json(history)
        return

    if not history:
        click.echo(f"No audit trail found for job {job_id}")
        return

    click.echo("=" * 70)
    click.echo(f"AUDIT TRAIL: {job_id}")
    click.echo("=" * 70)

    for entry in history:
        click.echo(f"  [{entry['timestamp']}] {entry['old_state']} → {entry['new_state']}")
        if entry.get('details'):
            click.echo(f"    Details: {entry['details']}")

    click.echo("=" * 70)


if __name__ == '__main__':
    cli()