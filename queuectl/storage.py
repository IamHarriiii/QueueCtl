"""
Database storage layer for queuectl
Handles SQLite operations for jobs, configuration, and audit logging
Features: context manager, connection pooling, command validation, audit log
"""
import sqlite3
import re
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger('queuectl.storage')

# Dangerous patterns for command validation
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',      # rm -rf /
    r'mkfs\.',             # disk formatting
    r'dd\s+if=',           # disk overwrite
    r'>\s*/dev/sd',        # write to device
    r':\(\)\{\s*:\|:&\s*\};:',  # fork bomb
]


class Storage:
    """SQLite storage manager for jobs, configuration, and audit logging"""

    def __init__(self, db_path: str = None) -> None:
        """Initialize storage with database path"""
        if db_path is None:
            base_dir = Path.home() / ".queuectl"
            base_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(base_dir / "queuectl.db")

        self.db_path = db_path
        self.conn = None
        self._lock = threading.Lock()
        self._initialize_db()

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection (legacy compatibility)"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def _initialize_db(self) -> None:
        """Create tables if they don't exist"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    priority INTEGER DEFAULT 1,
                    timeout INTEGER,
                    tags TEXT,
                    pool TEXT,
                    worker_id TEXT,
                    locked_at TIMESTAMP,
                    run_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    dependencies TEXT,
                    stdout TEXT,
                    stderr TEXT,
                    exit_code INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_run_at ON jobs(run_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_locked_at ON jobs(locked_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC, created_at ASC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_tags ON jobs(tags)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_pool ON jobs(pool)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Audit log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    old_state TEXT,
                    new_state TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_log(job_id)")

            default_config = [
                ('max_retries', '3'),
                ('backoff_base', '2'),
                ('job_timeout', '300'),
                ('worker_poll_interval', '1'),
                ('priority_inheritance', 'true'),
                ('command_validation', 'true'),
            ]

            for key, value in default_config:
                cursor.execute(
                    "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                    (key, value)
                )

    @staticmethod
    def validate_command(command: str) -> tuple:
        """
        Validate a command for dangerous patterns

        Args:
            command: Shell command to validate

        Returns:
            Tuple of (is_safe, warning_message)
        """
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Potentially dangerous command pattern detected: {pattern}"
        return True, ""

    def _record_audit(self, cursor, job_id: str, old_state: Optional[str],
                      new_state: str, details: Optional[str] = None) -> None:
        """Record a state transition in the audit log"""
        try:
            cursor.execute(
                """INSERT INTO audit_log (job_id, old_state, new_state, details)
                   VALUES (?, ?, ?, ?)""",
                (job_id, old_state, new_state, details)
            )
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    def get_audit_log(self, job_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for a job"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT old_state, new_state, details, timestamp
                   FROM audit_log WHERE job_id = ? ORDER BY timestamp""",
                (job_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def create_job(self, job_data: Dict[str, Any]) -> bool:
        """Insert a new job into the database"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO jobs (
                        id, command, state, attempts, max_retries, priority,
                        timeout, tags, pool, run_at, dependencies, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_data['id'],
                    job_data['command'],
                    job_data.get('state', 'pending'),
                    job_data.get('attempts', 0),
                    job_data.get('max_retries', 3),
                    job_data.get('priority', 1),
                    job_data.get('timeout'),
                    job_data.get('tags'),
                    job_data.get('pool'),
                    job_data.get('run_at'),
                    job_data.get('dependencies'),
                    job_data.get('created_at', datetime.utcnow().isoformat()),
                    job_data.get('updated_at', datetime.utcnow().isoformat())
                ))

                self._record_audit(cursor, job_data['id'], None, 'pending', 'Job created')
                logger.info(f"Job {job_data['id']} created")
                return True
            except sqlite3.IntegrityError:
                logger.warning(f"Job {job_data.get('id')} already exists")
                return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a job by ID"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def claim_job(self, worker_id: str, pool: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Atomically claim a pending job for processing.
        Includes safety timeout for crashed workers.
        Supports dependency checking and worker pool filtering.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Build pool filter
            pool_filter = "AND pool = ?" if pool else "AND (pool IS NULL OR pool = '')"
            params = [worker_id]

            query = f"""
                UPDATE jobs
                SET state = 'processing',
                    worker_id = ?,
                    locked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    attempts = attempts + 1
                WHERE id IN (
                    SELECT id FROM jobs
                    WHERE (
                        state = 'pending'
                        OR (state = 'processing' AND locked_at < datetime('now', '-5 minutes'))
                    )
                    AND (run_at IS NULL OR datetime(run_at) <= datetime('now'))
                    AND cancelled_at IS NULL
                    {pool_filter}
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                )
            """

            if pool:
                params.append(pool)

            cursor.execute(query, params)

            if cursor.rowcount > 0:
                cursor.execute("""
                    SELECT * FROM jobs
                    WHERE worker_id = ? AND state = 'processing'
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (worker_id,))

                row = cursor.fetchone()
                if row:
                    job_dict = dict(row)
                    self._record_audit(
                        cursor, job_dict['id'], 'pending', 'processing',
                        f'Claimed by worker {worker_id}'
                    )
                    logger.info(f"Job {job_dict['id']} claimed by {worker_id}")
                    return job_dict

            return None

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job fields with audit logging"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Get old state for audit
            old_state = None
            if 'state' in updates:
                cursor.execute("SELECT state FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                if row:
                    old_state = row['state']

            updates['updated_at'] = datetime.utcnow().isoformat()

            fields = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [job_id]

            cursor.execute(f"UPDATE jobs SET {fields} WHERE id = ?", values)

            # Record audit
            if 'state' in updates and old_state:
                self._record_audit(cursor, job_id, old_state, updates['state'])

            success = cursor.rowcount > 0
            if success:
                logger.debug(f"Job {job_id} updated: {list(updates.keys())}")
            return success

    def list_jobs(self, state: Optional[str] = None, tags: Optional[str] = None,
                  pool: Optional[str] = None) -> List[Dict[str, Any]]:
        """List jobs with optional filtering by state, tags, or pool"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if state:
                conditions.append("state = ?")
                params.append(state)
            if tags:
                conditions.append("tags LIKE ?")
                params.append(f"%{tags}%")
            if pool:
                conditions.append("pool = ?")
                params.append(pool)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            cursor.execute(f"SELECT * FROM jobs {where} ORDER BY priority DESC, created_at DESC", params)
            return [dict(row) for row in cursor.fetchall()]

    def get_job_stats(self) -> Dict[str, int]:
        """Get count of jobs by state"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT state, COUNT(*) as count
                FROM jobs
                GROUP BY state
            """)

            stats = {row['state']: row['count'] for row in cursor.fetchall()}

            for state in ['pending', 'processing', 'completed', 'failed', 'dead', 'cancelled']:
                if state not in stats:
                    stats[state] = 0

            return stats

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()

            if row:
                value = row['value']
                # Handle booleans
                if value.lower() in ('true', 'false'):
                    return value.lower() == 'true'
                try:
                    return int(value)
                except ValueError:
                    try:
                        return float(value)
                    except ValueError:
                        return value

            return default

    def set_config(self, key: str, value: Any) -> bool:
        """Set configuration value"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO config (key, value)
                VALUES (?, ?)
            """, (key, str(value)))

            logger.info(f"Config set: {key} = {value}")
            return True

    def list_config(self) -> Dict[str, Any]:
        """List all configuration values"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT key, value FROM config")

            config = {}
            for row in cursor.fetchall():
                value = row['value']
                if value.lower() in ('true', 'false'):
                    config[row['key']] = value.lower() == 'true'
                else:
                    try:
                        config[row['key']] = int(value)
                    except ValueError:
                        try:
                            config[row['key']] = float(value)
                        except ValueError:
                            config[row['key']] = value

            return config

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or processing job"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # Get old state
            cursor.execute("SELECT state FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            old_state = row['state'] if row else None

            cursor.execute("""
                UPDATE jobs
                SET state = 'cancelled',
                    cancelled_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND state IN ('pending', 'processing')
            """, (job_id,))

            if cursor.rowcount > 0:
                self._record_audit(cursor, job_id, old_state, 'cancelled', 'Cancelled by user')
                logger.info(f"Job {job_id} cancelled")
                return True
            return False

    def get_active_workers(self) -> int:
        """Get count of currently active workers"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(DISTINCT worker_id) as count
                FROM jobs
                WHERE state = 'processing'
                AND locked_at > datetime('now', '-1 minute')
            """)

            row = cursor.fetchone()
            return row['count'] if row else 0
