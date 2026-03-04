"""
queuectl - A production-grade CLI-based background job queue system

Features:
- Job queue with multiple worker processes and worker pools
- Retry mechanism with exponential backoff
- Dead Letter Queue for permanently failed jobs
- Persistent storage with SQLite (WAL mode)
- Job dependencies with DAG resolution
- Priority queues with inheritance
- Webhook notifications
- Metrics tracking and export
- Cron-like job scheduling
- Web dashboard with real-time monitoring
- Audit logging for all state transitions
- Command validation and security
- Configurable settings
"""

__version__ = "2.0.0"
__author__ = "HARINARAYANAN U"

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from .storage import Storage  # noqa: E402
from .config import Config  # noqa: E402
from .queue import Queue  # noqa: E402
from .worker import Worker, WorkerManager  # noqa: E402
from .models import Job, JobState, JobPriority  # noqa: E402

__all__ = [
    'Storage',
    'Config',
    'Queue',
    'Worker',
    'WorkerManager',
    'Job',
    'JobState',
    'JobPriority',
]
