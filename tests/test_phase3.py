"""
Test script for Phase 3 features
Tests job timeouts, webhooks, and priority inheritance
"""
import sys
import os
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from queuectl.storage import Storage
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.dependencies import DependencyResolver
from queuectl.webhooks import WebhookManager, WebhookDispatcher, WebhookEvent
from queuectl.models import Job, JobPriority
from queuectl.migrations import MigrationManager


def test_migrations():
    """Test database migrations"""
    print("\n" + "=" * 70)
    print("TEST 1: Database Migrations")
    print("=" * 70)
    
    storage = Storage()
    manager = MigrationManager(storage.db_path)
    
    current_version = manager.get_current_version()
    print(f"Current schema version: {current_version}")
    
    result = manager.migrate()
    
    if result['success']:
        print(f"✅ Migrations successful")
        print(f"   New version: {result['current_version']}")
        return True
    else:
        print(f"❌ Migration failed: {result['message']}")
        return False


def test_job_timeout():
    """Test job-specific timeout"""
    print("\n" + "=" * 70)
    print("TEST 2: Job Timeout")
    print("=" * 70)
    
    storage = Storage()
    config = Config(storage)
    queue = Queue(storage, config)
    
    # Enqueue job with custom timeout
    job_data = {
        'id': 'timeout-test',
        'command': 'sleep 5',
        'timeout': 2  # 2 second timeout
    }
    
    job = queue.enqueue(job_data)
    
    if job and job.timeout == 2:
        print(f"✅ Job enqueued with custom timeout: {job.timeout}s")
        
        # Verify timeout is stored
        retrieved_job = queue.get_job('timeout-test')
        if retrieved_job and retrieved_job.timeout == 2:
            print(f"✅ Timeout persisted correctly")
            return True
        else:
            print(f"❌ Timeout not persisted")
            return False
    else:
        print(f"❌ Failed to enqueue job with timeout")
        return False


def test_webhooks():
    """Test webhook system"""
    print("\n" + "=" * 70)
    print("TEST 3: Webhook System")
    print("=" * 70)
    
    storage = Storage()
    manager = WebhookManager(storage)
    
    # Add webhook
    success = manager.add_webhook(
        'test-webhook',
        'https://example.com/webhook',
        [WebhookEvent.JOB_COMPLETED, WebhookEvent.JOB_FAILED],
        'secret123'
    )
    
    if not success:
        print(f"❌ Failed to add webhook")
        return False
    
    print(f"✅ Webhook added successfully")
    
    # List webhooks
    webhooks = manager.list_webhooks()
    
    if len(webhooks) > 0:
        print(f"✅ Webhook retrieved: {webhooks[0]['url']}")
    else:
        print(f"❌ Failed to retrieve webhooks")
        return False
    
    # Test webhook for event
    event_webhooks = manager.get_webhooks_for_event(WebhookEvent.JOB_COMPLETED)
    
    if len(event_webhooks) > 0:
        print(f"✅ Webhook found for job.completed event")
        return True
    else:
        print(f"❌ Webhook not found for event")
        return False


def test_priority_inheritance():
    """Test priority inheritance"""
    print("\n" + "=" * 70)
    print("TEST 4: Priority Inheritance")
    print("=" * 70)
    
    storage = Storage()
    config = Config(storage)
    queue = Queue(storage, config)
    deps = DependencyResolver(storage)
    
    # Create dependency chain: C -> B -> A
    job_a = queue.enqueue({'id': 'priority-a', 'command': 'echo A', 'priority': JobPriority.LOW})
    job_b = queue.enqueue({'id': 'priority-b', 'command': 'echo B', 'priority': JobPriority.LOW})
    
    # Add dependencies
    deps.add_dependency('priority-b', 'priority-a')
    
    print(f"Created jobs A and B with LOW priority")
    print(f"Added dependency: B depends on A")
    
    # Now enqueue high-priority job C that depends on B
    job_c = queue.enqueue({'id': 'priority-c', 'command': 'echo C', 'priority': JobPriority.HIGH})
    deps.add_dependency('priority-c', 'priority-b')
    
    # Manually propagate priority (normally done in enqueue)
    deps.propagate_priority('priority-c', JobPriority.HIGH)
    
    print(f"Enqueued job C with HIGH priority, depends on B")
    print(f"Propagated priority to dependencies")
    
    # Check if priorities were updated
    updated_a = queue.get_job('priority-a')
    updated_b = queue.get_job('priority-b')
    
    if updated_a.priority == JobPriority.HIGH and updated_b.priority == JobPriority.HIGH:
        print(f"✅ Priority inheritance working correctly")
        print(f"   Job A priority: {updated_a.get_priority_name()}")
        print(f"   Job B priority: {updated_b.get_priority_name()}")
        return True
    else:
        print(f"❌ Priority inheritance failed")
        print(f"   Job A priority: {updated_a.get_priority_name()}")
        print(f"   Job B priority: {updated_b.get_priority_name()}")
        return False


def run_all_tests():
    """Run all Phase 3 tests"""
    print("\n" + "=" * 70)
    print("QUEUECTL PHASE 3 TESTS")
    print("=" * 70)
    
    tests = [
        ("Database Migrations", test_migrations),
        ("Job Timeout", test_job_timeout),
        ("Webhook System", test_webhooks),
        ("Priority Inheritance", test_priority_inheritance),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<35} {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL PHASE 3 TESTS PASSED!")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
