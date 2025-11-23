"""
Test Case 3: Log Replication
Verifies that operations are replicated across all nodes.
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

def test_log_replication():
    """Test that operations replicate to all followers"""
    print("=" * 60)
    print("TEST 3: Log Replication")
    print("=" * 60)
    
    # Step 1: Find leader
    print("\n[1] Finding leader...")
    leader_url, leader_status = get_leader()
    
    if not leader_url:
        print("✗ TEST FAILED: No leader found")
        return False
    
    print(f"✓ Leader found: {leader_status['node_id']}")
    
    # Step 2: Clear queue on leader
    print("\n[2] Clearing queue...")
    try:
        requests.post(f"{leader_url}/clear", timeout=5)
        time.sleep(2)
    except Exception as e:
        print(f"✗ Failed to clear queue: {e}")
        return False
    
    # Step 3: Add tracks to leader
    tracks = [
        {"id": 1, "title": "Song A", "artist": "Artist 1", "duration": 180, "votes": 0},
        {"id": 2, "title": "Song B", "artist": "Artist 2", "duration": 200, "votes": 0},
        {"id": 3, "title": "Song C", "artist": "Artist 3", "duration": 220, "votes": 0}
    ]
    
    print(f"\n[3] Adding {len(tracks)} tracks to leader...")
    
    for track in tracks:
        try:
            response = requests.post(f"{leader_url}/add_track", json=track, timeout=5)
            if response.status_code != 200:
                print(f"✗ Failed to add track {track['id']}: {response.status_code}")
                return False
            print(f"  ✓ Added: {track['title']}")
        except Exception as e:
            print(f"✗ Failed to add track {track['id']}: {e}")
            return False
    
    # Step 4: Wait for replication
    print("\n[4] Waiting for replication...")
    time.sleep(3)
    
    # Step 5: Verify all nodes have the same queue
    print("\n[5] Verifying queue on all nodes...")
    
    queues = []
    for i, url in enumerate(BASE_URLS, 1):
        try:
            response = requests.get(f"{url}/queue", timeout=2)
            queue = response.json()
            
            print(f"\nNode {i}: {len(queue)} tracks")
            for track in queue:
                print(f"  - {track['id']}: {track['title']}")
            
            # Store queue (as sorted list of IDs for comparison)
            queue_ids = sorted([t['id'] for t in queue])
            queues.append(queue_ids)
            
        except Exception as e:
            print(f"\nNode {i}: ERROR - {e}")
            queues.append(None)
    
    # Step 6: Verify all queues match
    print("\n[6] Comparing queues...")
    
    valid_queues = [q for q in queues if q is not None]
    
    if len(valid_queues) < 3:  # Need majority
        print(f"✗ TEST FAILED: Only {len(valid_queues)} nodes responded")
        return False
    
    first_queue = valid_queues[0]
    all_match = all(q == first_queue for q in valid_queues)
    
    print("\n" + "=" * 60)
    if all_match and len(first_queue) == len(tracks):
        print("✓ TEST PASSED: All nodes have identical replicated queue")
        print(f"  Tracks: {first_queue}")
        return True
    else:
        print("✗ TEST FAILED: Queues do not match across nodes")
        for i, q in enumerate(queues, 1):
            print(f"  Node {i}: {q}")
        return False

if __name__ == "__main__":
    success = test_log_replication()
    sys.exit(0 if success else 1)
