# Raft Implementation - TA Demo Script

**Student**: Farhan  
**Course**: CSE 5306 - Distributed Systems  
**Assignment**: PA3 - Raft Consensus Algorithm (Q3, Q4, Q5)

---

## Pre-Demo Setup (Do This First!)

```bash
cd layered-rest
docker-compose down -v
docker-compose up --build -d
sleep 10  # Wait for leader election
```

**Verify cluster is running**:
```bash
docker ps | grep raft-node
# Should show 5 nodes running
```

---

## Part 1: Leader Election Demo (Q3) - 3 minutes

### Show Initial Leader Election

**Check cluster status**:
```bash
for port in 8001 8002 8003 8004 8005; do
  echo "=== Node $port ==="
  curl -s http://localhost:$port/raft/status | jq '{node_id, state, term, leader}'
done
```

**Expected Output**: 1 LEADER, 4 FOLLOWERS, same term

**Show RPC Logging** (in docker logs):
```bash
docker logs raft-node-2 2>&1 | grep "RPC"
# Look for: "Node node-X sends RPC RequestVote to Node node-Y:50051"
# Look for: "Node node-X runs RPC RequestVote called by Node node-Y"
```

### Demonstrate Leader Failure & Re-election

**Step 1**: Identify and kill the leader
```bash
# Find leader
curl -s http://localhost:8001/raft/status | jq -r '.leader'

# Kill the leader (example: if node-3 is leader)
docker stop raft-node-3
```

**Step 2**: Wait for new election
```bash
sleep 5
```

**Step 3**: Verify new leader elected
```bash
for port in 8001 8002 8004 8005; do
  curl -s http://localhost:$port/raft/status | jq '{node_id, state, term, leader}'
done
```

**Expected**: New leader elected, term incremented (e.g., 1 → 2)

**Step 4**: Restart old leader
```bash
docker start raft-node-3
sleep 3
curl -s http://localhost:8003/raft/status | jq '{state, term, leader}'
```

**Expected**: Old leader rejoins as FOLLOWER with new term

---

## Part 2: Log Replication Demo (Q4) - 4 minutes

### Add Tracks and Show Replication

**Step 1**: Find current leader
```bash
LEADER=$(curl -s http://localhost:8001/raft/status | jq -r '.leader')
LEADER_PORT=$(echo $LEADER | sed 's/node-/800/')
echo "Leader is on port $LEADER_PORT"
```

**Step 2**: Add tracks to leader
```bash
curl -X POST http://localhost:$LEADER_PORT/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "title": "Bohemian Rhapsody", "artist": "Queen", "duration": 354, "votes": 0}'

curl -X POST http://localhost:$LEADER_PORT/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 2, "title": "Stairway to Heaven", "artist": "Led Zeppelin", "duration": 482, "votes": 0}'

curl -X POST http://localhost:$LEADER_PORT/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 3, "title": "Hotel California", "artist": "Eagles", "duration": 391, "votes": 0}'
```

**Step 3**: Verify replication across ALL nodes
```bash
for port in 8001 8002 8003 8004 8005; do
  echo "=== Node $port ==="
  curl -s http://localhost:$port/queue | jq 'map(.id)'
done
```

**Expected**: ALL nodes show `[1, 2, 3]` - Perfect consistency!

### Show RPC Logging for Log Replication

```bash
docker logs raft-node-2 2>&1 | grep "AppendEntries" | tail -10
# Look for: "Node node-X sends RPC AppendEntries(3 entries) to Node node-Y:50051"
# Look for: "Node node-X runs RPC AppendEntries(3 entries) called by Node node-Y"
```

### Demonstrate Request Forwarding (Non-Leader)

**Try to write to a follower**:
```bash
curl -v -X POST http://localhost:8001/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 4, "title": "Imagine", "artist": "John Lennon", "duration": 183, "votes": 0}' 2>&1 | grep -E "(307|X-Leader-Id)"
```

**Expected**: HTTP 307 with `X-Leader-Id` header showing redirect to leader

---

## Part 3: Follower Recovery Demo - 3 minutes

### Show Catch-Up Mechanism

**Step 1**: Stop a follower (not the leader!)
```bash
docker stop raft-node-1
echo "Node-1 is now offline"
```

**Step 2**: Add tracks while follower is down
```bash
curl -X POST http://localhost:$LEADER_PORT/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 10, "title": "Recovery Song 1", "artist": "Test Artist", "duration": 200, "votes": 0}'

curl -X POST http://localhost:$LEADER_PORT/add_track \
  -H "Content-Type: application/json" \
  -d '{"id": 11, "title": "Recovery Song 2", "artist": "Test Artist", "duration": 220, "votes": 0}'
```

**Step 3**: Check leader has new tracks
```bash
curl -s http://localhost:$LEADER_PORT/queue | jq 'map(.id)'
# Should show: [1, 2, 3, 10, 11]
```

**Step 4**: Restart follower
```bash
docker start raft-node-1
sleep 3
```

**Step 5**: Verify follower caught up
```bash
curl -s http://localhost:8001/queue | jq 'map(.id)'
# Should show: [1, 2, 3, 10, 11] - Same as leader!
```

**Show catch-up in logs**:
```bash
docker logs raft-node-1 2>&1 | grep "replicated.*entries" | tail -5
# Look for: "[RAFT] Node node-1 replicated X entries, log size now Y"
```

---

## Part 4: Test Suite Demo (Q5) - 2 minutes

### Run Automated Tests

**Test 1: Leader Election**:
```bash
docker exec raft-test-runner python3 /app/tests/test_raft_leader_election.py
```
**Expected**: `✓ Test PASSED: Exactly 1 leader, 4 followers`

**Test 2: Leader Failure** (requires host Docker access):
```bash
python3 tests/test_raft_leader_failure.py
```
**Expected**: `✓ Test PASSED: New leader elected after failure`

**Test 3: Log Replication**:
```bash
docker exec raft-test-runner python3 /app/tests/test_raft_log_replication.py
```
**Expected**: `✓ Test PASSED: All nodes have identical logs`

**Test 4: Follower Recovery** (requires host Docker access):
```bash
python3 tests/test_raft_follower_recovery.py
```
**Expected**: `✓ Test PASSED: Follower caught up successfully`

**Test 5: Consistency**:
```bash
docker exec raft-test-runner python3 /app/tests/test_raft_consistency.py
```
**Expected**: `✓ Test PASSED: All nodes consistent after concurrent ops`

---

## Key Points to Emphasize

### Q3: Leader Election Requirements ✅
- ✅ **Heartbeat timeout**: Exactly 1.0 second
- ✅ **Election timeout**: Random 1.5-3.0 seconds per node
- ✅ **All nodes start as FOLLOWER**
- ✅ **Automatic transition**: FOLLOWER → CANDIDATE → LEADER
- ✅ **RPC logging format**: Exactly as specified
  - Client: `Node node-X sends RPC RequestVote to Node node-Y:50051`
  - Server: `Node node-X runs RPC RequestVote called by Node node-Y`
- ✅ **5 containerized nodes** communicating via gRPC

### Q4: Log Replication Requirements ✅
- ✅ **Log structure**: Each entry has term, index, operation, payload
- ✅ **Leader receives** → appends → sends to followers
- ✅ **Followers replicate** → send ACK
- ✅ **Leader commits** on majority ACK
- ✅ **Leader applies** to state machine (Redis)
- ✅ **Followers apply** when leader_commit advances
- ✅ **RPC logging format**: Same as Q3 for AppendEntries
- ✅ **Request forwarding**: Non-leaders return HTTP 307 redirect
- ✅ **Same 5-node containerized setup**

### Q5: Testing Requirements ✅
- ✅ **5 different test cases** implemented and passing
- ✅ Tests cover: election, failure, replication, recovery, consistency
- ✅ Follower recovery = "new node entering" scenario
- ✅ All tests documented with execution screenshots

---

## Assignment Compliance Checklist

### Q3 Implementation ✅
- [x] gRPC proto file created (`proto/raft.proto`)
- [x] Heartbeat timeout = 1.0 second
- [x] Election timeout = random 1.5-3.0 seconds
- [x] All nodes start as FOLLOWER
- [x] Follower timeout → CANDIDATE transition
- [x] Candidate increments term, votes for self, sends RequestVote
- [x] Becomes leader on majority votes
- [x] Reverts to follower if loses or discovers higher term
- [x] RPC logging format matches specification exactly
- [x] 5 containerized nodes (raft-node-1 through raft-node-5)
- [x] gRPC communication on ports 50051-50055

### Q4 Implementation ✅
- [x] Extended proto file with AppendEntries & LogEntry
- [x] Log maintains committed + pending operations
- [x] Leader receives request, appends to log
- [x] Leader sends log to followers on heartbeat
- [x] Leader includes commit_index in AppendEntries
- [x] Followers copy log and ACK
- [x] Followers execute ops up to commit_index
- [x] Leader commits when majority ACK received
- [x] Leader increments commit_index
- [x] RPC logging format compliant
- [x] Non-leaders redirect to leader (HTTP 307)
- [x] Same 5-node containerized setup

### Q5 Implementation ✅
- [x] Test 1: Leader election
- [x] Test 2: Leader failure
- [x] Test 3: Log replication
- [x] Test 4: Follower recovery (new node scenario)
- [x] Test 5: Consistency under concurrent operations
- [x] All tests documented in report
- [x] Execution screenshots captured

---

## Quick Reference Commands

**Check cluster status**:
```bash
for port in 8001 8002 8003 8004 8005; do
  curl -s http://localhost:$port/raft/status | jq '{node_id, state, term, leader}'
done
```

**Find current leader**:
```bash
curl -s http://localhost:8001/raft/status | jq -r '.leader'
```

**Check queue on all nodes**:
```bash
for port in 8001 8002 8003 8004 8005; do
  echo "Node $port:"
  curl -s http://localhost:$port/queue | jq 'map(.id)'
done
```

**View logs for a specific node**:
```bash
docker logs raft-node-2 2>&1 | grep "RAFT" | tail -20
```

**View logs for a RPC communication**:
```bash
docker logs raft-node-2 2>&1 | grep "RPC" | tail -20
```

**Restart entire cluster**:
```bash
docker-compose down -v
docker-compose up --build -d
sleep 10
```

**Stop/Start individual node**:
```bash
docker stop raft-node-3
docker start raft-node-3
```

---

## Common TA Questions & Answers

**Q: Why 5 nodes?**  
A: Tolerates 2 node failures. Majority quorum is 3/5. System remains operational with any 3+ nodes.

**Q: What happens during network partition?**  
A: Minority partition cannot elect leader or commit operations. Only majority partition continues.

**Q: How do you prevent two leaders?**  
A: Each term has at most one leader - only one candidate can receive majority votes (3/5).

**Q: What if follower has conflicting log?**  
A: Leader overwrites conflicts using prev_log_index/term consistency check in AppendEntries.

**Q: Performance vs Two-Phase Commit?**  
A: Raft has higher latency (~100-200ms vs 50-100ms) but provides high availability and automatic failover. 2PC has single point of failure (coordinator).

**Q: How does heartbeat work?**  
A: Leader sends AppendEntries RPC every 1.0 second. Followers reset election timer on receipt. Empty entries = heartbeat, non-empty = log replication.

**Q: What's the election timeout range?**  
A: Each node picks random timeout between 1.5-3.0 seconds. Randomization prevents split votes.

**Q: How do you handle concurrent writes?**  
A: All writes go through leader. Leader serializes them in log, replicates to majority, then commits.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────┐
│           Raft Cluster (5 Nodes)                 │
│                                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ Node-1  │  │ Node-2  │  │ Node-3  │  ...    │
│  │FOLLOWER │  │ LEADER  │  │FOLLOWER │         │
│  │ :8001   │  │ :8002   │  │ :8003   │         │
│  │:50051   │  │:50052   │  │:50053   │         │
│  └────┬────┘  └────┬────┘  └────┬────┘         │
│       │            │            │               │
│       └────────────┴────────────┘               │
│         gRPC (RequestVote, AppendEntries)       │
│                                                  │
│  Each node:                                     │
│  - Maintains replicated log                     │
│  - Has dedicated Redis instance                 │
│  - Exposes HTTP API (FastAPI)                   │
│  - Communicates via gRPC                        │
└──────────────────────────────────────────────────┘

State Transitions:
FOLLOWER ──timeout──> CANDIDATE ──majority votes──> LEADER
    ↑                      │                            │
    └──────────────────────┴────────────────────────────┘
           (higher term discovered)
```

---

## Troubleshooting

**Issue**: No leader elected
```bash
docker-compose down -v
docker-compose up --build -d
sleep 10
```

**Issue**: Logs not replicating
```bash
# Check which node is leader
curl http://localhost:8001/raft/status | jq '.leader'
# Write to leader's port
```

**Issue**: Test failures
```bash
# Clean restart
docker-compose down -v
docker-compose up --build -d
sleep 10
# Run tests
```

**Issue**: Can't connect to port 80
```bash
# Nginx is on port 8080 (not 80)
curl http://localhost:8080/raft/status
```

---

## Demo Timeline (10 minutes)

| Time | Section | What to Show |
|------|---------|--------------|
| 0:00 | Setup | Start cluster, verify running |
| 0:30 | Q3 Part 1 | Show leader election, RPC logs |
| 2:00 | Q3 Part 2 | Kill leader, show re-election |
| 3:30 | Q4 Part 1 | Add tracks, show replication |
| 5:00 | Q4 Part 2 | Show request forwarding |
| 6:00 | Recovery | Stop follower, add data, restart, verify catch-up |
| 8:00 | Q5 | Run 2-3 automated tests |
| 9:30 | Wrap-up | Answer questions |

---

## Success Indicators

✅ **Visual Confirmations**:
- 1 leader, 4 followers in cluster status
- Same term across all nodes
- Identical queue IDs across all nodes
- RPC logs showing correct format
- Tests passing with green checkmarks

✅ **Functional Confirmations**:
- New leader elected within 3-5 seconds of failure
- Logs replicate to all nodes automatically
- Follower catches up after restart
- Non-leaders redirect to leader
- All 5 tests pass

---

**Ready to demo!** 🚀

Good luck with your presentation!
