"""
Data models for queuectl
Defines Job structure, state constants, and priority levels
"""
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime
import uuid


@dataclass
class Job:
    """Job model representing a background task"""

    id: str
    command: str
    state: str = 'pending'
    attempts: int = 0
    max_retries: int = 3
    priority: int = 1  # 0=low, 1=medium, 2=high
    timeout: Optional[int] = None  # Job-specific timeout in seconds
    tags: Optional[str] = None  # Comma-separated tags
    pool: Optional[str] = None  # Worker pool assignment
    worker_id: Optional[str] = None
    locked_at: Optional[str] = None
    run_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    dependencies: Optional[str] = None  # JSON list of job IDs
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        """Set timestamps if not provided"""
        now = datetime.utcnow().isoformat()
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

    def __repr__(self) -> str:
        """Human-readable representation"""
        return (f"Job(id='{self.id}', command='{self.command[:50]}', "
                f"state='{self.state}', priority={self.get_priority_name()}, "
                f"attempts={self.attempts}/{self.max_retries})")

    def to_dict(self) -> dict:
        """Convert job to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Job':
        """Create Job from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

    @staticmethod
    def generate_id() -> str:
        """Generate unique job ID"""
        return str(uuid.uuid4())

    def is_retryable(self) -> bool:
        """Check if job can be retried"""
        return self.attempts < self.max_retries

    def should_be_in_dlq(self) -> bool:
        """Check if job should be moved to dead letter queue"""
        return self.attempts >= self.max_retries and self.state == 'failed'

    def is_cancelled(self) -> bool:
        """Check if job is cancelled"""
        return self.cancelled_at is not None

    def get_priority_name(self) -> str:
        """Get human-readable priority name"""
        priority_names = {0: 'low', 1: 'medium', 2: 'high'}
        return priority_names.get(self.priority, 'medium')

    def get_tags_list(self) -> list:
        """Get tags as a list"""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',')]

    def has_tag(self, tag: str) -> bool:
        """Check if job has a specific tag"""
        return tag in self.get_tags_list()


# Job state constants
class JobState:
    """Job state constants"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    DEAD = 'dead'
    CANCELLED = 'cancelled'

    @classmethod
    def all_states(cls) -> list:
        """Get all valid job states"""
        return [cls.PENDING, cls.PROCESSING, cls.COMPLETED, cls.FAILED, cls.DEAD, cls.CANCELLED]

    @classmethod
    def is_valid(cls, state: str) -> bool:
        """Check if state is valid"""
        return state in cls.all_states()

    @classmethod
    def terminal_states(cls) -> list:
        """Get states that are final (no more transitions)"""
        return [cls.COMPLETED, cls.DEAD, cls.CANCELLED]

    @classmethod
    def active_states(cls) -> list:
        """Get states where jobs are still in-flight"""
        return [cls.PENDING, cls.PROCESSING, cls.FAILED]


# Priority constants
class JobPriority:
    """Job priority constants"""
    LOW = 0
    MEDIUM = 1
    HIGH = 2

    @classmethod
    def from_string(cls, priority_str: str) -> int:
        """Convert priority string to integer"""
        priority_map = {
            'low': cls.LOW,
            'medium': cls.MEDIUM,
            'high': cls.HIGH
        }
        return priority_map.get(priority_str.lower(), cls.MEDIUM)

    @classmethod
    def to_string(cls, priority_int: int) -> str:
        """Convert priority integer to string"""
        priority_map = {
            cls.LOW: 'low',
            cls.MEDIUM: 'medium',
            cls.HIGH: 'high'
        }
        return priority_map.get(priority_int, 'medium')

    @classmethod
    def all_priorities(cls) -> list:
        """Get all priority levels"""
        return [cls.LOW, cls.MEDIUM, cls.HIGH]
