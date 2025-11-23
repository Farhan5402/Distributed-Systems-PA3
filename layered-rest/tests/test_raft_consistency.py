"""
Test Case 5: Consistency Under Concurrent Operations
Tests that the system maintains consistency when multiple clients
send operations concurrently.
"""

import requests
import time
import sys
import threading
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

def get_leader():
    """Find the current leader"""
    for url in BASE_URLS:
        try:
            response = requests.get(f"{url}/raft/status", timeout=2)
            status = response.json()
            if status['state'] == 'LEADER':
                return url, status
        except:
            pass
    return None, None

def add_track_concurrent(leader_url, track, results, index):
    """Add a track and store the result"""
    try:
        response = requests.post(f"{leader_url}/add_track", json=track, timeout=10)
        if response.status_code == 200:
            results[index] = "SUCCESS"
            print(f"  ✓ Added track {track['id']}")
        else:
            results[index] = f"FAILED-{response.status_code}"
            print(f"  ✗ Failed track {track['id']}: {response.status_code}")
    except Exception as e:
        results[index] = f"ERROR-{str(e)[:30]}"
        print(f"  ✗ Error track {track['id']}: {e}")

def test_consistency():
    """Test consistency under concurrent operations"""
    print("=" * 60)
    print("TEST 5: Consistency Under Concurrent Operations")
    print("=" * 60)
    
    # Step 1: Find leader
    print("\n[1] Finding leader...")
    leader_url, leader_status = get_leader()
    
    if not leader_url:
        print("✗ TEST FAILED: No leader found")
        return False
    
    print(f"✓ Leader: {leader_status['node_id']}")
    
    # Step 2: Clear queue
    print("\n[2] Clearing queue...")
    try:
        requests.post(f"{leader_url}/clear", timeout=5)
        time.sleep(2)
    except Exception as e:
        print(f"✗ Failed to clear: {e}")
        return False
    
    # Step 3: Send concurrent add operations
    num_tracks = 10
    tracks = [
        {
            "id": i,
            "title": f"Concurrent Song {i}",
            "artist": f"Artist {i}",
            "duration": 100 + i * 10,
            "votes": 0
        }
        for i in range(1, num_tracks + 1)
    ]
    
    print(f"\n[3] Sending {num_tracks} concurrent add operations...")
    
    threads = []
    results = [None] * num_tracks
    
    # Launch threads
    for i, track in enumerate(tracks):
        thread = threading.Thread(
            target=add_track_concurrent,
            args=(leader_url, track, results, i)
        )
        threads.append(thread)
        thread.start()
    
    # Wait for all to complete
    for thread in threads:
        thread.join(timeout=15)
    
    # Count successes
    successes = sum(1 for r in results if r == "SUCCESS")
    print(f"\n[4] Operations completed: {successes}/{num_tracks} successful")
    
    if successes < num_tracks * 0.8:  # Allow some failures
        print(f"✗ Too many failures: {successes}/{num_tracks}")
        return False
    
    # Step 4: Wait for replication
    print("\n[5] Waiting for replication...")
    time.sleep(3)
    
    # Step 5: Verify consistency across all nodes
    print("\n[6] Verifying consistency across all nodes...")
    
    queues = []
    for i, url in enumerate(BASE_URLS, 1):
        try:
            response = requests.get(f"{url}/queue", timeout=2)
            queue = response.json()
            queue_ids = sorted([t['id'] for t in queue])
            queues.append(queue_ids)
            print(f"  Node {i}: {len(queue_ids)} tracks - {queue_ids}")
        except Exception as e:
            print(f"  Node {i}: ERROR - {e}")
            queues.append(None)
    
    # Step 6: Check all nodes have same queue
    valid_queues = [q for q in queues if q is not None]
    
    if len(valid_queues) < 3:
        print(f"\n✗ TEST FAILED: Only {len(valid_queues)} nodes responded")
        return False
    
    first_queue = valid_queues[0]
    all_match = all(q == first_queue for q in valid_queues)
    
    print("\n" + "=" * 60)
    if all_match and len(first_queue) == successes:
        print("✓ TEST PASSED: All nodes consistent after concurrent operations")
        print(f"  Queue size: {len(first_queue)}")
        print(f"  Track IDs: {first_queue}")
        return True
    else:
        print("✗ TEST FAILED: Nodes not consistent")
        for i, q in enumerate(queues, 1):
            print(f"  Node {i}: {q}")
        return False

if __name__ == "__main__":
    success = test_consistency()
    sys.exit(0 if success else 1)
