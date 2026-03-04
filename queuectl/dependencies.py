"""
Job dependency resolution system for queuectl
Handles DAG-based job execution with dependency tracking
"""
import logging
from typing import List, Dict, Optional
from .storage import Storage

logger = logging.getLogger('queuectl.dependencies')


class DependencyResolver:
    """Resolves job dependencies and detects circular dependencies"""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def add_dependency(self, job_id: str, depends_on_job_id: str) -> bool:
        """
        Add a dependency relationship

        Args:
            job_id: Job that depends on another
            depends_on_job_id: Job that must complete first

        Returns:
            True if dependency added, False if would create cycle
        """
        if self._would_create_cycle(job_id, depends_on_job_id):
            return False

        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO job_dependencies (job_id, depends_on_job_id)
                VALUES (?, ?)
            """, (job_id, depends_on_job_id))
            return True

    def get_dependencies(self, job_id: str) -> List[str]:
        """Get list of job IDs that this job depends on"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT depends_on_job_id FROM job_dependencies
                WHERE job_id = ?
            """, (job_id,))
            return [row[0] for row in cursor.fetchall()]

    def get_dependents(self, job_id: str) -> List[str]:
        """Get list of job IDs that depend on this job"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT job_id FROM job_dependencies
                WHERE depends_on_job_id = ?
            """, (job_id,))
            return [row[0] for row in cursor.fetchall()]

    def are_dependencies_met(self, job_id: str) -> bool:
        """
        Check if all dependencies for a job are completed

        Args:
            job_id: Job to check

        Returns:
            True if all dependencies are completed, False otherwise
        """
        dependencies = self.get_dependencies(job_id)

        if not dependencies:
            return True

        with self.storage._get_conn() as conn:
            cursor = conn.cursor()

            placeholders = ','.join(['?' for _ in dependencies])
            cursor.execute(f"""
                SELECT COUNT(*) FROM jobs
                WHERE id IN ({placeholders})
                AND state = 'completed'
            """, dependencies)

            completed_count = cursor.fetchone()[0]
            return completed_count == len(dependencies)

    def get_blocked_jobs(self) -> List[Dict]:
        """Get all jobs that are blocked by dependencies"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT j.id, j.command, j.state
                FROM jobs j
                INNER JOIN job_dependencies jd ON j.id = jd.job_id
                WHERE j.state = 'pending'
            """)

            blocked = []
            for row in cursor.fetchall():
                job_id = row[0]
                if not self.are_dependencies_met(job_id):
                    blocked.append({
                        'id': job_id,
                        'command': row[1],
                        'state': row[2],
                        'dependencies': self.get_dependencies(job_id)
                    })

            return blocked

    def _would_create_cycle(self, job_id: str, depends_on_job_id: str) -> bool:
        """
        Check if adding dependency (job_id -> depends_on_job_id) would create a cycle.

        Uses BFS reachability: if job_id is reachable from depends_on_job_id
        via existing edges, adding this edge would close the loop.
        """
        if job_id == depends_on_job_id:
            return True

        with self.storage._get_conn() as conn:
            cursor = conn.cursor()

            # BFS: can we reach job_id starting from depends_on_job_id?
            visited = set()
            queue = [depends_on_job_id]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                cursor.execute(
                    "SELECT depends_on_job_id FROM job_dependencies WHERE job_id = ?",
                    (current,)
                )
                for row in cursor.fetchall():
                    dep = row[0]
                    if dep == job_id:
                        return True  # Found path back to job_id — cycle!
                    if dep not in visited:
                        queue.append(dep)

            return False

    def get_dependency_tree(self, job_id: str) -> Optional[Dict]:
        """
        Get the full dependency tree for a job

        Returns:
            Dictionary representing the dependency tree
        """
        job_dict = self.storage.get_job(job_id)
        if not job_dict:
            return None

        dependencies = self.get_dependencies(job_id)

        tree = {
            'id': job_id,
            'command': job_dict['command'],
            'state': job_dict['state'],
            'dependencies': []
        }

        for dep_id in dependencies:
            dep_tree = self.get_dependency_tree(dep_id)
            if dep_tree:
                tree['dependencies'].append(dep_tree)

        return tree

    def get_ready_jobs(self) -> List[str]:
        """
        Get list of pending jobs whose dependencies are all met

        Returns:
            List of job IDs ready to execute
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id FROM jobs
                WHERE state = 'pending'
                AND cancelled_at IS NULL
            """)

            pending_jobs = [row[0] for row in cursor.fetchall()]

            ready = []
            for job_id in pending_jobs:
                if self.are_dependencies_met(job_id):
                    ready.append(job_id)

            return ready

    def remove_dependencies(self, job_id: str) -> None:
        """Remove all dependencies for a job"""
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM job_dependencies
                WHERE job_id = ?
            """, (job_id,))

    def propagate_priority(self, job_id: str, priority: int) -> None:
        """
        Propagate priority to all dependencies

        When a high-priority job is enqueued, its dependencies should inherit
        the higher priority to ensure they complete first.
        Uses a single DB connection to avoid nested context managers.

        Args:
            job_id: Job whose dependencies should inherit priority
            priority: Priority to propagate
        """
        with self.storage._get_conn() as conn:
            cursor = conn.cursor()
            self._propagate_priority_recursive(cursor, job_id, priority)

    def _propagate_priority_recursive(self, cursor, job_id: str, priority: int) -> None:
        """Internal recursive priority propagation using shared cursor"""
        cursor.execute(
            "SELECT depends_on_job_id FROM job_dependencies WHERE job_id = ?",
            (job_id,)
        )
        dependencies = [row[0] for row in cursor.fetchall()]

        if not dependencies:
            return

        for dep_id in dependencies:
            cursor.execute("SELECT priority FROM jobs WHERE id = ?", (dep_id,))
            row = cursor.fetchone()

            if row:
                current_priority = row[0]

                if priority > current_priority:
                    cursor.execute(
                        "UPDATE jobs SET priority = ? WHERE id = ?",
                        (priority, dep_id)
                    )
                    self._propagate_priority_recursive(cursor, dep_id, priority)
