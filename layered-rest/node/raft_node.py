"""
Simplified Raft Consensus Algorithm Implementation
Implements leader election (Q3) and log replication (Q4)
"""

import threading
import time
import random
import grpc
from enum import Enum
from typing import List, Dict, Callable, Optional, Tuple
import json

# Import generated proto files
import proto.raft_pb2 as raft_pb2
import proto.raft_pb2_grpc as raft_pb2_grpc


class NodeState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"


class LogEntry:
    """Represents a log entry in the Raft log"""
    def __init__(self, term: int, index: int, operation: str, payload: dict):
        self.term = term
        self.index = index
        self.operation = operation
        self.payload = payload
    
    def to_proto(self):
        """Convert to protobuf message"""
        return raft_pb2.LogEntry(
            term=self.term,
            index=self.index,
            operation=self.operation,
            payload=json.dumps(self.payload)
        )
    
    @staticmethod
    def from_proto(proto_entry):
        """Create LogEntry from protobuf message"""
        return LogEntry(
            term=proto_entry.term,
            index=proto_entry.index,
            operation=proto_entry.operation,
            payload=json.loads(proto_entry.payload) if proto_entry.payload else {}
        )


class RaftNode:
    """
    Simplified Raft consensus node implementing:
    - Leader election with randomized timeouts
    - Log replication with majority consensus
    """
    
    def __init__(self, node_id: str, peers: List[str], apply_fn: Callable, get_last_applied_fn: Callable = None, set_last_applied_fn: Callable = None):
        self.node_id = node_id
        self.peers = peers  # List of peer addresses (e.g., ["node-2:50051", "node-3:50051"])
        self.apply_fn = apply_fn  # Function to apply committed log entries to state machine
        self.get_last_applied_fn = get_last_applied_fn  # Function to get last applied index from persistent storage
        self.set_last_applied_fn = set_last_applied_fn  # Function to save last applied index to persistent storage
        
        # Persistent state (should be saved to disk in production)
        self.current_term = 0
        self.voted_for = None
        self.log: List[LogEntry] = []  # Log entries (index starts at 1)
        
        # Volatile state on all servers
        self.commit_index = 0  # Index of highest log entry known to be committed
        self.last_applied = 0  # Index of highest log entry applied to state machine
        
        # Restore last_applied from persistent storage if available
        if self.get_last_applied_fn:
            try:
                self.last_applied = self.get_last_applied_fn()
                print(f"[RAFT] Node {self.node_id} restored last_applied = {self.last_applied}")
            except Exception as e:
                print(f"[RAFT] Node {self.node_id} could not restore last_applied: {e}")
        
        # Volatile state on leaders (reinitialized after election)
        self.next_index: Dict[str, int] = {}   # For each server, index of next log entry to send
        self.match_index: Dict[str, int] = {}  # For each server, index of highest log entry known to be replicated
        
        # State management
        self.state = NodeState.FOLLOWER
        self.leader_id = None
        self.votes_received = set()
        
        # Timing
        self.heartbeat_interval = 1.0  # 1 second heartbeat
        self.election_timeout = self._random_election_timeout()
        self.last_heartbeat = time.time()
        
        # Threading
        self.running = False
        self.lock = threading.Lock()
        self.election_thread = None
        self.heartbeat_thread = None
        
        print(f"[RAFT] Node {self.node_id} initialized with {len(self.peers)} peers")
        print(f"[RAFT] Election timeout: {self.election_timeout:.2f}s")
    
    def _random_election_timeout(self) -> float:
        """Generate random election timeout between 1.5 and 3 seconds"""
        return random.uniform(1.5, 3.0)
    
    def start(self):
        """Start the Raft node"""
        self.running = True
        self.last_heartbeat = time.time()
        
        # Start election timer thread
        self.election_thread = threading.Thread(target=self._election_timer, daemon=True)
        self.election_thread.start()
        
        print(f"[RAFT] Node {self.node_id} started in {self.state.value} state")
    
    def stop(self):
        """Stop the Raft node"""
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
        if self.election_thread:
            self.election_thread.join(timeout=2)
        print(f"[RAFT] Node {self.node_id} stopped")
    
    def _election_timer(self):
        """Monitor election timeout and trigger elections"""
        while self.running:
            time.sleep(0.1)  # Check every 100ms
            
            with self.lock:
                if self.state == NodeState.LEADER:
                    continue  # Leaders don't need election timeout
                
                elapsed = time.time() - self.last_heartbeat
                if elapsed >= self.election_timeout:
                    print(f"[RAFT] Node {self.node_id} election timeout ({self.election_timeout:.2f}s) - starting election")
                    self._start_election()
    
    def _start_election(self):
        """Transition to candidate and start election"""
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.votes_received = {self.node_id}
        self.last_heartbeat = time.time()
        self.election_timeout = self._random_election_timeout()
        
        term = self.current_term
        last_log_index = len(self.log)
        last_log_term = self.log[-1].term if self.log else 0
        
        print(f"[RAFT] Node {self.node_id} became CANDIDATE for term {term}")
        
        # Request votes from all peers
        for peer in self.peers:
            threading.Thread(
                target=self._request_vote,
                args=(peer, term, last_log_index, last_log_term),
                daemon=True
            ).start()
    
    def _request_vote(self, peer: str, term: int, last_log_index: int, last_log_term: int):
        """Send RequestVote RPC to a peer"""
        try:
            # Client-side log
            print(f"Node {self.node_id} sends RPC RequestVote to Node {peer}")
            
            channel = grpc.insecure_channel(peer)
            stub = raft_pb2_grpc.RaftServiceStub(channel)
            
            request = raft_pb2.VoteRequest(
                term=term,
                candidate_id=self.node_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term
            )
            
            response = stub.RequestVote(request, timeout=1.0)
            
            with self.lock:
                # Update term if we discover a higher term
                if response.term > self.current_term:
                    self.current_term = response.term
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                    print(f"[RAFT] Node {self.node_id} discovered higher term {response.term}, reverting to FOLLOWER")
                    return
                
                # Count vote if still candidate and in same term
                if self.state == NodeState.CANDIDATE and term == self.current_term and response.vote_granted:
                    self.votes_received.add(response.voter_id)
                    print(f"[RAFT] Node {self.node_id} received vote from {response.voter_id} ({len(self.votes_received)}/{len(self.peers) + 1})")
                    
                    # Check if we have majority
                    if len(self.votes_received) > (len(self.peers) + 1) // 2:
                        self._become_leader()
            
            channel.close()
        except Exception as e:
            print(f"[RAFT] Node {self.node_id} failed to request vote from {peer}: {e}")
    
    def _become_leader(self):
        """Transition to leader state"""
        if self.state != NodeState.CANDIDATE:
            return
        
        self.state = NodeState.LEADER
        self.leader_id = self.node_id
        
        # Initialize leader state
        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0
        
        print(f"[RAFT] Node {self.node_id} became LEADER for term {self.current_term}")
        
        # Start sending heartbeats
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=0.5)
        self.heartbeat_thread = threading.Thread(target=self._send_heartbeats, daemon=True)
        self.heartbeat_thread.start()
    
    def _send_heartbeats(self):
        """Send periodic heartbeats (empty AppendEntries) to all followers"""
        while self.running and self.state == NodeState.LEADER:
            for peer in self.peers:
                threading.Thread(
                    target=self._send_append_entries,
                    args=(peer,),
                    daemon=True
                ).start()
            
            time.sleep(self.heartbeat_interval)
    
    def _send_append_entries(self, peer: str):
        """Send AppendEntries RPC to a follower"""
        try:
            with self.lock:
                if self.state != NodeState.LEADER:
                    return
                
                next_idx = self.next_index.get(peer, 1)
                prev_log_index = next_idx - 1
                prev_log_term = self.log[prev_log_index - 1].term if prev_log_index > 0 and prev_log_index <= len(self.log) else 0
                
                # Get entries to send
                entries = []
                if next_idx <= len(self.log):
                    entries = [self.log[i].to_proto() for i in range(next_idx - 1, len(self.log))]
                
                term = self.current_term
                leader_commit = self.commit_index
            
            # Client-side log
            rpc_name = "AppendEntries(heartbeat)" if not entries else f"AppendEntries({len(entries)} entries)"
            print(f"Node {self.node_id} sends RPC {rpc_name} to Node {peer}")
            
            channel = grpc.insecure_channel(peer)
            stub = raft_pb2_grpc.RaftServiceStub(channel)
            
            request = raft_pb2.AppendEntriesRequest(
                term=term,
                leader_id=self.node_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=entries,
                leader_commit=leader_commit
            )
            
            response = stub.AppendEntries(request, timeout=1.0)
            
            with self.lock:
                # Update term if we discover a higher term
                if response.term > self.current_term:
                    self.current_term = response.term
                    self.state = NodeState.FOLLOWER
                    self.voted_for = None
                    self.leader_id = None
                    print(f"[RAFT] Node {self.node_id} discovered higher term {response.term}, stepping down from LEADER")
                    return
                
                if self.state == NodeState.LEADER and term == self.current_term:
                    if response.success:
                        # Update next_index and match_index
                        self.match_index[peer] = response.match_index
                        self.next_index[peer] = response.match_index + 1
                        
                        # Try to commit entries
                        self._try_commit()
                    else:
                        # Decrement next_index and retry
                        self.next_index[peer] = max(1, self.next_index[peer] - 1)
            
            channel.close()
        except Exception as e:
            pass  # Silent failure for heartbeats
    
    def _try_commit(self):
        """Try to commit log entries if majority has replicated them"""
        if self.state != NodeState.LEADER:
            return
        
        # Find highest index replicated on majority
        for n in range(len(self.log), self.commit_index, -1):
            if self.log[n - 1].term == self.current_term:
                # Count replicas
                replicas = 1  # Leader has it
                for peer in self.peers:
                    if self.match_index.get(peer, 0) >= n:
                        replicas += 1
                
                # If majority, commit
                if replicas > (len(self.peers) + 1) // 2:
                    self.commit_index = n
                    print(f"[RAFT] Node {self.node_id} committed entries up to index {n}")
                    self._apply_committed()
                    break
    
    def _apply_committed(self):
        """Apply committed log entries to state machine"""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied - 1]
            print(f"[RAFT] Node {self.node_id} applying entry {self.last_applied}: {entry.operation}")
            try:
                self.apply_fn(entry.operation, entry.payload)
                # Persist last_applied after successful application
                if self.set_last_applied_fn:
                    self.set_last_applied_fn(self.last_applied)
            except Exception as e:
                print(f"[RAFT] Node {self.node_id} failed to apply entry {self.last_applied}: {e}")
    
    def submit_operation(self, operation: str, payload: dict, timeout: float = 10.0) -> bool:
        """
        Submit an operation to the Raft log.
        Returns True if operation was committed, False otherwise.
        """
        with self.lock:
            if self.state != NodeState.LEADER:
                return False
            
            # Append to log
            entry = LogEntry(
                term=self.current_term,
                index=len(self.log) + 1,
                operation=operation,
                payload=payload
            )
            self.log.append(entry)
            
            entry_index = entry.index
            print(f"[RAFT] Node {self.node_id} appended entry {entry_index}: {operation}")
        
        # Wait for commit
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self.lock:
                if self.commit_index >= entry_index:
                    return True
                if self.state != NodeState.LEADER:
                    return False
            time.sleep(0.1)
        
        return False
    
    def is_leader(self) -> bool:
        """Check if this node is the leader"""
        with self.lock:
            return self.state == NodeState.LEADER
    
    def get_leader(self) -> Optional[str]:
        """Get the current leader ID"""
        with self.lock:
            return self.leader_id


class RaftServiceServicer(raft_pb2_grpc.RaftServiceServicer):
    """gRPC service implementation for Raft RPCs"""
    
    def __init__(self, raft_node: RaftNode):
        self.raft = raft_node
    
    def RequestVote(self, request, context):
        """Handle RequestVote RPC"""
        # Server-side log
        print(f"Node {self.raft.node_id} runs RPC RequestVote called by Node {request.candidate_id}")
        
        with self.raft.lock:
            vote_granted = False
            
            # Update term if we discover a higher term
            if request.term > self.raft.current_term:
                self.raft.current_term = request.term
                self.raft.state = NodeState.FOLLOWER
                self.raft.voted_for = None
                self.raft.leader_id = None
            
            # Grant vote if:
            # 1. Haven't voted in this term, or already voted for this candidate
            # 2. Candidate's log is at least as up-to-date as ours
            if request.term == self.raft.current_term:
                if self.raft.voted_for is None or self.raft.voted_for == request.candidate_id:
                    # Check log is up-to-date
                    our_last_log_index = len(self.raft.log)
                    our_last_log_term = self.raft.log[-1].term if self.raft.log else 0
                    
                    log_ok = (request.last_log_term > our_last_log_term or
                              (request.last_log_term == our_last_log_term and 
                               request.last_log_index >= our_last_log_index))
                    
                    if log_ok:
                        vote_granted = True
                        self.raft.voted_for = request.candidate_id
                        self.raft.last_heartbeat = time.time()  # Reset election timeout
                        print(f"[RAFT] Node {self.raft.node_id} granted vote to {request.candidate_id} for term {request.term}")
        
        return raft_pb2.VoteResponse(
            term=self.raft.current_term,
            vote_granted=vote_granted,
            voter_id=self.raft.node_id
        )
    
    def AppendEntries(self, request, context):
        """Handle AppendEntries RPC (heartbeat and log replication)"""
        # Server-side log
        rpc_name = "AppendEntries(heartbeat)" if not request.entries else f"AppendEntries({len(request.entries)} entries)"
        print(f"Node {self.raft.node_id} runs RPC {rpc_name} called by Node {request.leader_id}")
        
        with self.raft.lock:
            success = False
            match_index = 0
            
            # Update term if we discover a higher term
            if request.term > self.raft.current_term:
                self.raft.current_term = request.term
                self.raft.state = NodeState.FOLLOWER
                self.raft.voted_for = None
            
            # Accept heartbeat/entries if term is current
            if request.term == self.raft.current_term:
                self.raft.state = NodeState.FOLLOWER
                self.raft.leader_id = request.leader_id
                self.raft.last_heartbeat = time.time()  # Reset election timeout
                
                # Check if log contains entry at prev_log_index with prev_log_term
                if request.prev_log_index == 0 or \
                   (request.prev_log_index <= len(self.raft.log) and 
                    self.raft.log[request.prev_log_index - 1].term == request.prev_log_term):
                    
                    success = True
                    
                    # Delete conflicting entries and append new ones
                    if request.entries:
                        # Find where to insert
                        insert_idx = request.prev_log_index
                        new_entries_appended = 0
                        
                        for i, entry_proto in enumerate(request.entries):
                            idx = insert_idx + i + 1
                            entry = LogEntry.from_proto(entry_proto)
                            
                            # If existing entry conflicts, delete it and all following
                            if idx <= len(self.raft.log):
                                if self.raft.log[idx - 1].term != entry.term:
                                    # Conflict: delete this and all following entries
                                    self.raft.log = self.raft.log[:idx - 1]
                                    self.raft.log.append(entry)
                                    new_entries_appended += 1
                                # else: entry already exists with same term, skip it
                            else:
                                # Append new entry beyond current log
                                self.raft.log.append(entry)
                                new_entries_appended += 1
                        
                        if new_entries_appended > 0:
                            print(f"[RAFT] Node {self.raft.node_id} replicated {new_entries_appended} entries, log size now {len(self.raft.log)}")
                    
                    match_index = len(self.raft.log)
                    
                    # Update commit index
                    if request.leader_commit > self.raft.commit_index:
                        self.raft.commit_index = min(request.leader_commit, len(self.raft.log))
                        self.raft._apply_committed()
        
        return raft_pb2.AppendEntriesResponse(
            term=self.raft.current_term,
            success=success,
            follower_id=self.raft.node_id,
            match_index=match_index
        )
