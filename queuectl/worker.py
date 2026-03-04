"""
Worker process management for queuectl
Handles job execution, retry logic, worker coordination,
dependency checking, webhook dispatch, and worker pools
"""
import subprocess
import time
import signal
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional
from multiprocessing import Process, Manager
import uuid

from .storage import Storage
from .config import Config
from .models import Job, JobState

logger = logging.getLogger('queuectl.worker')

MAX_OUTPUT_LEN = 2000
DEFAULT_TIMEOUT = 300


def _worker_process(worker_id: str, db_path: str, shutdown_event, pool: Optional[str] = None) -> None:
    """
    Worker process function (must be at module level for multiprocessing)
    
    Args:
        worker_id: Unique worker identifier
        db_path: Path to database
        shutdown_event: Shutdown event (shared between processes)
        pool: Optional worker pool name
    """
    storage = Storage(db_path)
    config = Config(storage)
    
    worker = Worker(worker_id, storage, config, shutdown_event, pool=pool)
    worker.run()


class Worker:
    """Worker process that executes jobs from the queue"""
    
    def __init__(self, worker_id: str, storage: Storage, config: Config,
                 shutdown_event, pool: Optional[str] = None) -> None:
        """
        Initialize worker
        
        Args:
            worker_id: Unique worker identifier
            storage: Storage instance
            config: Config instance
            shutdown_event: Multiprocessing event for graceful shutdown
            pool: Optional worker pool name (only process matching jobs)
        """
        self.worker_id = worker_id
        self.storage = storage
        self.config = config
        self.shutdown_event = shutdown_event
        self.pool = pool
        self.poll_interval = config.get('worker_poll_interval', 1)
        
        # Initialize webhook dispatcher
        self.webhook_dispatcher = None
        try:
            from .webhooks import WebhookManager, WebhookDispatcher
            manager = WebhookManager(storage)
            self.webhook_dispatcher = WebhookDispatcher(manager)
            logger.debug(f"[Worker {worker_id}] Webhook dispatcher initialized")
        except Exception as e:
            logger.debug(f"[Worker {worker_id}] Webhooks not available: {e}")
        
        # Initialize dependency resolver
        self.dep_resolver = None
        try:
            from .dependencies import DependencyResolver
            self.dep_resolver = DependencyResolver(storage)
            logger.debug(f"[Worker {worker_id}] Dependency resolver initialized")
        except Exception as e:
            logger.debug(f"[Worker {worker_id}] Dependencies not available: {e}")
        
        # Initialize metrics tracker
        self.metrics_tracker = None
        try:
            from .metrics import MetricsTracker
            self.metrics_tracker = MetricsTracker(storage)
        except Exception:
            pass
    
    def run(self) -> None:
        """Main worker loop - poll for jobs and execute them"""
        pool_info = f" (pool: {self.pool})" if self.pool else ""
        print(f"[Worker {self.worker_id}] Started{pool_info}")
        logger.info(f"Worker {self.worker_id} started{pool_info}")
        
        while not self.shutdown_event.is_set():
            try:
                from pathlib import Path
                stop_file = Path.home() / ".queuectl" / "stop"
                if stop_file.exists():
                    print(f"[Worker {self.worker_id}] Stop file detected, shutting down")
                    logger.info(f"Worker {self.worker_id} stop file detected")
                    self.shutdown_event.set()
                    try:
                        stop_file.unlink()
                    except FileNotFoundError:
                        pass
                    break
   
                job_data = self.storage.claim_job(self.worker_id, pool=self.pool)
                
                if job_data:
                    job = Job.from_dict(job_data)
                    
                    # Check dependencies before executing
                    if self.dep_resolver and not self._check_dependencies(job):
                        # Put job back to pending — dependencies not met
                        self.storage.update_job(job.id, {
                            'state': JobState.PENDING,
                            'worker_id': None,
                            'locked_at': None,
                            'attempts': max(0, job.attempts - 1),
                        })
                        logger.debug(f"Job {job.id} returned to pending — dependencies not met")
                        time.sleep(self.poll_interval)
                        continue
                    
                    # Validate command
                    if self.config.get('command_validation', True):
                        is_safe, warning = Storage.validate_command(job.command)
                        if not is_safe:
                            logger.warning(f"Job {job.id} blocked: {warning}")
                            print(f"[Worker {self.worker_id}] ⚠ Job {job.id} blocked: {warning}")
                            self.handle_failure(job, "", warning, -1)
                            continue
                    
                    print(f"[Worker {self.worker_id}] Claimed job {job.id}")
                    logger.info(f"Worker {self.worker_id} claimed job {job.id}")
                    self.execute_job(job)
                else:
                    time.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                print(f"[Worker {self.worker_id}] Error in main loop: {e}")
                time.sleep(self.poll_interval)
        
        print(f"[Worker {self.worker_id}] Shutdown signal received, exiting")
        logger.info(f"Worker {self.worker_id} shut down")
    
    def _check_dependencies(self, job: Job) -> bool:
        """Check if all dependencies for a job are met"""
        if not self.dep_resolver:
            return True
        try:
            return self.dep_resolver.are_dependencies_met(job.id)
        except Exception:
            return True  # Don't block if dependency check fails
    
    def execute_job(self, job: Job) -> None:
        """Execute a job command"""
        timeout = job.timeout if job.timeout is not None else self.config.get('job_timeout', DEFAULT_TIMEOUT)
        start_time = time.time()
        
        # Dispatch job started webhook
        self._dispatch_webhook('JOB_STARTED', job)
        
        try:
            print(f"[Worker {self.worker_id}] Executing: {job.command} (timeout: {timeout}s)")
            logger.info(f"Executing job {job.id}: {job.command[:100]}")
            
            result = subprocess.run(
                job.command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                text=True
            )

            stdout = result.stdout[:MAX_OUTPUT_LEN] if result.stdout else ""
            stderr = result.stderr[:MAX_OUTPUT_LEN] if result.stderr else ""

            # Record execution time metric
            elapsed = time.time() - start_time
            if self.metrics_tracker:
                try:
                    self.metrics_tracker.record_metric('job_execution_time', elapsed, 
                                                       {'job_id': job.id, 'success': result.returncode == 0})
                except Exception:
                    pass

            if result.returncode == 0:
                self.mark_completed(job, stdout, stderr, result.returncode)
            else:
                self.handle_failure(job, stdout, stderr, result.returncode, is_timeout=False)
        
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            logger.warning(f"Job {job.id} timed out after {elapsed:.1f}s")
            print(f"[Worker {self.worker_id}] Job {job.id} timed out after {timeout}s")
            self.handle_failure(
                job, "", f"Job exceeded timeout of {timeout} seconds",
                -1, is_timeout=True
            )
        
        except Exception as e:
            logger.error(f"Job {job.id} execution error: {e}")
            print(f"[Worker {self.worker_id}] Job {job.id} execution error: {e}")
            self.handle_failure(
                job, "", f"Execution error: {str(e)}", -1, is_timeout=False
            )
    
    def mark_completed(self, job: Job, stdout: str, stderr: str, exit_code: int) -> None:
        """Mark job as completed successfully"""
        print(f"[Worker {self.worker_id}] Job {job.id} completed successfully")
        logger.info(f"Job {job.id} completed (exit code: {exit_code})")
        
        updates = {
            'state': JobState.COMPLETED,
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': exit_code,
        }
        
        self.storage.update_job(job.id, updates)
        
        # Record snapshot
        if self.metrics_tracker:
            try:
                self.metrics_tracker.record_queue_snapshot()
            except Exception:
                pass
        
        # Dispatch webhook
        self._dispatch_webhook('JOB_COMPLETED', job, updates)
    
    def handle_failure(self, job: Job, stdout: str, stderr: str,
                       exit_code: int, is_timeout: bool = False) -> None:
        """Handle job failure with retry logic"""
        print(f"[Worker {self.worker_id}] Job {job.id} failed (attempt {job.attempts}/{job.max_retries})")
        logger.warning(f"Job {job.id} failed (attempt {job.attempts}/{job.max_retries})")
        
        updates = {
            'stdout': stdout,
            'stderr': stderr,
            'exit_code': exit_code,
        }

        if job.attempts >= job.max_retries:
            print(f"[Worker {self.worker_id}] Job {job.id} moved to DLQ after {job.attempts} attempts")
            logger.info(f"Job {job.id} moved to DLQ")
            updates['state'] = JobState.DEAD
        else:
            backoff_base = self.config.get('backoff_base', 2)
            delay = backoff_base ** job.attempts
            run_at = datetime.utcnow() + timedelta(seconds=delay)
            
            print(f"[Worker {self.worker_id}] Job {job.id} will retry in {delay}s")
            logger.info(f"Job {job.id} retry in {delay}s")
            
            updates['state'] = JobState.PENDING
            updates['run_at'] = run_at.isoformat()
            updates['worker_id'] = None
            updates['locked_at'] = None
        
        self.storage.update_job(job.id, updates)
        
        # Record snapshot
        if self.metrics_tracker:
            try:
                self.metrics_tracker.record_queue_snapshot()
            except Exception:
                pass
        
        # Dispatch webhook
        event = 'JOB_TIMEOUT' if is_timeout else 'JOB_FAILED'
        self._dispatch_webhook(event, job, updates)
    
    def _dispatch_webhook(self, event_name: str, job: Job,
                          extra_data: Optional[dict] = None) -> None:
        """Dispatch webhook for a job event"""
        if not self.webhook_dispatcher:
            return
        try:
            from .webhooks import WebhookEvent
            event_map = {
                'JOB_STARTED': WebhookEvent.JOB_STARTED,
                'JOB_COMPLETED': WebhookEvent.JOB_COMPLETED,
                'JOB_FAILED': WebhookEvent.JOB_FAILED,
                'JOB_TIMEOUT': WebhookEvent.JOB_TIMEOUT,
                'JOB_CANCELLED': WebhookEvent.JOB_CANCELLED,
            }
            event = event_map.get(event_name)
            if event:
                job_dict = job.to_dict()
                if extra_data:
                    job_dict.update(extra_data)
                self.webhook_dispatcher.dispatch(event, job_dict)
        except Exception as e:
            logger.debug(f"Webhook dispatch failed for {event_name}: {e}")


class WorkerManager:
    """Manages multiple worker processes"""
    
    def __init__(self, storage: Storage, config: Config,
                 pool: Optional[str] = None) -> None:
        """
        Initialize worker manager
        
        Args:
            storage: Storage instance
            config: Config instance
            pool: Optional worker pool name
        """
        self.storage = storage
        self.config = config
        self.pool = pool
        self.workers = []
        self.manager = Manager()
        self.shutdown_event = self.manager.Event()
    
    def start_workers(self, count: int) -> None:
        """Start multiple worker processes"""
        pool_info = f" (pool: {self.pool})" if self.pool else ""
        print(f"Starting {count} worker(s){pool_info}...")
        logger.info(f"Starting {count} workers{pool_info}")
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        for i in range(count):
            worker_id = f"worker-{uuid.uuid4().hex[:8]}"

            process = Process(
                target=_worker_process,
                args=(worker_id, self.storage.db_path, self.shutdown_event, self.pool),
                name=worker_id
            )
            process.start()
            
            self.workers.append({
                'id': worker_id,
                'process': process
            })
        
        print(f"All workers started. Press Ctrl+C to stop.")

        try:
            for worker_info in self.workers:
                worker_info['process'].join()
        except KeyboardInterrupt:
            pass
        
        print("All workers stopped")
        logger.info("All workers stopped")
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals"""
        print("\nShutdown signal received, stopping workers gracefully...")
        logger.info("Shutdown signal received")
        self.shutdown_event.set()
    
    def stop_workers(self) -> None:
        """Stop all running workers gracefully"""
        print("Requesting worker shutdown...")
        self.shutdown_event.set()

        for worker_info in self.workers:
            if worker_info['process'].is_alive():
                worker_info['process'].join(timeout=30)

                if worker_info['process'].is_alive():
                    print(f"Force terminating {worker_info['id']}")
                    logger.warning(f"Force terminating {worker_info['id']}")
                    worker_info['process'].terminate()
        
        self.workers.clear()
        print("All workers stopped")