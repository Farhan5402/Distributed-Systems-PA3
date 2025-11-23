"""
Test Case 4: Follower Recovery (Catch-up)
Stops a follower, performs operations, then restarts the follower
to verify it catches up with the leader's log.
"""

import requests
import time
import sys
import subprocess
import os

# Use Docker service names if in container, otherwise localhost
if os.path.exists('/.dockerenv'):
    print("ERROR: This test cannot run inside a container (requires docker stop/start)")
    print("Please run from host: python3 tests/test_raft_follower_recovery.py")
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
    for i, url in enumerate(BASE_URLS):
        try:
            response = requests.get(f"{url}/raft/status", timeout=2)
            status = response.json()
            if status['state'] == 'LEADER':
                return url, status, i
        except:
            pass
    return None, None, None

def get_follower(leader_idx):
    """Get a follower that's not the leader"""
    for i, url in enumerate(BASE_URLS):
        if i == leader_idx:
            continue
        try:
            response = requests.get(f"{url}/raft/status", timeout=2)
            status = response.json()
            if status['state'] == 'FOLLOWER':
                return url, status, i
        except:
            pass
    return None, None, None

def test_follower_recovery():
    """Test follower recovery and catch-up"""
    print("=" * 60)
    print("TEST 4: Follower Recovery (Catch-up)")
    print("=" * 60)
    
    # Step 1: Find leader and a follower
    print("\n[1] Finding leader and follower...")
    leader_url, leader_status, leader_idx = get_leader()
    
    if not leader_url:
        print("✗ TEST FAILED: No leader found")
        return False
    
    follower_url, follower_status, follower_idx = get_follower(leader_idx)
    
    if not follower_url:
        print("✗ TEST FAILED: No follower found")
        return False
    
    print(f"✓ Leader: {leader_status['node_id']}")
    print(f"✓ Follower to stop: {follower_status['node_id']}")
    
    # Step 2: Clear queue
    print("\n[2] Clearing queue...")
    try:
        requests.post(f"{leader_url}/clear", timeout=5)
        time.sleep(2)
    except Exception as e:
        print(f"✗ Failed to clear: {e}")
        return False
    
    # Step 3: Stop follower
    follower_container = CONTAINER_NAMES[follower_idx]
    print(f"\n[3] Stopping follower: {follower_container}")
    
    result = subprocess.run(
        ["docker", "stop", follower_container],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"✗ Failed to stop container: {result.stderr}")
        return False
    
    print("✓ Follower stopped")
    time.sleep(2)
    
    # Step 4: Add tracks while follower is down
    tracks = [
        {"id": 10, "title": "Recovery Song 1", "artist": "Test", "duration": 100, "votes": 0},
        {"id": 11, "title": "Recovery Song 2", "artist": "Test", "duration": 120, "votes": 0},
        {"id": 12, "title": "Recovery Song 3", "artist": "Test", "duration": 140, "votes": 0}
    ]
    
    print(f"\n[4] Adding {len(tracks)} tracks while follower is down...")
    
    for track in tracks:
        try:
            response = requests.post(f"{leader_url}/add_track", json=track, timeout=5)
            if response.status_code != 200:
                print(f"✗ Failed to add track: {response.status_code}")
                subprocess.run(["docker", "start", follower_container])
                return False
            print(f"  ✓ Added: {track['title']}")
        except Exception as e:
            print(f"✗ Failed to add track: {e}")
            subprocess.run(["docker", "start", follower_container])
            return False
    
    time.sleep(2)
    
    # Step 5: Get leader's queue
    leader_queue = requests.get(f"{leader_url}/queue", timeout=2).json()
    leader_track_ids = sorted([t['id'] for t in leader_queue])
    print(f"\n[5] Leader queue: {leader_track_ids}")
    
    # Step 6: Restart follower
    print(f"\n[6] Restarting follower: {follower_container}")
    subprocess.run(["docker", "start", follower_container])
    time.sleep(5)  # Give container time to fully start
    
    # Wait for follower to catch up
    print("\n[7] Waiting for follower to catch up...")
    max_wait = 20  # seconds
    caught_up = False
    for i in range(max_wait):
        time.sleep(1)
        try:
            # Get current leader queue (in case more operations happened)
            leader_queue_now = requests.get(f"{leader_url}/queue", timeout=2).json()
            current_leader_ids = sorted([t['id'] for t in leader_queue_now])
            
            # Get follower queue
            response = requests.get(f"{follower_url}/queue", timeout=2)
            follower_queue = response.json()
            follower_track_ids = sorted([t['id'] for t in follower_queue])
            
            # Check if follower matches current leader state
            if follower_track_ids == current_leader_ids and len(follower_track_ids) >= 3:
                print(f"  ✓ Caught up after {i+1} seconds")
                leader_track_ids = current_leader_ids  # Update expected value
                caught_up = True
                break
        except Exception as e:
            print(f"  Attempt {i+1}: {e}")
    
    if not caught_up:
        print(f"  ! Catch-up not confirmed during wait period, verifying final state...")
    
    # Step 7: Verify follower caught up
    print(f"\n[8] Verifying final state...")
    
    # Step 7: Verify follower caught up
    print(f"\n[8] Verifying final state...")
    
    try:
        # Get final state from both leader and follower
        leader_final = requests.get(f"{leader_url}/queue", timeout=2).json()
        leader_final_ids = sorted([t['id'] for t in leader_final])
        
        follower_final = requests.get(f"{follower_url}/queue", timeout=2).json()
        follower_final_ids = sorted([t['id'] for t in follower_final])
        
        print(f"Leader queue: {leader_final_ids}")
        print(f"Follower queue: {follower_final_ids}")
        
        if follower_final_ids == leader_final_ids and len(follower_final_ids) >= 3:
            print("\n" + "=" * 60)
            print("✓ TEST PASSED: Follower caught up successfully")
            print(f"  Both nodes have: {leader_final_ids}")
            print(f"  Queue size: {len(leader_final_ids)}")
            return True
        else:
            print("\n" + "=" * 60)
            print("✗ TEST FAILED: Follower did not catch up")
            print(f"  Leader: {leader_final_ids}")
            print(f"  Follower: {follower_final_ids}")
            return False
    
    except Exception as e:
        print(f"✗ Failed to verify: {e}")
        return False

if __name__ == "__main__":
    success = test_follower_recovery()
    sys.exit(0 if success else 1)
