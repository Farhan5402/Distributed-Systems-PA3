import grpc
from concurrent import futures
import json
import uuid
import os
from typing import List, Dict, Tuple
import sys
sys.path.insert(0, '/app/proto')
import twopc_pb2
import twopc_pb2_grpc


def get_node_id():
    """Get the current node's hostname as its ID."""
    return os.environ.get('HOSTNAME', 'unknown-node')


def get_grpc_peers():
    """Get list of peer nodes for 2PC gRPC communication."""
    peers = os.getenv("PEER_NODES", "")
    peer_list = [p.strip() for p in peers.split(",") if p.strip()]
    # Convert HTTP URLs to gRPC addresses (IP:port format)
    grpc_peers = []
    for peer in peer_list:
        # Extract IP from HTTP URL and use gRPC port
        if "http://" in peer:
            # Format is http://IP:8000, extract IP
            ip = peer.replace("http://", "").split(":")[0]
            grpc_peers.append(f"{ip}:50051")
        else:
            # Assume it's already an IP or hostname
            grpc_peers.append(f"{peer}:50051")
    return grpc_peers


class TwoPhaseCommitServicer(twopc_pb2_grpc.TwoPhaseCommitServiceServicer):
    """gRPC service implementing participant-side 2PC logic."""
    
    def __init__(self, validate_fn, commit_fn, abort_fn):
        """
        Initialize the 2PC participant.
        
        Args:
            validate_fn: Function to validate if transaction can be committed
            commit_fn: Function to commit the transaction
            abort_fn: Function to abort/rollback the transaction
        """
        self.validate_fn = validate_fn
        self.commit_fn = commit_fn
        self.abort_fn = abort_fn
        self.node_id = get_node_id()
        self.pending_transactions: Dict[str, Dict] = {}
    
    def RequestVote(self, request, context):
        """
        Participant receives VoteRequest from Coordinator.
        Validates the transaction and returns vote.
        """
        tx_id = request.transaction_id
        coordinator_id = request.coordinator_id
        operation = request.operation
        
        # Server-side log: Participant receives VoteRequest
        print(f"Phase VOTING of Node {self.node_id} receives RPC RequestVote from Phase VOTING of Node {coordinator_id}")
        
        try:
            payload = json.loads(request.payload)
            # Validate if this transaction can be committed
            can_commit = self.validate_fn(operation, payload)
            
            if can_commit:
                # Store transaction state for later commit/abort
                self.pending_transactions[tx_id] = {
                    'operation': operation,
                    'payload': payload,
                    'coordinator': coordinator_id
                }
                
                response = twopc_pb2.VoteResponse(
                    transaction_id=tx_id,
                    participant_id=self.node_id,
                    vote_commit=True,
                    reason="Transaction validated successfully"
                )
                
                # Server-side log: Participant sends VoteCommit
                print(f"Phase VOTING of Node {self.node_id} sends RPC VoteResponse(COMMIT) to Phase VOTING of Node {coordinator_id}")
            else:
                response = twopc_pb2.VoteResponse(
                    transaction_id=tx_id,
                    participant_id=self.node_id,
                    vote_commit=False,
                    reason="Validation failed"
                )
                
                # Server-side log: Participant sends VoteAbort
                print(f"Phase VOTING of Node {self.node_id} sends RPC VoteResponse(ABORT) to Phase VOTING of Node {coordinator_id}")
        
        except Exception as e:
            response = twopc_pb2.VoteResponse(
                transaction_id=tx_id,
                participant_id=self.node_id,
                vote_commit=False,
                reason=f"Error during validation: {str(e)}"
            )
            
            # Server-side log: Participant sends VoteAbort due to error
            print(f"Phase VOTING of Node {self.node_id} sends RPC VoteResponse(ABORT) to Phase VOTING of Node {coordinator_id}")
        
        return response
    
    def SendDecision(self, request, context):
        """
        Participant receives final decision from Coordinator.
        Each node has its own database replica. Participants commit to their
        local replica when they receive GlobalCommit.
        """
        tx_id = request.transaction_id
        coordinator_id = request.coordinator_id
        commit = request.commit
        
        # Server-side log: Participant receives GlobalDecision
        decision_type = "GlobalCommit" if commit else "GlobalAbort"
        print(f"Phase DECISION of Node {self.node_id} receives RPC SendDecision({decision_type}) from Phase DECISION of Node {coordinator_id}")
        
        success = False
        
        if tx_id in self.pending_transactions:
            tx_data = self.pending_transactions[tx_id]
            
            try:
                if commit:
                    # Commit to this node's local replica
                    self.commit_fn(tx_data['operation'], tx_data['payload'])
                    print(f"Phase DECISION of Node {self.node_id} committed transaction {tx_id} to local replica")
                    success = True
                else:
                    # Execute abort/cleanup
                    self.abort_fn(tx_data['operation'], tx_data['payload'])
                    print(f"Phase DECISION of Node {self.node_id} aborted transaction {tx_id}")
                    success = True
                
                # Clean up pending transaction
                del self.pending_transactions[tx_id]
                
            except Exception as e:
                print(f"Phase DECISION of Node {self.node_id} error processing decision for {tx_id}: {str(e)}")
                success = False
        else:
            # Transaction not found in pending list, but still acknowledge
            # This can happen if we're just a validator, not a holder of prepared state
            print(f"Phase DECISION of Node {self.node_id} transaction {tx_id} not in pending list")
            success = True
        
        # Server-side log: Participant sends DecisionAck
        print(f"Phase DECISION of Node {self.node_id} sends RPC DecisionAck to Phase DECISION of Node {coordinator_id}")
        
        return twopc_pb2.DecisionAck(
            transaction_id=tx_id,
            participant_id=self.node_id,
            success=success
        )


class TwoPhaseCommitCoordinator:
    """Coordinator-side 2PC logic."""
    
    def __init__(self):
        self.node_id = get_node_id()
    
    def execute_2pc(self, operation: str, payload: Dict) -> Tuple[bool, str]:
        """
        Execute 2PC protocol as coordinator.
        Each node has its own database replica. The coordinator commits locally,
        then instructs all participants to commit to their replicas.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        tx_id = str(uuid.uuid4())
        peers = get_grpc_peers()  # Gets other nodes (excluding self)
        
        print(f"Phase VOTING of Node {self.node_id} starting 2PC for transaction {tx_id}")
        
        # Phase 1: Voting Phase - get votes from all peer nodes
        votes = self._voting_phase(tx_id, operation, payload, peers)
        
        # Determine global decision based on peer votes
        all_commit = all(vote for vote in votes.values()) if votes else True
        
        if all_commit:
            # All peers voted to commit, now commit to coordinator's replica
            try:
                from main import commit_operation
                commit_operation(operation, payload)
                print(f"Phase DECISION of Node {self.node_id} committed transaction {tx_id} to local replica")
                
                # Inform all peers to commit to their replicas
                self._decision_phase(tx_id, True, peers)
                return True, f"Transaction {tx_id} committed successfully"
            except Exception as e:
                print(f"Phase DECISION of Node {self.node_id} error committing {tx_id}: {str(e)}")
                # Inform peers to abort
                self._decision_phase(tx_id, False, peers)
                return False, f"Transaction {tx_id} aborted due to commit error"
        else:
            # At least one peer voted to abort
            print(f"Phase DECISION of Node {self.node_id} aborting transaction {tx_id}")
            self._decision_phase(tx_id, False, peers)
            return False, f"Transaction {tx_id} aborted"
    
    def _voting_phase(self, tx_id: str, operation: str, payload: Dict, peers: List[str]) -> Dict[str, bool]:
        """
        Voting phase: Send VoteRequest to all participants.
        
        Returns:
            Dict mapping peer address to vote (True=Commit, False=Abort)
        """
        votes = {}
        vote_request = twopc_pb2.VoteRequest(
            transaction_id=tx_id,
            operation=operation,
            payload=json.dumps(payload),
            coordinator_id=self.node_id
        )
        
        for peer in peers:
            try:
                # Client-side log: Coordinator sends VoteRequest
                print(f"Phase VOTING of Node {self.node_id} sends RPC RequestVote to Phase VOTING of Node {peer}")
                
                channel = grpc.insecure_channel(peer)
                stub = twopc_pb2_grpc.TwoPhaseCommitServiceStub(channel)
                
                response = stub.RequestVote(vote_request, timeout=5)
                votes[peer] = response.vote_commit
                
                # Client-side log: Coordinator receives VoteResponse
                vote_type = "COMMIT" if response.vote_commit else "ABORT"
                print(f"Phase VOTING of Node {self.node_id} receives RPC VoteResponse({vote_type}) from Phase VOTING of Node {peer}")
                
                channel.close()
            
            except Exception as e:
                print(f"Phase VOTING of Node {self.node_id} error contacting {peer}: {str(e)}")
                votes[peer] = False  # Treat failure as abort vote
        
        return votes
    
    def _decision_phase(self, tx_id: str, commit: bool, peers: List[str]) -> bool:
        """
        Decision phase: Send GlobalCommit or GlobalAbort to all participants.
        
        Returns:
            True if all participants acknowledged, False otherwise
        """
        decision = twopc_pb2.GlobalDecision(
            transaction_id=tx_id,
            commit=commit,
            coordinator_id=self.node_id
        )
        
        decision_type = "GlobalCommit" if commit else "GlobalAbort"
        all_acked = True
        
        for peer in peers:
            try:
                # Client-side log: Coordinator sends GlobalDecision
                print(f"Phase DECISION of Node {self.node_id} sends RPC SendDecision({decision_type}) to Phase DECISION of Node {peer}")
                
                channel = grpc.insecure_channel(peer)
                stub = twopc_pb2_grpc.TwoPhaseCommitServiceStub(channel)
                
                response = stub.SendDecision(decision, timeout=5)
                
                # Client-side log: Coordinator receives DecisionAck
                print(f"Phase DECISION of Node {self.node_id} receives RPC DecisionAck from Phase DECISION of Node {peer}")
                
                if not response.success:
                    all_acked = False
                    print(f"Phase DECISION of Node {self.node_id} warning: {peer} failed to acknowledge decision")
                
                channel.close()
            
            except Exception as e:
                print(f"Phase DECISION of Node {self.node_id} error sending decision to {peer}: {str(e)}")
                all_acked = False
        
        return all_acked
