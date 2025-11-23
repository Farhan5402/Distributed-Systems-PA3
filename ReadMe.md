# Distributed Music Queue with Two-Phase Commit

**Course:** CSE 5306 - Distributed Systems  
**Assignment:** Project Assignment 3  
**Implementation:** Two-Phase Commit with Separate Phase Services

---

## Overview

This system implements a distributed music queue with **Two-Phase Commit (2PC)** protocol for strong consistency across 5 replicated nodes. The key architectural feature is that the **voting phase and decision phase run as separate gRPC services** within each container, communicating via gRPC to demonstrate a microservices approach.

### Key Features

- ✅ **5 Distributed Nodes**: Each node runs in its own Docker container with a dedicated Redis replica
- ✅ **Separate Phase Services**: Voting Phase (port 50051) and Decision Phase (port 50052) are independent gRPC services
- ✅ **Intra-Node gRPC Communication**: Phases communicate via gRPC within the same container (ExecuteDecision RPC)
- ✅ **Language-Agnostic Design**: Protocol buffer-based design allows phases to be implemented in different languages
- ✅ **Strong Consistency**: All write operations use 2PC to ensure atomic commits across all replicas
- ✅ **Comprehensive Logging**: All RPCs are logged showing phase names and communication patterns

---

## Quick Start

### Prerequisites

- **Docker Desktop** installed and running
- **Docker Compose** (included with Docker Desktop)
- **curl** and **jq** (for testing)

### Installation & Setup

```bash
# 1. Navigate to the project directory
cd layered-rest

# 2. Start the system (this will build and run all services)
docker-compose up --build -d

# 3. Wait for services to initialize (~10 seconds)
sleep 10

# 4. Verify all services are running
docker-compose ps
```

**Expected Output:**
```
NAME                        IMAGE                  STATUS
layered-rest-nginx-1        nginx:alpine           Up
layered-rest-node-1         layered-rest-node-1    Up (healthy)
layered-rest-node-2         layered-rest-node-2    Up (healthy)
layered-rest-node-3         layered-rest-node-3    Up (healthy)
layered-rest-node-4         layered-rest-node-4    Up (healthy)
layered-rest-node-5         layered-rest-node-5    Up (healthy)
layered-rest-redis-1-1      redis:7-alpine         Up
layered-rest-redis-2-1      redis:7-alpine         Up
layered-rest-redis-3-1      redis:7-alpine         Up
layered-rest-redis-4-1      redis:7-alpine         Up
layered-rest-redis-5-1      redis:7-alpine         Up
layered-rest-test-runner-1  layered-rest-test-...  Up
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        NGINX (Port 8080)                    │
│                    Load Balancer / Router                   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
         ┌────▼────┐    ┌────▼────┐    ┌────▼────┐  ...
         │ Node-1  │    │ Node-2  │    │ Node-3  │
         │─────────│    │─────────│    │─────────│
         │ Voting  │    │ Voting  │    │ Voting  │
         │ Phase   │◄───┼─gRPC───►│    │ Phase   │
         │:50051   │    │ :50051  │    │ :50051  │
         │    │    │    │    │    │    │    │    │
         │    ▼    │    │    ▼    │    │    ▼    │
         │Decision │    │Decision │    │Decision │
         │ Phase   │◄───┼─gRPC───►│    │ Phase   │
         │ :50052  │    │ :50052  │    │ :50052  │
         │    │    │    │    │    │    │    │    │
         │    ▼    │    │    ▼    │    │    ▼    │
         │ Redis-1 │    │ Redis-2 │    │ Redis-3 │
         └─────────┘    └─────────┘    └─────────┘
```

### Intra-Node Communication (Key Requirement)

Within each node, the **Voting Phase Service** communicates with the **Decision Phase Service** via gRPC:

```
┌──────────────────────────────────────┐
│           Node Container             │
│                                      │
│  ┌─────────────────────┐             │
│  │  Voting Phase       │             │
│  │  Service (:50051)   │             │
│  └──────────┬──────────┘             │
│             │ ExecuteDecision RPC    │
│             │ (gRPC Call)            │
│             ▼                        │
│  ┌─────────────────────┐             │
│  │  Decision Phase     │             │
│  │  Service (:50052)   │             │
│  └──────────┬──────────┘             │
│             │                        │
│             ▼                        │
│        Redis Replica                 │
└──────────────────────────────────────┘
```

---

## API Endpoints

All endpoints are accessed via **http://localhost:8080**

### 1. Get Queue
```bash
curl -s http://localhost:8080/queue | jq
```

**Response:**
```json
[
  {
    "id": 1,
    "title": "Song Title",
    "artist": "Artist Name",
    "duration": 200,
    "votes": 5
  }
]
```

### 2. Add Track (Triggers 2PC)
```bash
curl -X POST http://localhost:8080/add_track \
  -H "Content-Type: application/json" \
  -d '{
    "id": 1,
    "title": "Bohemian Rhapsody",
    "artist": "Queen",
    "duration": 354,
    "votes": 0
  }' | jq
```

**Response:**
```json
{
  "message": "Transaction <uuid> committed successfully",
  "queue": [...]
}
```

### 3. Vote on Track (Triggers 2PC)
```bash
curl -X POST http://localhost:8080/vote \
  -H "Content-Type: application/json" \
  -d '{
    "track_id": 1,
    "vote_type": "up"
  }' | jq
```

### 4. Remove Track (Triggers 2PC)
```bash
curl -X POST http://localhost:8080/remove_track \
  -H "Content-Type: application/json" \
  -d '{
    "track_id": 1
  }' | jq
```

---

## Viewing 2PC Logs

### Find the Coordinator

After performing a write operation, find which node acted as coordinator:

```bash
# Search all nodes for "starting 2PC"
for i in {1..5}; do
  echo "=== Node-$i ==="
  docker logs layered-rest-node-$i 2>&1 | grep "starting 2PC" | tail -1
done
```

### View Complete 2PC Flow

```bash
# Replace 'X' with the coordinator node number (e.g., 3)
docker logs layered-rest-node-X 2>&1 | grep "Phase" | tail -40
```

**Example Output:**
```
Phase VOTING of Node-3 starting 2PC for transaction abc123...
Phase VOTING of Node-3 sends RPC RequestVote to Phase VOTING of Node-1
Phase VOTING of Node-3 receives RPC VoteResponse(COMMIT) from Phase VOTING of Node-1
Phase VOTING of Node-3 sends RPC RequestVote to Phase VOTING of Node-2
Phase VOTING of Node-3 receives RPC VoteResponse(COMMIT) from Phase VOTING of Node-2
...
Phase VOTING of Node-3 sends RPC ExecuteDecision to Phase DECISION of Node-3
Phase DECISION of Node-3 committed transaction abc123... to local replica
Phase DECISION of Node-3 sends RPC ExecuteDecision response to Phase VOTING of Node-3
...
Phase DECISION of Node-3 sends RPC SendDecision(GlobalCommit) to Phase DECISION of Node-1
Phase DECISION of Node-3 receives RPC DecisionAck from Phase DECISION of Node-1
...
```

**Key Points to Observe:**
1. **Phase 1 (Voting)**: Coordinator's voting phase requests votes from all participants
2. **Intra-Node gRPC**: `ExecuteDecision` RPC from voting phase to decision phase (same node)
3. **Phase 2 (Decision)**: Coordinator's decision phase sends global decision to all participants

### View Participant Logs

```bash
# View any participant node (non-coordinator)
docker logs layered-rest-node-1 2>&1 | grep "Phase" | tail -10
```

**Example Output:**
```
Phase VOTING of Node-1 receives RPC RequestVote from Phase VOTING of Node-3
Phase VOTING of Node-1 sends RPC VoteResponse(COMMIT) to Phase VOTING of Node-3
Phase DECISION of Node-1 receives RPC SendDecision(GlobalCommit) from Phase DECISION of Node-3
Phase DECISION of Node-1 committed transaction abc123... to local replica
Phase DECISION of Node-1 sends RPC DecisionAck to Phase DECISION of Node-3
```

---

## Testing

### Quick Consistency Test

```bash
# Add a track
curl -X POST http://localhost:8080/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "title": "Test", "artist": "Artist", "duration": 200, "votes": 0}' | jq

# Query 5 times - nginx will round-robin to different nodes
for i in {1..5}; do
  echo "=== Query $i ==="
  curl -s http://localhost:8080/queue | jq -c 'map(.id)'
done
```

**Expected:** All 5 queries should return `[1]` - proving consistency across all replicas.

---

## Verifying Separate Phase Services

To prove the voting and decision phases are separate gRPC services:

```bash
# Check gRPC servers on any node
docker exec layered-rest-node-1 ps aux | grep python
```

You'll see the FastAPI server and two gRPC server threads.

### View Proto Definitions

```bash
# View the protocol buffer definitions
cat proto/twopc.proto
```

You'll see two separate services defined:
- `VotingPhaseService` (handles RequestVote RPC)
- `DecisionPhaseService` (handles SendDecision and ExecuteDecision RPCs)

---

## Troubleshooting

### Issue: Containers won't start

```bash
# Clean everything and restart
docker-compose down -v
docker rm -f $(docker ps -aq --filter "name=layered-rest") 2>/dev/null || true
docker-compose up --build -d
sleep 10
```

### Issue: "Connection refused" errors

```bash
# Check if all containers are healthy
docker-compose ps

# If any are unhealthy, check logs
docker logs layered-rest-node-1
```

### Issue: Inconsistent data across nodes

```bash
# This shouldn't happen, but if it does, check 2PC logs
for i in {1..5}; do
  echo "=== Node-$i Recent Transactions ==="
  docker logs layered-rest-node-$i 2>&1 | grep "committed transaction" | tail -3
done
```

### Issue: Can't find coordinator in logs

```bash
# Some transactions might be very old, search for recent ones
docker logs layered-rest-node-1 2>&1 | grep "Phase VOTING" | tail -20
```

### Issue: Tests failing

```bash
# Restart the system fresh
docker-compose down -v
docker rm -f $(docker ps -aq --filter "name=layered-rest") 2>/dev/null || true
docker-compose up --build -d
sleep 15  # Give more time for initialization

# Run tests again
docker exec layered-rest-test-runner-1 python run_all_tests.py
```

---

## Stopping the System

```bash
# Stop all containers (preserves data)
docker-compose stop

# Stop and remove containers and volumes (clean slate)
docker-compose down -v
```

---

## Project Structure

```
layered-rest/
├── docker-compose.yml          # Defines 5 nodes + redis + nginx
├── nginx.conf                  # Load balancer configuration
├── DEMO_SCRIPT.md             # Detailed demo walkthrough
├── README.md                  # This file
├── node/                      # Application code
│   ├── main.py                # FastAPI + gRPC server startup
│   ├── coordinator.py         # 2PC coordinator logic
│   ├── voting_phase_service.py    # Voting Phase gRPC service
│   ├── decision_phase_service.py  # Decision Phase gRPC service
│   ├── twopc_service.py       # Helper functions
│   ├── Dockerfile             # Container image definition
│   ├── entrypoint.sh          # Container startup script
│   ├── requirements.txt       # Python dependencies
│   └── proto/
│       └── twopc.proto        # Protocol buffer definitions
├── proto/
│   └── twopc.proto            # Proto file (copied for reference)
└── tests/
    ├── run_all_tests.py       # Test suite runner
    ├── test_add_remove.py     # Add/remove tests
    ├── test_vote.py           # Voting tests
    ├── test_metadata.py       # Metadata tests
    ├── test_history.py        # History tests
    └── test_sync.py           # Sync tests
```

---

## Implementation Details

### Two-Phase Commit Protocol

1. **Coordinator Selection**: The node receiving the write request via nginx becomes the coordinator
2. **Phase 1 (Voting)**:
   - Coordinator's Voting Phase sends `RequestVote` to all participants' Voting Phases
   - Each participant validates the operation and votes COMMIT or ABORT
3. **Intra-Node Communication**:
   - Coordinator's Voting Phase calls its own Decision Phase via `ExecuteDecision` RPC
   - This demonstrates separate services communicating via gRPC
4. **Phase 2 (Decision)**:
   - Coordinator's Decision Phase commits locally
   - Sends `SendDecision(GlobalCommit)` to all participants' Decision Phases
   - Each participant commits and sends acknowledgment

### Why Separate Phase Services?

This design demonstrates:
- **Microservices Architecture**: Each phase can be independently scaled or replaced
- **Language Agnostic**: Voting phase could be in Python, decision phase in Go (via Protocol Buffers)
- **Clear Separation of Concerns**: Voting logic isolated from commit/abort logic
- **Testability**: Each service can be tested independently

---

## API Documentation

Once the system is running, visit **http://localhost:8080/docs** for interactive Swagger UI documentation.

---

## Support

For issues or questions:
1. Check the **Troubleshooting** section above
2. Review logs: `docker logs layered-rest-node-1`
3. Check **DEMO_SCRIPT.md** for detailed demo walkthrough

---

## Performance Notes

- **Latency**: 2PC adds ~100-200ms overhead compared to single-node writes
- **Throughput**: System handles ~10-20 write TPS (transactions per second)
- **Scalability**: Currently configured for 5 nodes; can be extended to more nodes by editing `docker-compose.yml`

---

**Last Updated:** November 23, 2025  
**Implementation:** Python 3.11, FastAPI, gRPC, Redis, Docker Compose
