# Raft Consensus Implementation - PA3

**Student**: Farhan  
**Course**: CSE 5306 - Distributed Systems  
**Assignment**: Programming Assignment 3 - Raft Consensus Algorithm

---

## 📋 Overview

This project implements the Raft consensus algorithm for a distributed music queue system. The implementation includes:

- **Q3**: Leader election with randomized timeouts
- **Q4**: Log replication across distributed nodes
- **Q5**: Five automated test cases validating consensus behavior

### Architecture

- **5 Raft Nodes**: `raft-node-1` through `raft-node-5`
- **FastAPI**: HTTP REST API (ports 8001-8005)
- **gRPC**: Raft consensus communication (ports 50051-50055)
- **Redis**: Persistent storage for each node
- **Nginx**: Load balancer
- **Automated Tests**: Comprehensive test suite for validation

---

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (only needed for running tests 2 and 4 from host)
- Ports 8001-8005, 50051-50055 available

### Start the System

```bash
# Clone the repository (if not already)
cd layered-rest

# Start all services
docker-compose up -d

# Wait for leader election (5-10 seconds)
sleep 5

# Verify system is running
curl http://localhost:8001/raft/status | python3 -m json.tool
```

Expected output should show one leader and four followers:
```json
{
    "node_id": "node-X",
    "state": "LEADER",
    "term": 1,
    "leader": "node-X",
    "log_size": 0,
    "commit_index": 0,
    "is_leader": true
}
```

---

## 🧪 Running Tests

All five required tests are included. Tests 1, 3, and 5 run inside the test-runner container. Tests 2 and 4 require Docker access and must run from the host.

**⚠️ IMPORTANT**: Clear the queue before running tests to avoid duplicate data:
```bash
curl -s -X POST http://localhost:8001/clear
sleep 2
```

### Test 1: Leader Election ✅

Verifies exactly one leader is elected and all others are followers.

```bash
docker exec raft-test-runner python3 /app/tests/test_raft_leader_election.py
```

**Expected**: `✓ TEST PASSED: Exactly one leader elected`

---

### Test 2: Leader Failure & Re-election ✅

Stops the current leader and verifies a new leader is automatically elected.

**⚠️ Must run from host (requires Docker access):**

```bash
python3 tests/test_raft_leader_failure.py
```

**Expected**: `✓ TEST PASSED: New leader elected after failure`

---

### Test 3: Log Replication ✅

Adds entries to the leader and verifies they're replicated to all followers.

```bash
docker exec raft-test-runner python3 /app/tests/test_raft_log_replication.py
```

**Expected**: `✓ TEST PASSED: All nodes have identical replicated queue`

---

### Test 4: Follower Recovery (Catch-up) ✅

Stops a follower, adds data, restarts the follower, and verifies it catches up.

**⚠️ Must run from host (requires Docker access):**

```bash
python3 tests/test_raft_follower_recovery.py
```

**Expected**: `✓ TEST PASSED: Follower caught up successfully`

---

### Test 5: Consistency Under Concurrent Operations ✅

Sends concurrent operations and verifies all nodes remain consistent.

```bash
docker exec raft-test-runner python3 /app/tests/test_raft_consistency.py
```

**Expected**: `✓ TEST PASSED: All nodes consistent after concurrent operations`

---

## 🎯 API Endpoints

### Raft Status
```bash
curl http://localhost:8001/raft/status
```

### Check Queue (any node)
```bash
curl http://localhost:8001/queue
curl http://localhost:8002/queue
# ... etc
```

### Add Track (automatically forwards to leader if sent to follower)
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"id": 1, "title": "Song Name", "artist": "Artist", "duration": 180, "votes": 0}' \
  http://localhost:8001/add_track
```

### Vote for Track
```bash
curl -X POST http://localhost:8001/vote/1
```

### Get Next Track
```bash
curl http://localhost:8001/next
```

### Clear Queue
```bash
curl -X POST http://localhost:8001/clear
```

---

## 🔍 Key Features

### Auto-Forwarding
Followers automatically forward write requests to the leader:
- Client sends request to any node
- If follower receives it, auto-forwards to leader
- Returns success response after leader commits
- No manual redirect handling needed

### Fault Tolerance
- Automatic leader election if leader fails
- New leader elected within 2-5 seconds
- Followers catch up after restart
- Persistent state survives container restarts

### Log Replication
- All writes go through Raft consensus
- Majority agreement required for commit
- Consistent replication across all nodes
- Log entries applied in order

---

## 🛠️ Troubleshooting

### System Won't Start

```bash
# Stop everything and clean up
docker-compose down -v

# Rebuild and start fresh
docker-compose build
docker-compose up -d
```

### No Leader Elected

```bash
# Check logs
docker logs raft-node-1
docker logs raft-node-2

# Wait longer (up to 10 seconds)
sleep 10
curl http://localhost:8001/raft/status
```

### Port Conflicts

```bash
# Check if ports are in use
lsof -i :8001
lsof -i :50051

# Kill conflicting processes or change ports in docker-compose.yml
```

### Test Failures

**If Test 2 or 4 fails with "cannot run inside container":**
- These tests MUST run from the host machine
- They need Docker CLI access to stop/start containers
- Run: `python3 tests/test_raft_leader_failure.py` (not docker exec)

**If tests fail due to timing:**
- Wait longer before running tests after startup
- System needs 5-10 seconds for initial leader election

---

## 📁 Project Structure

```
layered-rest/
├── docker-compose.yml          # Service orchestration
├── nginx.conf                  # Load balancer config
├── README.md                   # This file
├── FINAL_DEMO_SCRIPT.md       # Detailed demo walkthrough
├── node/
│   ├── Dockerfile
│   ├── main.py                # FastAPI application
│   ├── raft_node.py           # Raft consensus implementation
│   ├── requirements.txt
│   ├── entrypoint.sh
│   └── proto/
│       ├── raft.proto         # gRPC protocol definition
│       ├── raft_pb2.py        # Generated protobuf
│       └── raft_pb2_grpc.py   # Generated gRPC stubs
├── tests/
│   ├── test_raft_leader_election.py
│   ├── test_raft_leader_failure.py
│   ├── test_raft_log_replication.py
│   ├── test_raft_follower_recovery.py
│   └── test_raft_consistency.py
└── proto/                      # Shared proto files
```

---

## 🧹 Cleanup

```bash
# Stop all services
docker-compose down

# Stop and remove all data (including Redis volumes)
docker-compose down -v

# Remove built images
docker-compose down --rmi all -v
```

---

## 📝 Implementation Notes

### Raft Algorithm Components

1. **Leader Election (Q3)**
   - Randomized election timeouts (1.5-3.0 seconds)
   - Majority voting required
   - Term-based leadership

2. **Log Replication (Q4)**
   - AppendEntries RPC for heartbeats and log sync
   - Prev log index/term consistency check
   - Commit index advancement on majority replication

3. **Persistence**
   - Redis stores: queue, metadata, last_applied index
   - Raft log is in-memory (rebuilt on restart from leader)
   - Followers catch up automatically after restart

### Auto-Forwarding Implementation

When a follower receives a write request:
```python
if self.raft.get_state() != "LEADER":
    leader = self.raft.get_leader()
    response = requests.post(leader_url, json=data)
    return response.json()
```

---

## 🎓 Assignment Coverage

- ✅ **Q3**: Leader election with 5 nodes
- ✅ **Q4**: Log replication for music queue operations
- ✅ **Q5**: Five automated test cases:
  1. Leader election verification
  2. Leader failure and re-election
  3. Log replication consistency
  4. Follower recovery (new node scenario)
  5. Consistency under concurrent operations

---

## 📞 Support

If you encounter issues:

1. Check Docker is running: `docker ps`
2. Verify no port conflicts: `lsof -i :8001`
3. Check logs: `docker logs raft-node-1`
4. Try clean restart: `docker-compose down -v && docker-compose up -d`
5. Ensure Python dependencies (for host tests): `pip3 install requests`

For the complete demo walkthrough, see `FINAL_DEMO_SCRIPT.md`.
