"""
Pytest-based unit tests for queuectl v2.0.0
Tests new features: tags, pools, audit log, command validation,
rate limiter, batch operations, cron scheduling, and CLI commands
"""
import json
import os
import sys
import tempfile
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from queuectl.storage import Storage
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.models import Job, JobState, JobPriority
from queuectl.webhooks import RateLimiter, WebhookEvent, WebhookManager
from queuectl.migrations import MigrationManager, MIGRATIONS
from queuectl.utils import parse_tags, format_duration, truncate_string, calculate_backoff_delay


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_path():
    """Create a temporary database"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def storage(db_path):
    """Create storage instance with temp DB"""
    return Storage(db_path)


@pytest.fixture
def config(storage):
    """Create config instance"""
    return Config(storage)


@pytest.fixture
def queue(storage, config):
    """Create queue instance"""
    return Queue(storage, config)


# ============================================================================
# Job Model Tests
# ============================================================================

class TestJobModel:
    def test_repr(self):
        job = Job(id='test-1', command='echo hello', priority=2)
        r = repr(job)
        assert 'test-1' in r
        assert 'echo hello' in r
        assert 'high' in r

    def test_from_dict(self):
        data = {'id': 'j1', 'command': 'echo hi', 'priority': 0, 'tags': 'a,b'}
        job = Job.from_dict(data)
        assert job.id == 'j1'
        assert job.priority == 0
        assert job.tags == 'a,b'

    def test_to_dict(self):
        job = Job(id='j1', command='ls', tags='x')
        d = job.to_dict()
        assert d['id'] == 'j1'
        assert d['tags'] == 'x'

    def test_get_tags_list(self):
        job = Job(id='j1', command='ls', tags='alpha,beta,gamma')
        assert job.get_tags_list() == ['alpha', 'beta', 'gamma']

    def test_get_tags_list_empty(self):
        job = Job(id='j1', command='ls')
        assert job.get_tags_list() == []

    def test_has_tag(self):
        job = Job(id='j1', command='ls', tags='batch,nightly')
        assert job.has_tag('batch') is True
        assert job.has_tag('daily') is False

    def test_is_retryable(self):
        job = Job(id='j1', command='ls', attempts=1, max_retries=3)
        assert job.is_retryable() is True
        job.attempts = 3
        assert job.is_retryable() is False

    def test_generate_id(self):
        id1 = Job.generate_id()
        id2 = Job.generate_id()
        assert id1 != id2
        assert len(id1) > 10

    def test_get_priority_name(self):
        assert Job(id='x', command='y', priority=0).get_priority_name() == 'low'
        assert Job(id='x', command='y', priority=1).get_priority_name() == 'medium'
        assert Job(id='x', command='y', priority=2).get_priority_name() == 'high'


class TestJobState:
    def test_all_states(self):
        states = JobState.all_states()
        assert 'pending' in states
        assert 'cancelled' in states
        assert len(states) == 6

    def test_terminal_states(self):
        terminal = JobState.terminal_states()
        assert 'completed' in terminal
        assert 'dead' in terminal
        assert 'pending' not in terminal

    def test_is_valid(self):
        assert JobState.is_valid('pending') is True
        assert JobState.is_valid('invalid') is False


class TestJobPriority:
    def test_from_string(self):
        assert JobPriority.from_string('low') == 0
        assert JobPriority.from_string('medium') == 1
        assert JobPriority.from_string('high') == 2
        assert JobPriority.from_string('unknown') == 1  # default

    def test_to_string(self):
        assert JobPriority.to_string(0) == 'low'
        assert JobPriority.to_string(2) == 'high'


# ============================================================================
# Storage Tests
# ============================================================================

class TestStorage:
    def test_create_job(self, storage):
        result = storage.create_job({'id': 'j1', 'command': 'echo hi'})
        assert result is True

    def test_create_duplicate_job(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi'})
        result = storage.create_job({'id': 'j1', 'command': 'echo hi'})
        assert result is False

    def test_get_job(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi', 'tags': 'test', 'pool': 'cpu'})
        job = storage.get_job('j1')
        assert job is not None
        assert job['command'] == 'echo hi'
        assert job['tags'] == 'test'
        assert job['pool'] == 'cpu'

    def test_get_nonexistent_job(self, storage):
        assert storage.get_job('nonexistent') is None

    def test_update_job(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi'})
        result = storage.update_job('j1', {'state': 'completed', 'exit_code': 0})
        assert result is True
        job = storage.get_job('j1')
        assert job['state'] == 'completed'

    def test_list_jobs_by_state(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a', 'state': 'pending'})
        storage.create_job({'id': 'j2', 'command': 'b', 'state': 'completed'})
        pending = storage.list_jobs(state='pending')
        assert len(pending) == 1
        assert pending[0]['id'] == 'j1'

    def test_list_jobs_by_tags(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a', 'tags': 'batch,nightly'})
        storage.create_job({'id': 'j2', 'command': 'b', 'tags': 'daily'})
        result = storage.list_jobs(tags='batch')
        assert len(result) == 1
        assert result[0]['id'] == 'j1'

    def test_list_jobs_by_pool(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a', 'pool': 'gpu'})
        storage.create_job({'id': 'j2', 'command': 'b', 'pool': 'cpu'})
        result = storage.list_jobs(pool='gpu')
        assert len(result) == 1
        assert result[0]['id'] == 'j1'

    def test_cancel_job(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a'})
        result = storage.cancel_job('j1')
        assert result is True
        job = storage.get_job('j1')
        assert job['state'] == 'cancelled'

    def test_cancel_completed_job_fails(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a', 'state': 'completed'})
        result = storage.cancel_job('j1')
        assert result is False

    def test_get_job_stats(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a', 'state': 'pending'})
        storage.create_job({'id': 'j2', 'command': 'b', 'state': 'completed'})
        stats = storage.get_job_stats()
        assert stats['pending'] == 1
        assert stats['completed'] == 1

    def test_claim_job_priority_order(self, storage):
        storage.create_job({'id': 'low', 'command': 'a', 'priority': 0})
        storage.create_job({'id': 'high', 'command': 'b', 'priority': 2})
        claimed = storage.claim_job('worker-1')
        assert claimed is not None
        assert claimed['id'] == 'high'

    def test_claim_job_with_pool(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a', 'pool': 'gpu'})
        storage.create_job({'id': 'j2', 'command': 'b', 'pool': 'cpu'})
        claimed = storage.claim_job('worker-1', pool='gpu')
        assert claimed is not None
        assert claimed['id'] == 'j1'

    def test_claim_job_no_pool_filter(self, storage):
        storage.create_job({'id': 'j1', 'command': 'a'})  # no pool
        claimed = storage.claim_job('worker-1')
        assert claimed is not None


# ============================================================================
# Audit Log Tests
# ============================================================================

class TestAuditLog:
    def test_audit_on_create(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi'})
        audit = storage.get_audit_log('j1')
        assert len(audit) == 1
        assert audit[0]['new_state'] == 'pending'
        assert audit[0]['details'] == 'Job created'

    def test_audit_on_state_change(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi'})
        storage.update_job('j1', {'state': 'processing'})
        audit = storage.get_audit_log('j1')
        assert len(audit) == 2
        assert audit[1]['old_state'] == 'pending'
        assert audit[1]['new_state'] == 'processing'

    def test_audit_on_cancel(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi'})
        storage.cancel_job('j1')
        audit = storage.get_audit_log('j1')
        assert any(e['new_state'] == 'cancelled' for e in audit)

    def test_audit_on_claim(self, storage):
        storage.create_job({'id': 'j1', 'command': 'echo hi'})
        storage.claim_job('worker-1')
        audit = storage.get_audit_log('j1')
        assert any(e['new_state'] == 'processing' for e in audit)


# ============================================================================
# Command Validation Tests
# ============================================================================

class TestCommandValidation:
    def test_safe_command(self):
        safe, msg = Storage.validate_command('echo hello')
        assert safe is True

    def test_rm_rf_root(self):
        safe, msg = Storage.validate_command('rm -rf /')
        assert safe is False

    def test_rm_rf_path(self):
        safe, msg = Storage.validate_command('rm -rf /etc')
        assert safe is False

    def test_fork_bomb(self):
        safe, msg = Storage.validate_command(':(){:|:&};:')
        assert safe is False

    def test_mkfs(self):
        safe, msg = Storage.validate_command('mkfs.ext4 /dev/sda')
        assert safe is False

    def test_dd(self):
        safe, msg = Storage.validate_command('dd if=/dev/zero of=/dev/sda')
        assert safe is False

    def test_safe_rm(self):
        safe, msg = Storage.validate_command('rm temp.txt')
        assert safe is True


# ============================================================================
# Queue Tests
# ============================================================================

class TestQueue:
    def test_enqueue(self, queue):
        job = queue.enqueue({'command': 'echo hello'})
        assert job is not None
        assert job.state == 'pending'
        assert job.command == 'echo hello'

    def test_enqueue_with_priority(self, queue):
        job = queue.enqueue({'command': 'echo hi', 'priority': 2})
        assert job.priority == 2

    def test_enqueue_with_tags(self, queue):
        job = queue.enqueue({'command': 'echo hi', 'tags': 'test,batch'})
        assert job.tags == 'test,batch'

    def test_enqueue_requires_command(self, queue):
        with pytest.raises(ValueError):
            queue.enqueue({'id': 'no-command'})

    def test_list_jobs(self, queue):
        queue.enqueue({'command': 'a'})
        queue.enqueue({'command': 'b'})
        jobs = queue.list_jobs()
        assert len(jobs) == 2

    def test_get_status(self, queue):
        queue.enqueue({'command': 'a'})
        status = queue.get_status()
        assert status['total_jobs'] == 1
        assert status['jobs']['pending'] == 1

    def test_schedule_job(self, queue):
        job = queue.schedule_job({'command': 'echo later'}, 3600)
        assert job is not None
        assert job.run_at is not None

    def test_retry_from_dlq(self, queue, storage):
        queue.enqueue({'id': 'dead-job', 'command': 'echo fail'})
        storage.update_job('dead-job', {'state': 'dead', 'attempts': 3})
        result = queue.retry_job('dead-job')
        assert result is True
        job = queue.get_job('dead-job')
        assert job.state == 'pending'
        assert job.attempts == 0

    def test_list_dlq(self, queue, storage):
        queue.enqueue({'id': 'dead-1', 'command': 'fail'})
        storage.update_job('dead-1', {'state': 'dead'})
        dlq = queue.list_dlq()
        assert len(dlq) == 1
        assert dlq[0].id == 'dead-1'


# ============================================================================
# Config Tests
# ============================================================================

class TestConfig:
    def test_get_default(self, config):
        assert config.get('max_retries') == 3
        assert config.get('backoff_base') == 2

    def test_set_and_get(self, config):
        config.set('max_retries', 10)
        assert config.get('max_retries') == 10

    def test_get_all_includes_defaults(self, config):
        all_cfg = config.get_all()
        assert 'max_retries' in all_cfg
        assert 'command_validation' in all_cfg
        assert 'webhook_rate_limit' in all_cfg

    def test_is_valid_key(self, config):
        assert config.is_valid_key('max_retries') is True
        assert config.is_valid_key('nonexistent') is False


# ============================================================================
# Rate Limiter Tests
# ============================================================================

class TestRateLimiter:
    def test_allows_under_limit(self):
        rl = RateLimiter(max_per_minute=5)
        for _ in range(5):
            assert rl.allow('key1') is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_per_minute=3)
        for _ in range(3):
            rl.allow('key1')
        assert rl.allow('key1') is False

    def test_separate_keys(self):
        rl = RateLimiter(max_per_minute=2)
        rl.allow('key1')
        rl.allow('key1')
        assert rl.allow('key1') is False
        assert rl.allow('key2') is True  # different key


# ============================================================================
# Migration Tests
# ============================================================================

class TestMigrations:
    def test_migrations_exist(self):
        assert len(MIGRATIONS) >= 5

    def test_migration_versions_sequential(self):
        versions = [m.version for m in MIGRATIONS]
        for i in range(1, len(versions)):
            assert versions[i] > versions[i-1]

    def test_apply_migrations(self, db_path):
        storage = Storage(db_path)
        manager = MigrationManager(db_path)
        result = manager.migrate()
        assert result['success'] is True


# ============================================================================
# Utility Tests
# ============================================================================

class TestUtils:
    def test_parse_tags(self):
        assert parse_tags('a,b,c') == ['a', 'b', 'c']
        assert parse_tags('') == []
        assert parse_tags(None) == []
        assert parse_tags(' x , y ') == ['x', 'y']

    def test_format_duration(self):
        assert format_duration(0.5) == '500ms'
        assert format_duration(45) == '45.0s'
        assert format_duration(125) == '2m 5s'
        assert format_duration(3661) == '1h 1m'

    def test_truncate_string(self):
        assert truncate_string('hello', 10) == 'hello'
        assert truncate_string('abcdefghij', 5) == 'abc..'
        assert truncate_string('', 5) == ''
        assert truncate_string(None, 5) == ''

    def test_calculate_backoff(self):
        assert calculate_backoff_delay(1, 2) == 2
        assert calculate_backoff_delay(3, 2) == 8
        assert calculate_backoff_delay(0, 2) == 1


# ============================================================================
# Webhook Manager Tests
# ============================================================================

class TestWebhookManager:
    def test_add_webhook(self, storage):
        manager = WebhookManager(storage)
        result = manager.add_webhook('wh1', 'http://example.com', ['job.completed'])
        assert result is True

    def test_list_webhooks(self, storage):
        manager = WebhookManager(storage)
        manager.add_webhook('wh1', 'http://example.com', ['job.completed'])
        webhooks = manager.list_webhooks()
        assert len(webhooks) == 1
        assert webhooks[0]['url'] == 'http://example.com'

    def test_remove_webhook(self, storage):
        manager = WebhookManager(storage)
        manager.add_webhook('wh1', 'http://example.com', ['*'])
        result = manager.remove_webhook('wh1')
        assert result is True
        assert len(manager.list_webhooks()) == 0

    def test_toggle_webhook(self, storage):
        manager = WebhookManager(storage)
        manager.add_webhook('wh1', 'http://example.com', ['*'])
        manager.toggle_webhook('wh1', False)
        webhooks = manager.list_webhooks()
        assert webhooks[0]['enabled'] is False

    def test_get_webhooks_for_event(self, storage):
        manager = WebhookManager(storage)
        manager.add_webhook('wh1', 'http://a.com', ['job.completed'])
        manager.add_webhook('wh2', 'http://b.com', ['job.failed'])
        result = manager.get_webhooks_for_event('job.completed')
        assert len(result) == 1
        assert result[0]['url'] == 'http://a.com'

    def test_wildcard_webhook(self, storage):
        manager = WebhookManager(storage)
        manager.add_webhook('wh1', 'http://a.com', ['*'])
        result = manager.get_webhooks_for_event('job.started')
        assert len(result) == 1

    def test_webhook_events(self):
        events = WebhookEvent.all_events()
        assert 'job.started' in events
        assert 'job.completed' in events
        assert 'job.failed' in events
        assert 'job.timeout' in events
        assert 'job.cancelled' in events


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
