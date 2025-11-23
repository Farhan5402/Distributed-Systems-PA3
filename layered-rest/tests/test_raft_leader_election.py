"""
Test Case 1: Leader Election
Verifies that a leader is elected when the cluster starts.
"""

import requests
import time
import sys
import os

# Use Docker service names if in container, otherwise localhost
if os.path.exists('/.dockerenv'):
    BASE_URLS = [
        "http://node-1:8000",
        "http://node-2:8000",
        "http://node-3:8000",
        "http://node-4:8000",
        "http://node-5:8000"
    ]
else:
    BASE_URLS = [
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003",
        "http://localhost:8004",
        "http://localhost:8005"
    ]

def test_leader_election():
    """Test that exactly one leader is elected"""
    print("=" * 60)
    print("TEST 1: Leader Election")
    print("=" * 60)
    
    # Wait for election to complete
    print("\n[1] Waiting for leader election...")
    time.sleep(5)
    
    # Check status of all nodes
    leaders = []
    followers = []
    
    for i, url in enumerate(BASE_URLS, 1):
        try:
            response = requests.get(f"{url}/raft/status", timeout=2)
            status = response.json()
            
            print(f"\nNode {i} ({status['node_id']}):")
            print(f"  State: {status['state']}")
            print(f"  Term: {status['term']}")
            print(f"  Leader: {status['leader']}")
            
            if status['state'] == 'LEADER':
                leaders.append(status['node_id'])
            elif status['state'] == 'FOLLOWER':
                followers.append(status['node_id'])
        
        except Exception as e:
            print(f"\nNode {i}: ERROR - {e}")
    
    # Verify exactly one leader
    print("\n" + "=" * 60)
    print(f"Leaders found: {len(leaders)} - {leaders}")
    print(f"Followers found: {len(followers)} - {followers}")
    
    if len(leaders) == 1:
        print("\n✓ TEST PASSED: Exactly one leader elected")
        print(f"  Leader: {leaders[0]}")
        return True
    else:
        print(f"\n✗ TEST FAILED: Expected 1 leader, found {len(leaders)}")
        return False

if __name__ == "__main__":
    success = test_leader_election()
    sys.exit(0 if success else 1)
