"""
Database migration system for queuectl
Handles schema upgrades and version tracking
"""
import sqlite3
import logging
from typing import List, Dict

logger = logging.getLogger('queuectl.migrations')


class Migration:
    """Represents a single database migration"""

    def __init__(self, version: int, description: str, sql: List[str]) -> None:
        self.version = version
        self.description = description
        self.sql = sql


# Migration definitions
MIGRATIONS = [
    Migration(
        version=2,
        description='Add priority and cancellation support',
        sql=[
            'ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 1',
            'ALTER TABLE jobs ADD COLUMN cancelled_at TIMESTAMP',
            'CREATE INDEX idx_jobs_priority ON jobs(priority DESC, created_at ASC)',
        ]
    ),
    Migration(
        version=3,
        description='Add job dependencies',
        sql=[
            '''CREATE TABLE IF NOT EXISTS job_dependencies (
                job_id TEXT NOT NULL,
                depends_on_job_id TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                FOREIGN KEY (depends_on_job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                PRIMARY KEY (job_id, depends_on_job_id)
            )''',
            'CREATE INDEX idx_deps_job ON job_dependencies(job_id)',
            'CREATE INDEX idx_deps_depends ON job_dependencies(depends_on_job_id)',
        ]
    ),
    Migration(
        version=4,
        description='Add metrics table',
        sql=[
            '''CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT
            )''',
            'CREATE INDEX idx_metrics_name_time ON metrics(metric_name, timestamp)',
        ]
    ),
    Migration(
        version=5,
        description='Add Phase 3 features: timeout, tags, pool',
        sql=[
            '''ALTER TABLE jobs ADD COLUMN timeout INTEGER DEFAULT NULL''',
            '''ALTER TABLE jobs ADD COLUMN tags TEXT DEFAULT NULL''',
            '''ALTER TABLE jobs ADD COLUMN pool TEXT DEFAULT NULL''',
        ]
    ),
    Migration(
        version=6,
        description='Add audit log and indexes',
        sql=[
            '''CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                old_state TEXT,
                new_state TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )''',
            'CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_log(job_id)',
            'CREATE INDEX IF NOT EXISTS idx_jobs_tags ON jobs(tags)',
            'CREATE INDEX IF NOT EXISTS idx_jobs_pool ON jobs(pool)',
        ]
    ),
]


class MigrationManager:
    """Manages database migrations"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_migration_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return sqlite3.connect(self.db_path)

    def _ensure_migration_table(self) -> None:
        """Create migration tracking table if it doesn't exist"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def get_current_version(self) -> int:
        """Get current schema version"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT MAX(version) FROM schema_migrations')
            result = cursor.fetchone()
            return result[0] if result[0] is not None else 1
        finally:
            conn.close()

    def get_pending_migrations(self) -> List[Migration]:
        """Get list of pending migrations"""
        current_version = self.get_current_version()
        return [m for m in MIGRATIONS if m.version > current_version]

    def apply_migration(self, migration: Migration) -> bool:
        """Apply a single migration"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            for sql in migration.sql:
                try:
                    cursor.execute(sql)
                except sqlite3.OperationalError as e:
                    # Skip "already exists" errors for idempotent migrations
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        logger.debug(f"Skipping (already applied): {sql[:60]}")
                        continue
                    raise

            cursor.execute(
                'INSERT INTO schema_migrations (version, description) VALUES (?, ?)',
                (migration.version, migration.description)
            )

            conn.commit()
            logger.info(f"Migration v{migration.version} applied: {migration.description}")
            return True
        except Exception as e:
            conn.rollback()
            raise Exception(f"Migration {migration.version} failed: {e}")
        finally:
            conn.close()

    def migrate(self) -> Dict[str, any]:
        """Run all pending migrations"""
        pending = self.get_pending_migrations()

        if not pending:
            return {
                'success': True,
                'message': 'No pending migrations',
                'current_version': self.get_current_version()
            }

        applied = []
        for migration in pending:
            try:
                self.apply_migration(migration)
                applied.append(migration.version)
            except Exception as e:
                return {
                    'success': False,
                    'message': str(e),
                    'applied': applied,
                    'failed_at': migration.version
                }

        return {
            'success': True,
            'message': f'Applied {len(applied)} migration(s)',
            'applied': applied,
            'current_version': self.get_current_version()
        }

    def get_migration_history(self) -> List[Dict]:
        """Get migration history"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT version, description, applied_at
                FROM schema_migrations
                ORDER BY version
            ''')

            return [
                {
                    'version': row[0],
                    'description': row[1],
                    'applied_at': row[2]
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()
