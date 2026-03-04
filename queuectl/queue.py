"""
Queue management for queuectl
Handles job enqueuing, listing, and status operations
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from .storage import Storage
from .models import Job, JobState
from .config import Config


class Queue:
    """Job queue manager"""

    def __init__(self, storage: Storage, config: Config):
        """Initialize queue with storage and config"""
        self.storage = storage
        self.config = config

    def enqueue(self, job_data: Dict[str, Any]) -> Optional[Job]:
        """
        Add a new job to the queue

        Args:
            job_data: Dictionary containing job information

        Returns:
            Job object if successful, None otherwise
        """

        if 'command' not in job_data:
            raise ValueError("Job must have a 'command' field")

        if 'id' not in job_data:
            job_data['id'] = Job.generate_id()

        if 'max_retries' not in job_data:
            job_data['max_retries'] = self.config.get('max_retries', 3)

        now = datetime.utcnow().isoformat()
        if 'created_at' not in job_data:
            job_data['created_at'] = now
        if 'updated_at' not in job_data:
            job_data['updated_at'] = now

        success = self.storage.create_job(job_data)

        if success:
            job = Job.from_dict(job_data)

            # Propagate priority to dependencies if enabled
            if self.config.get('priority_inheritance', True):
                try:
                    from .dependencies import DependencyResolver
                    resolver = DependencyResolver(self.storage)

                    # If job has dependencies, propagate priority
                    if resolver.get_dependencies(job.id):
                        resolver.propagate_priority(job.id, job.priority)
                except Exception:
                    pass  # Don't fail enqueue if priority propagation fails

            return job

        return None

    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get a job by ID

        Args:
            job_id: Job identifier

        Returns:
            Job object if found, None otherwise
        """
        job_data = self.storage.get_job(job_id)
        if job_data:
            return Job.from_dict(job_data)
        return None

    def list_jobs(self, state: Optional[str] = None) -> List[Job]:
        """
        List jobs, optionally filtered by state

        Args:
            state: Optional state filter

        Returns:
            List of Job objects
        """
        job_data_list = self.storage.list_jobs(state)
        return [Job.from_dict(data) for data in job_data_list]

    def get_status(self) -> Dict[str, Any]:
        """
        Get queue status with job counts and worker info

        Returns:
            Dictionary with status information
        """
        stats = self.storage.get_job_stats()

        active_workers = self._count_active_workers()

        return {
            'jobs': stats,
            'total_jobs': sum(stats.values()),
            'active_workers': active_workers,
            'timestamp': datetime.utcnow().isoformat()
        }

    def _count_active_workers(self) -> int:
        """Count number of active workers"""
        processing_jobs = self.storage.list_jobs('processing')
        worker_ids = set(job['worker_id'] for job in processing_jobs if job.get('worker_id'))
        return len(worker_ids)

    def retry_job(self, job_id: str) -> bool:
        """
        Retry a job from DLQ (move from dead to pending)

        Args:
            job_id: Job identifier

        Returns:
            True if successful
        """
        job = self.get_job(job_id)

        if not job:
            return False

        if job.state != JobState.DEAD:
            return False

        updates = {
            'state': JobState.PENDING,
            'attempts': 0,
            'run_at': None,
            'worker_id': None,
            'locked_at': None,
            'stdout': None,
            'stderr': None,
            'exit_code': None,
        }

        return self.storage.update_job(job_id, updates)

    def list_dlq(self) -> List[Job]:
        """
        List all jobs in Dead Letter Queue

        Returns:
            List of dead jobs
        """
        return self.list_jobs(JobState.DEAD)

    def schedule_job(self, job_data: Dict[str, Any], delay_seconds: int) -> Optional[Job]:
        """
        Schedule a job to run after a delay

        Args:
            job_data: Job information
            delay_seconds: Delay in seconds before job should run

        Returns:
            Job object if successful
        """
        run_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
        job_data['run_at'] = run_at.isoformat()

        return self.enqueue(job_data)
