"""
Test script for Phase 2 features
Tests job dependencies and web dashboard
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from queuectl.storage import Storage
from queuectl.config import Config
from queuectl.queue import Queue
from queuectl.dependencies import DependencyResolver
from queuectl.models import Job, JobPriority


def test_dependencies():
    """Test job dependency system"""
    print("\n" + "=" * 70)
    print("TEST 1: Job Dependencies")
    print("=" * 70)
    
    storage = Storage()
    config = Config(storage)
    queue = Queue(storage, config)
    deps = DependencyResolver(storage)
    
    # Create jobs
    job_a = queue.enqueue({'id': 'job-a', 'command': 'echo A'})
    job_b = queue.enqueue({'id': 'job-b', 'command': 'echo B'})
    job_c = queue.enqueue({'id': 'job-c', 'command': 'echo C'})
    
    print(f"Created jobs: {job_a.id}, {job_b.id}, {job_c.id}")
    
    # Add dependencies: C depends on B, B depends on A
    deps.add_dependency('job-c', 'job-b')
    deps.add_dependency('job-b', 'job-a')
    
    print("Added dependencies: C→B→A")
    
    # Check dependencies
    c_deps = deps.get_dependencies('job-c')
    print(f"Job C dependencies: {c_deps}")
    
    # Check if dependencies are met
    c_ready = deps.are_dependencies_met('job-c')
    print(f"Job C ready to run: {c_ready}")
    
    if not c_ready and c_deps == ['job-b']:
        print("✅ Dependency system working correctly")
        return True
    else:
        print("❌ Dependency system failed")
        return False


def test_circular_dependency():
    """Test circular dependency detection"""
    print("\n" + "=" * 70)
    print("TEST 2: Circular Dependency Detection")
    print("=" * 70)
    
    storage = Storage()
    config = Config(storage)
    queue = Queue(storage, config)
    deps = DependencyResolver(storage)
    
    # Create jobs
    job_x = queue.enqueue({'id': 'job-x', 'command': 'echo X'})
    job_y = queue.enqueue({'id': 'job-y', 'command': 'echo Y'})
    
    # Add dependency: Y depends on X
    deps.add_dependency('job-y', 'job-x')
    
    # Try to create cycle: X depends on Y (should fail)
    would_cycle = deps.add_dependency('job-x', 'job-y')
    
    if not would_cycle:
        print("✅ Circular dependency correctly prevented")
        return True
    else:
        print("❌ Circular dependency was allowed (FAIL)")
        return False


def test_dependency_tree():
    """Test dependency tree generation"""
    print("\n" + "=" * 70)
    print("TEST 3: Dependency Tree")
    print("=" * 70)
    
    storage = Storage()
    deps = DependencyResolver(storage)
    
    tree = deps.get_dependency_tree('job-c')
    
    if tree and 'dependencies' in tree:
        print(f"✅ Dependency tree generated")
        print(f"   Tree: {tree}")
        return True
    else:
        print("❌ Failed to generate dependency tree")
        return False


def run_all_tests():
    """Run all Phase 2 tests"""
    print("\n" + "=" * 70)
    print("QUEUECTL PHASE 2 TESTS")
    print("=" * 70)
    
    tests = [
        ("Job Dependencies", test_dependencies),
        ("Circular Dependency Detection", test_circular_dependency),
        ("Dependency Tree", test_dependency_tree),
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
        print("\n🎉 ALL PHASE 2 TESTS PASSED!")
        return 0
    else:
        print("\n⚠️  SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
