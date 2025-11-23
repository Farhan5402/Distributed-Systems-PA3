"""
Test Case 2: Leader Failure and Re-election
Simulates leader failure by stopping the leader container and verifies re-election.
"""

import requests
import time
import sys
import subprocess
import os

# Use Docker service names if in container, otherwise localhost
if os.path.exists('/.dockerenv'):
    print("ERROR: This test cannot run inside a container (requires docker stop/start)")
    print("Please run from host: python3 tests/test_raft_leader_failure.py")
    sys.exit(1)

BASE_URLS = [
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
    "http://localhost:8004",
    "http://localhost:8005"
]

CONTAINER_NAMES = [
    "raft-node-1",
    "raft-node-2",
    "raft-node-3",
    "raft-node-4",
    "raft-node-5"
]

def get_leader():
    """Find the current leader"""
    for i, url in enumerate(BASE_URLS, 1):
        try:
            response = requests.get(f"{url}/raft/status", timeout=2)
            status = response.json()
            if status['state'] == 'LEADER':
                return status['node_id'], i - 1, url
        except:
            pass
    return None, None, None

def test_leader_failure():
    """Test leader failure and re-election"""
    print("=" * 60)
    print("TEST 2: Leader Failure and Re-election")
    print("=" * 60)
    
    # Step 1: Wait for initial leader
    print("\n[1] Waiting for initial leader election...")
    time.sleep(5)
    
    initial_leader, leader_idx, leader_url = get_leader()
    if not initial_leader:
        print("✗ TEST FAILED: No initial leader found")
        return False
    
    print(f"\n[2] Initial leader: {initial_leader}")
    
    # Step 2: Stop the leader container
    leader_container = CONTAINER_NAMES[leader_idx]
    print(f"\n[3] Stopping leader container: {leader_container}")
    
    result = subprocess.run(
        ["docker", "stop", leader_container],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"✗ Failed to stop container: {result.stderr}")
        return False
    
    print(f"✓ Leader container stopped")
    
    # Step 3: Wait for re-election
    print(f"\n[4] Waiting for re-election (up to 10 seconds)...")
    time.sleep(10)
    
    # Step 4: Check for new leader
    new_leader, new_idx, new_url = get_leader()
    
    if not new_leader:
        print("✗ TEST FAILED: No new leader elected after failure")
        # Restart the stopped container
        subprocess.run(["docker", "start", leader_container])
        return False
    
    if new_leader == initial_leader:
        print(f"✗ TEST FAILED: Same leader ({new_leader}) - expected different leader")
        subprocess.run(["docker", "start", leader_container])
        return False
    
    print(f"\n[5] New leader elected: {new_leader}")
    
    # Step 5: Verify new leader is functional
    try:
        response = requests.get(f"{new_url}/raft/status", timeout=2)
        status = response.json()
        print(f"\nNew leader status:")
        print(f"  State: {status['state']}")
        print(f"  Term: {status['term']} (should be > initial term)")
    except Exception as e:
        print(f"✗ Failed to get new leader status: {e}")
        subprocess.run(["docker", "start", leader_container])
        return False
    
    # Step 6: Restart the stopped container
    print(f"\n[6] Restarting stopped container: {leader_container}")
    subprocess.run(["docker", "start", leader_container])
    time.sleep(3)
    
    print("\n" + "=" * 60)
    print("✓ TEST PASSED: New leader elected after failure")
    print(f"  Initial leader: {initial_leader}")
    print(f"  New leader: {new_leader}")
    return True

if __name__ == "__main__":
    success = test_leader_failure()
    sys.exit(0 if success else 1)
