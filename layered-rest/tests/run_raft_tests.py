"""
Raft Test Suite Runner
Runs all 5 Raft test cases in sequence
"""

import subprocess
import sys
import time

TESTS = [
    ("Test 1: Leader Election", "test_raft_leader_election.py"),
    ("Test 2: Leader Failure", "test_raft_leader_failure.py"),
    ("Test 3: Log Replication", "test_raft_log_replication.py"),
    ("Test 4: Follower Recovery", "test_raft_follower_recovery.py"),
    ("Test 5: Consistency", "test_raft_consistency.py")
]

def run_test(name, script):
    """Run a single test and return success status"""
    print("\n" + "=" * 70)
    print(f"RUNNING: {name}")
    print("=" * 70)
    
    result = subprocess.run(
        ["python3", script],
        cwd="/app/tests"
    )
    
    success = result.returncode == 0
    
    if success:
        print(f"\n✓ {name} PASSED")
    else:
        print(f"\n✗ {name} FAILED")
    
    # Wait between tests
    time.sleep(3)
    
    return success

def main():
    """Run all tests"""
    print("=" * 70)
    print("RAFT CONSENSUS ALGORITHM - TEST SUITE")
    print("=" * 70)
    print(f"Running {len(TESTS)} tests...\n")
    
    results = []
    
    for name, script in TESTS:
        success = run_test(name, script)
        results.append((name, success))
    
    # Print summary
    print("\n\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{status}: {name}")
    
    print("=" * 70)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("=" * 70)
    
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
