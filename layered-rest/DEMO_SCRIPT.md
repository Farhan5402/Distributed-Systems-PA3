# Two-Phase Commit Demo Script

**Course:** CSE 5306 - Distributed Systems  
**Demo Date:** November 23, 2025  
**System:** Distributed Music Queue with 2PC Separate Phase Services

---

## Pre-Demo Setup (Do this before the TA arrives)

### 1. Navigate to Project Directory
```bash
cd /Users/farhan121/code-uta/sem1/cse5306/Project\ Assignment\ 3/Distributed-Systems-PA3/layered-rest
```

### 2. Clean Start
```bash
# Stop any running containers and clean up
docker-compose down -v

# Force remove any lingering containers (if needed)
docker rm -f $(docker ps -aq --filter "name=layered-rest") 2>/dev/null || true

# Rebuild and start fresh
docker-compose up --build -d

# Wait for all services to be ready (about 10 seconds)
sleep 10
```

### 3. Verify All Services Are Running
```bash
# Check all 5 nodes are up
docker-compose ps

# Should show:
# - layered-rest-node-1 through layered-rest-node-5 (5 separate services)
# - layered-rest-redis-1-1 through layered-rest-redis-5-1 (5 redis instances)
# - layered-rest-nginx-1 (nginx load balancer)
# - layered-rest-test-runner-1 (test runner)

# Quick health check - all nodes should be running
docker ps --filter "name=layered-rest-node" --format "table {{.Names}}\t{{.Status}}"
```

---

## Demo Script (Present to TA)

### Introduction (30 seconds)

**Say:**
> "I've implemented a distributed music queue system using Two-Phase Commit protocol with a microservices architecture. The key feature is that the voting phase and decision phase run as **separate gRPC services** within each container, communicating via gRPC. This allows them to potentially be implemented in different programming languages. I have 5 nodes, each with its own Redis replica, and all write operations use 2PC to ensure strong consistency."

---

### Part 1: Show Initial State (1 minute)

#### Check Queue is Empty on All Nodes

```bash
# Check node 1
curl -s http://localhost:8080/queue | jq

# Should show: []
```

**Say:**
> "The queue is currently empty across all 5 replicas. Let me verify a couple more nodes to show they're synchronized."

```bash
# Check a few more nodes via round-robin (nginx routes randomly)
curl -s http://localhost:8080/queue | jq
curl -s http://localhost:8080/queue | jq
```

---

### Part 2: Add First Track - Show 2PC in Action (3 minutes)

**Say:**
> "Now I'll add a track. This will trigger the Two-Phase Commit protocol. The request will go to a random node (the coordinator), which will execute 2PC with all other nodes as participants."

#### Add Track ID 1

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

**Expected Response:**
```json
{
  "message": "Transaction <uuid> committed successfully",
  "queue": [
    {
      "id": 1,
      "title": "Bohemian Rhapsody",
      "artist": "Queen",
      "duration": 354,
      "votes": 0
    }
  ]
}
```

**Say:**
> "Success! The transaction committed. Now let me show you the logs to prove the 2PC protocol executed."

---

### Part 3: Show Coordinator Logs (2 minutes)

**Find which node was the coordinator:**

```bash
# Search all nodes for "starting 2PC" to find coordinator
for i in {1..5}; do
  echo "=== Checking Node-$i ==="
  docker logs layered-rest-node-$i 2>&1 | grep "starting 2PC" | tail -1
done
```

**Say:**
> "Let's say Node-3 was the coordinator. I'll show its logs now."

**Show Coordinator Logs:**

```bash
# Replace node-3 with whichever was coordinator
docker logs layered-rest-node-3 2>&1 | grep "Phase" | tail -30
```

**Expected Output (explain while scrolling):**

```
Phase VOTING of Node-3 starting 2PC for transaction <uuid>
Phase VOTING of Node-3 sends RPC RequestVote to Phase VOTING of Node-1
Phase VOTING of Node-3 receives RPC VoteResponse(COMMIT) from Phase VOTING of Node-1
Phase VOTING of Node-3 sends RPC RequestVote to Phase VOTING of Node-2
Phase VOTING of Node-3 receives RPC VoteResponse(COMMIT) from Phase VOTING of Node-2
Phase VOTING of Node-3 sends RPC RequestVote to Phase VOTING of Node-4
Phase VOTING of Node-3 receives RPC VoteResponse(COMMIT) from Phase VOTING of Node-4
Phase VOTING of Node-3 sends RPC RequestVote to Phase VOTING of Node-5
Phase VOTING of Node-3 receives RPC VoteResponse(COMMIT) from Phase VOTING of Node-5

Phase VOTING of Node-3 sends RPC ExecuteDecision to Phase DECISION of Node-3
Phase DECISION of Node-3 receives RPC ExecuteDecision from Phase VOTING of Node-3
Phase DECISION of Node-3 committed transaction <uuid> to local replica
Phase DECISION of Node-3 sends RPC ExecuteDecision response to Phase VOTING of Node-3

Phase DECISION of Node-3 sends RPC SendDecision(GlobalCommit) to Phase DECISION of Node-1
Phase DECISION of Node-3 receives RPC DecisionAck from Phase DECISION of Node-1
Phase DECISION of Node-3 sends RPC SendDecision(GlobalCommit) to Phase DECISION of Node-2
Phase DECISION of Node-3 receives RPC DecisionAck from Phase DECISION of Node-2
Phase DECISION of Node-3 sends RPC SendDecision(GlobalCommit) to Phase DECISION of Node-4
Phase DECISION of Node-3 receives RPC DecisionAck from Phase DECISION of Node-4
Phase DECISION of Node-3 sends RPC SendDecision(GlobalCommit) to Phase DECISION of Node-5
Phase DECISION of Node-3 receives RPC DecisionAck from Phase DECISION of Node-5
```

**Point out key details:**
> "Notice three important things:
> 1. **Phase 1 (Voting)**: Node-3's voting phase sends RequestVote to all other nodes' voting phases and receives COMMIT votes.
> 2. **Intra-Node Communication**: Node-3's voting phase calls its own decision phase via ExecuteDecision RPC - this is the key requirement from Q2, showing the phases communicate via gRPC within the same container.
> 3. **Phase 2 (Decision)**: Node-3's decision phase sends GlobalCommit to all participants' decision phases and gets acknowledgments."

---

### Part 4: Show Participant Logs (1 minute)

**Show Participant Logs (any node except coordinator):**

```bash
# Show Node-1 logs (assuming it was a participant)
docker logs layered-rest-node-1 2>&1 | grep "Phase" | tail -10
```

**Expected Output:**

```
Phase VOTING of Node-1 receives RPC RequestVote from Phase VOTING of Node-3
Phase VOTING of Node-1 sends RPC VoteResponse(COMMIT) to Phase VOTING of Node-3
Phase DECISION of Node-1 receives RPC SendDecision(GlobalCommit) from Phase DECISION of Node-3
Phase DECISION of Node-1 committed transaction <uuid> to local replica
Phase DECISION of Node-1 sends RPC DecisionAck to Phase DECISION of Node-3
```

**Say:**
> "From the participant's perspective, you can see it received a vote request from Node-3, voted COMMIT, then received the global commit decision and executed it on its local Redis replica."

---

### Part 5: Verify Consistency (1 minute)

**Check all nodes have the same data:**

```bash
# Query multiple times (nginx round-robins to different nodes)
echo "=== Query 1 ==="
curl -s http://localhost:8080/queue | jq -c 'map(.id)'

echo "=== Query 2 ==="
curl -s http://localhost:8080/queue | jq -c 'map(.id)'

echo "=== Query 3 ==="
curl -s http://localhost:8080/queue | jq -c 'map(.id)'

echo "=== Query 4 ==="
curl -s http://localhost:8080/queue | jq -c 'map(.id)'

echo "=== Query 5 ==="
curl -s http://localhost:8080/queue | jq -c 'map(.id)'
```

**Expected Output (all identical):**
```
[1]
[1]
[1]
[1]
[1]
```

**Say:**
> "All five queries hit different nodes (thanks to nginx load balancing), and they all return the same data. This demonstrates that 2PC successfully replicated the data across all 5 Redis instances."

---

### Part 6: Add Second Track (2 minutes)

**Say:**
> "Let me add another track to show the protocol works for multiple transactions."

```bash
curl -X POST http://localhost:8080/add_track \
  -H "Content-Type: application/json" \
  -d '{
    "id": 2,
    "title": "Stairway to Heaven",
    "artist": "Led Zeppelin",
    "duration": 482,
    "votes": 0
  }' | jq
```

**Expected Response:**
```json
{
  "message": "Transaction <uuid> committed successfully",
  "queue": [
    {
      "id": 1,
      "title": "Bohemian Rhapsody",
      "artist": "Queen",
      "duration": 354,
      "votes": 0
    },
    {
      "id": 2,
      "title": "Stairway to Heaven",
      "artist": "Led Zeppelin",
      "duration": 482,
      "votes": 0
    }
  ]
}
```

**Say:**
> "Great! Now we have two tracks in the queue."

---

### Part 7: Vote on a Track (2 minutes)

**Say:**
> "Now let me demonstrate voting, which also uses 2PC since it's a write operation."

```bash
curl -X POST http://localhost:8080/vote \
  -H "Content-Type: application/json" \
  -d '{
    "track_id": 2,
    "vote_type": "up"
  }' | jq
```

**Expected Response:**
```json
{
  "message": "Transaction <uuid> committed successfully",
  "queue": [
    {
      "id": 2,
      "title": "Stairway to Heaven",
      "artist": "Led Zeppelin",
      "duration": 482,
      "votes": 1
    },
    {
      "id": 1,
      "title": "Bohemian Rhapsody",
      "artist": "Queen",
      "duration": 354,
      "votes": 0
    }
  ]
}
```

**Say:**
> "Notice the vote count increased to 1, and the track moved to the top of the queue since we sort by votes. Let me show the logs for this transaction."

**Show recent logs:**

```bash
# Find coordinator for this vote transaction
docker logs $(docker ps -q --filter "name=layered-rest-node" | head -1) 2>&1 | grep "Phase" | tail -20
```

**Point out:**
> "You can see the same 2PC pattern: voting phase, intra-node ExecuteDecision, and decision phase. The protocol works identically for all write operations."

---

### Part 8: Show Final State (1 minute)

**Query the queue:**

```bash
curl -s http://localhost:8080/queue | jq
```

**Expected Output:**
```json
[
  {
    "id": 2,
    "title": "Stairway to Heaven",
    "artist": "Led Zeppelin",
    "duration": 482,
    "votes": 1
  },
  {
    "id": 1,
    "title": "Bohemian Rhapsody",
    "artist": "Queen",
    "duration": 354,
    "votes": 0
  }
]
```

**Say:**
> "Final state: two tracks, sorted by votes, consistently replicated across all 5 nodes."

---

## Summary for TA (30 seconds)

**Say:**
> "To summarize:
> 1. ✅ **Separate Phase Services**: Voting and decision phases are separate gRPC services
> 2. ✅ **Intra-Node gRPC**: Phases communicate via gRPC within the same container (ExecuteDecision RPC)
> 3. ✅ **Language-Agnostic**: Protocol buffer-based design supports different languages
> 4. ✅ **5+ Nodes**: System runs with 5 containerized nodes, each with separate Redis replica
> 5. ✅ **Strong Consistency**: 2PC ensures atomic commits across all replicas
> 6. ✅ **Full Logging**: All RPCs logged showing phase names and inter/intra-node communication
> 
> The logs clearly show the voting phase calling the decision phase via gRPC (ExecuteDecision), which satisfies the Q2 requirement for separate phase services communicating within the same node."

---

## Troubleshooting (If Something Goes Wrong)

### If containers aren't running:
```bash
docker-compose up --build -d
sleep 10
docker-compose ps
```

### If queue shows different data on different queries:
```bash
# This might happen if a transaction is in progress
# Wait a second and query again
sleep 2
curl -s http://localhost:8080/queue | jq
```

### If logs don't show Phase messages:
```bash
# Check all nodes
for i in {1..5}; do
  echo "=== Node-$i Logs ==="
  docker logs layered-rest-node-$i 2>&1 | grep "Phase" | tail -5
done
```

### To restart demo from scratch:
```bash
docker-compose down -v
docker rm -f $(docker ps -aq --filter "name=layered-rest") 2>/dev/null || true
docker-compose up --build -d
sleep 10
```

---

## Quick Reference Commands

```bash
# Add track
curl -X POST http://localhost:8080/add_track -H "Content-Type: application/json" \
  -d '{"id": 1, "title": "Song", "artist": "Artist", "duration": 200, "votes": 0}' | jq

# Vote on track
curl -X POST http://localhost:8080/vote -H "Content-Type: application/json" \
  -d '{"track_id": 1, "vote_type": "up"}' | jq

# Get queue
curl -s http://localhost:8080/queue | jq

# Show coordinator logs (find coordinator first)
for i in {1..5}; do echo "Node-$i:"; docker logs layered-rest-node-$i 2>&1 | grep "starting 2PC" | tail -1; done

# Show recent Phase logs from any node
docker logs layered-rest-node-1 2>&1 | grep "Phase" | tail -30

# Check services running
docker-compose ps

# Verify both gRPC servers
docker exec layered-rest-node-1 netstat -tuln | grep -E "50051|50052"
```

---

## Time Estimate

- **Setup**: 1 minute
- **Demo**: 10-12 minutes
- **Q&A**: 3-5 minutes
- **Total**: ~15 minutes

---

**Good luck with your demo! 🎵**
