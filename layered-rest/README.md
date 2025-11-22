# Distributed Music Queue System with Two-Phase Commit (2PC)

A distributed music queue system implementing the **Two-Phase Commit (2PC)** protocol to ensure consistency across multiple replicated nodes. This project demonstrates distributed transaction coordination, consensus algorithms, and fault-tolerant data replication.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Two-Phase Commit Protocol](#two-phase-commit-protocol)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Implementation Details](#implementation-details)
- [Logs and Monitoring](#logs-and-monitoring)

---

## Overview

This system implements a **distributed music queue** where multiple nodes maintain separate Redis database replicas. All write operations (adding tracks, voting, removing tracks) use the **Two-Phase Commit protocol** to ensure atomic, consistent updates across all replicas.

### Key Characteristics

- **5 replicated nodes**, each with its own Redis database
- **Nginx load balancer** distributing requests across nodes
- **2PC protocol** ensuring ACID properties for distributed transactions
- **gRPC** for inter-node communication (port 50051)
- **FastAPI** for REST API (port 8000 per node, port 8080 via nginx)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Nginx Load Balancer                   │
│                      (Port 8080)                         │
└────────────────┬────────────────────────────────────────┘
                 │
     ┌───────────┼───────────┬──────────┬──────────┐
     │           │           │          │          │
┌────▼───┐  ┌───▼────┐  ┌───▼────┐ ┌──▼─────┐ ┌──▼─────┐
│ Node 1 │  │ Node 2 │  │ Node 3 │ │ Node 4 │ │ Node 5 │
│ :8000  │  │ :8000  │  │ :8000  │ │ :8000  │ │ :8000  │
│ :50051 │  │ :50051 │  │ :50051 │ │ :50051 │ │ :50051 │
└───┬────┘  └───┬────┘  └───┬────┘ └───┬────┘ └───┬────┘
    │           │           │          │          │
┌───▼────┐  ┌───▼────┐  ┌───▼────┐ ┌──▼─────┐ ┌──▼─────┐
│Redis-1 │  │Redis-2 │  │Redis-3 │ │Redis-4 │ │Redis-5 │
│  :6379 │  │  :6379 │  │  :6379 │ │  :6379 │ │  :6379 │
└────────┘  └────────┘  └────────┘ └────────┘ └────────┘
```

### Components

- **Nodes (1-5)**: Python FastAPI services handling REST requests and participating in 2PC
- **Redis (1-5)**: Separate database replicas for each node
- **Nginx**: Load balancer routing HTTP traffic to available nodes
- **gRPC**: Inter-node communication for 2PC protocol

---

## Two-Phase Commit Protocol

The system implements the classic 2PC algorithm with two phases:

### Phase 1: Voting Phase

1. **Coordinator** receives a write request (e.g., add track)
2. **Coordinator** sends `RequestVote` RPC to all **Participants**
3. Each **Participant**:
   - Validates the operation locally
   - Responds with `VoteCommit` (Yes) or `VoteAbort` (No)
   - Stores transaction state in pending list

### Phase 2: Decision Phase

4. **Coordinator** collects all votes:
   - If **all participants vote commit**: Decision = `GlobalCommit`
   - If **any participant votes abort**: Decision = `GlobalAbort`
5. **Coordinator** commits to its local replica (if GlobalCommit)
6. **Coordinator** sends `SendDecision` RPC to all **Participants**
7. Each **Participant**:
   - Commits to local replica (if GlobalCommit)
   - Or aborts transaction (if GlobalAbort)
   - Sends `DecisionAck` back to Coordinator
8. Transaction complete

### 2PC Guarantees

- **Atomicity**: All nodes commit or all nodes abort
- **Consistency**: All replicas converge to the same state
- **Isolation**: Pending transactions don't affect reads
- **Durability**: Committed data persists in Redis

---

## Features

### Music Queue Operations

- **Add Track**: Add a new song to the queue with metadata (ID, title, artist, duration, votes)
- **Remove Track**: Remove a track by ID
- **Vote for Track**: Upvote or downvote tracks (affects queue ordering)
- **Play Next**: Move the top track from queue to history
- **View Queue**: Get current queue (sorted by votes, descending)
- **View History**: Get play history
- **Get Metadata**: Retrieve detailed track information

### 2PC Operations

- **RequestVote**: Voting phase RPC (Coordinator → Participants)
- **SendDecision**: Decision phase RPC (Coordinator → Participants)
- **Transaction Validation**: Pre-commit validation (duplicate checks, existence checks)
- **Transaction Logging**: Detailed RPC logs for debugging and analysis

---

## Prerequisites

- **Docker** (20.10+)
- **Docker Compose** (1.29+)
- **Python** 3.11+ (for local development)

---

## Installation & Setup

### 1. Clone the Repository

```bash
cd layered-rest
```

### 2. Build and Start Services

```bash
docker-compose up --build
```

This command will:
- Build 5 node containers
- Start 5 Redis replicas
- Start Nginx load balancer
- Initialize gRPC servers on each node

### 3. Verify System is Running

```bash
# Check node health
curl http://localhost:8080/queue

# Expected: []
```

### 4. Stop Services

```bash
docker-compose down
```

---

## API Endpoints

Base URL: `http://localhost:8080` (via Nginx load balancer)

### 1. Add Track

```bash
POST /add_track
Content-Type: application/json

{
  "id": 1,
  "title": "Bohemian Rhapsody",
  "artist": "Queen",
  "duration": 354,
  "votes": 0
}
```

**Response:**
```json
{
  "message": "Transaction <uuid> committed successfully",
  "queue": [...]
}
```

### 2. Remove Track

```bash
POST /remove_track
Content-Type: application/json

{
  "id": 1
}
```

### 3. Vote for Track

```bash
POST /vote?up=true
Content-Type: application/json

{
  "id": 1
}
```

Parameters:
- `up=true`: Upvote (default)
- `up=false`: Downvote

### 4. Get Queue

```bash
GET /queue
```

Returns array of tracks sorted by votes (descending).

### 5. Play Next

```bash
POST /play_next
```

Moves the top track to history.

### 6. Get History

```bash
GET /history
```

Returns array of played tracks.

### 7. Get Track Metadata

```bash
GET /metadata/{track_id}
```

Example: `GET /metadata/1`

### 8. Clear All (Test Utility)

```bash
POST /clear
```

Clears queue and history across all replicas.

---

## Testing

### Automated Test Suite

The project includes 5 comprehensive test cases validating 2PC behavior:

```bash
# Run all tests
docker-compose run --rm test-runner
```

### Test Cases

1. **test_add_remove.py**: Add and remove tracks using 2PC
2. **test_vote.py**: Vote operations with consensus
3. **test_sync.py**: Replica synchronization verification
4. **test_metadata.py**: Metadata retrieval and consistency
5. **test_history.py**: History tracking across transactions

### Manual Testing

```bash
# Add a track to node 1
curl -X POST http://localhost:8001/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "title": "Test Song", "artist": "Artist", "duration": 200, "votes": 5}'

# Verify it appears on node 2
curl http://localhost:8002/queue

# Should show the same track (2PC committed to all replicas)
```

---

## Project Structure

```
layered-rest/
├── docker-compose.yml          # Service orchestration
├── nginx.conf                  # Load balancer configuration
├── README.md                   # This file
│
├── node/
│   ├── Dockerfile              # Node container image
│   ├── entrypoint.sh           # Container startup script
│   ├── main.py                 # FastAPI application
│   ├── twopc_service.py        # 2PC coordinator and participant logic
│   ├── requirements.txt        # Python dependencies
│   ├── test-runner.sh          # Test execution script
│   └── proto/
│       └── twopc.proto         # gRPC service definition
│
├── proto/
│   └── twopc.proto             # Proto file for compilation
│
└── tests/
    ├── run_all_tests.py        # Test suite runner
    ├── test_add_remove.py      # Add/remove operations test
    ├── test_vote.py            # Voting test
    ├── test_sync.py            # Synchronization test
    ├── test_metadata.py        # Metadata test
    └── test_history.py         # History test
```

---

## Implementation Details

### main.py

- **FastAPI REST API**: Exposes HTTP endpoints for music queue operations
- **Redis Integration**: Each node connects to its own Redis replica (`redis-1` through `redis-5`)
- **2PC Coordinator**: Initiates 2PC transactions for write operations
- **gRPC Server**: Runs on port 50051 for participant role in 2PC

### twopc_service.py

#### TwoPhaseCommitServicer (Participant)

- Implements gRPC service for receiving coordinator requests
- `RequestVote`: Validates transactions and returns vote
- `SendDecision`: Commits or aborts based on global decision
- Maintains pending transaction state

#### TwoPhaseCommitCoordinator

- Initiates 2PC protocol for write operations
- `execute_2pc()`: Main entry point for coordinated transactions
- `_voting_phase()`: Collects votes from all participants
- `_decision_phase()`: Distributes global decision

### Validation Logic

```python
def validate_operation(operation: str, payload: dict) -> bool:
    """
    Pre-commit validation:
    - add_track: Check for duplicates
    - remove_track: Verify track exists
    - vote: Verify track exists
    - play_next: Verify queue is not empty
    - clear: Always allowed
    """
```

### Commit Logic

```python
def commit_operation(operation: str, payload: dict):
    """
    Atomic commit to local Redis replica:
    - add_track: Append to queue and sort
    - remove_track: Remove from queue
    - vote: Update votes and re-sort
    - play_next: Move from queue to history
    - clear: Delete all data
    """
```

---

## Logs and Monitoring

### 2PC Logging Format

The system produces detailed logs for each RPC call:

**Voting Phase (Client-side):**
```
Phase VOTING of Node <coordinator> sends RPC RequestVote to Phase VOTING of Node <peer>
Phase VOTING of Node <coordinator> receives RPC VoteResponse(COMMIT/ABORT) from Phase VOTING of Node <peer>
```

**Voting Phase (Server-side):**
```
Phase VOTING of Node <participant> receives RPC RequestVote from Phase VOTING of Node <coordinator>
Phase VOTING of Node <participant> sends RPC VoteResponse(COMMIT/ABORT) to Phase VOTING of Node <coordinator>
```

**Decision Phase (Client-side):**
```
Phase DECISION of Node <coordinator> sends RPC SendDecision(GlobalCommit/GlobalAbort) to Phase DECISION of Node <peer>
Phase DECISION of Node <coordinator> receives RPC DecisionAck from Phase DECISION of Node <peer>
```

**Decision Phase (Server-side):**
```
Phase DECISION of Node <participant> receives RPC SendDecision(GlobalCommit/GlobalAbort) from Phase DECISION of Node <coordinator>
Phase DECISION of Node <participant> committed transaction <tx_id> to local replica
Phase DECISION of Node <participant> sends RPC DecisionAck to Phase DECISION of Node <coordinator>
```

### View Live Logs

```bash
# All services
docker-compose logs -f

# Specific node
docker-compose logs -f node

# Nginx access logs
docker-compose logs -f nginx
```

---

## Example Workflow

### Adding a Track with 2PC

1. **Client** sends `POST /add_track` to `http://localhost:8080/add_track`
2. **Nginx** routes to random node (e.g., Node 3)
3. **Node 3** (Coordinator):
   - Generates transaction ID
   - Sends `RequestVote` to Nodes 1, 2, 4, 5 via gRPC
4. **Each Participant** (Nodes 1, 2, 4, 5):
   - Validates: "Track ID 1 doesn't exist in queue? Yes"
   - Responds: `VoteCommit`
5. **Node 3** (Coordinator):
   - Receives 4 commits → Decision = `GlobalCommit`
   - Commits to its Redis replica (redis-3)
   - Sends `SendDecision(GlobalCommit)` to all participants
6. **Each Participant**:
   - Commits to local replica (redis-1, redis-2, redis-4, redis-5)
   - Sends `DecisionAck`
7. **Node 3** returns success to client

Result: Track is atomically added to all 5 replicas.

---

## Troubleshooting

### Service won't start

```bash
# Check for port conflicts
lsof -i :8080
lsof -i :50051

# Rebuild containers
docker-compose down
docker-compose up --build
```

### Redis connection errors

```bash
# Check Redis containers
docker-compose ps

# Restart Redis
docker-compose restart redis-1 redis-2 redis-3 redis-4 redis-5
```

### 2PC transactions failing

Check logs for voting phase issues:
```bash
docker-compose logs | grep "VOTING"
```

Common issues:
- Network partition between nodes
- Validation failure (duplicate track, non-existent track)
- gRPC timeout (>5 seconds)

---

## Performance Considerations

- **Latency**: 2PC adds overhead due to 2 round-trips (voting + decision)
- **Scalability**: Coordinator contacts all N participants (O(N) complexity)
- **Blocking**: Participants block during voting phase
- **Timeout**: 5-second gRPC timeout for vote requests

---

## Future Enhancements

- **Three-Phase Commit (3PC)**: Non-blocking variant of 2PC
- **Paxos/Raft**: Fault-tolerant consensus for coordinator election
- **Persistent logs**: Write-ahead logs for crash recovery
- **Async replication**: Eventual consistency mode for reads

---

## License

This project is for educational purposes as part of CSE 5306 Distributed Systems coursework.

---

## Contributors

- **Project**: Distributed Systems PA3
- **Implementation**: Two-Phase Commit Protocol with gRPC and Redis

---

## References

- [Two-Phase Commit Protocol](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)
- [gRPC Documentation](https://grpc.io/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Redis Documentation](https://redis.io/documentation)
