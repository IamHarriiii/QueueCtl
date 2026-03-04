"""
Test script for Phase 1 enhancements
Tests priority queues, cancellation, metrics, and migrations
"""
import sys
import os
import time
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from queuectl.storage import Storage
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.migrations import MigrationManager
from queuectl.metrics import MetricsTracker
from queuectl.models import Job, JobPriority, JobState


def test_migrations():
    """Test database migrations"""
    print("\n" + "=" * 70)
    print("TEST 1: Database Migrations")
    print("=" * 70)
    
    storage = Storage()
    manager = MigrationManager(storage.db_path)
    
    current_version = manager.get_current_version()
    print(f"Current schema version: {current_version}")
    
    pending = manager.get_pending_migrations()
    print(f"Pending migrations: {len(pending)}")
    
    if pending:
        result = manager.migrate()
        if result['success']:
            print(f"✅ Migrations applied successfully")
            print(f"   New version: {result['current_version']}")
        else:
            print(f"❌ Migration failed: {result['message']}")
            return False
    else:
        print("✅ No pending migrations")
    
    return True


def test_priority_queues():
    """Test priority-based job claiming"""
    print("\n" + "=" * 70)
    print("TEST 2: Priority Queues")
    print("=" * 70)
    
    storage = Storage()
    config = Config(storage)
    queue = Queue(storage, config)
    
    # Enqueue jobs with different priorities
    jobs = [
        {'id': 'low-priority', 'command': 'echo low', 'priority': JobPriority.LOW},
        {'id': 'high-priority', 'command': 'echo high', 'priority': JobPriority.HIGH},
        {'id': 'medium-priority', 'command': 'echo medium', 'priority': JobPriority.MEDIUM},
    ]
    
    for job_data in jobs:
        job = queue.enqueue(job_data)
        print(f"Enqueued: {job.id} (priority: {job.get_priority_name()})")
    
    # Claim jobs and verify priority order
    claimed_order = []
    for i in range(3):
        job_dict = storage.claim_job(f"test-worker-{i}")
        if job_dict:
            job = Job.from_dict(job_dict)
            claimed_order.append(job.id)
            print(f"Claimed: {job.id} (priority: {job.get_priority_name()})")
    
    # High priority should be claimed first
    if claimed_order[0] == 'high-priority':
        print("✅ Priority queue working correctly")
        return True
    else:
        print(f"❌ Priority queue failed. Order: {claimed_order}")
        return False


def test_cancellation():
    """Test job cancellation"""
    print("\n" + "=" * 70)
    print("TEST 3: Job Cancellation")
    print("=" * 70)
    
    storage = Storage()
    config = Config(storage)
    queue = Queue(storage, config)
    
    # Enqueue a job
    job = queue.enqueue({'id': 'cancel-test', 'command': 'sleep 100'})
    print(f"Enqueued job: {job.id}")
    
    # Cancel it
    success = storage.cancel_job(job.id)
    
    if success:
        # Verify it's cancelled
        job_dict = storage.get_job(job.id)
        if job_dict and job_dict['state'] == 'cancelled':
            print("✅ Job cancellation working correctly")
            return True
        else:
            print("❌ Job not in cancelled state")
            return False
    else:
        print("❌ Failed to cancel job")
        return False


def test_metrics():
    """Test metrics tracking"""
    print("\n" + "=" * 70)
    print("TEST 4: Metrics Tracking")
    print("=" * 70)
    
    storage = Storage()
    tracker = MetricsTracker(storage)
    
    # Record some metrics
    tracker.record_metric('test_metric', 42.5, {'source': 'test'})
    tracker.record_queue_snapshot()
    
    # Get stats
    stats = tracker.get_job_stats(period_hours=24)
    print(f"Job stats: {stats}")
    
    # Export metrics
    data = tracker.export_metrics(period_hours=1, format='json')
    metrics_data = json.loads(data)
    
    if len(metrics_data) > 0:
        print(f"✅ Metrics tracking working ({len(metrics_data)} metrics recorded)")
        return True
    else:
        print("❌ No metrics recorded")
        return False


def run_all_tests():
    """Run all Phase 1 tests"""
    print("\n" + "=" * 70)
    print("QUEUECTL PHASE 1 ENHANCEMENT TESTS")
    print("=" * 70)
    
    tests = [
        ("Migrations", test_migrations),
        ("Priority Queues", test_priority_queues),
        ("Job Cancellation", test_cancellation),
        ("Metrics Tracking", test_metrics),
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
        print(f"{test_name:<20} {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL PHASE 1 TESTS PASSED!")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
