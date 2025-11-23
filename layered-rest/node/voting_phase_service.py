"""
Voting Phase Service - Runs as separate process on port 50051
Handles Phase 1 (Voting) of Two-Phase Commit protocol
"""

import grpc
from concurrent import futures
import json
import os
import socket
import sys
sys.path.insert(0, '/app/proto')
import twopc_pb2
import twopc_pb2_grpc


# Import helper functions
from twopc_service import get_node_id, get_friendly_node_name, get_grpc_peers


class VotingPhaseServicer(twopc_pb2_grpc.VotingPhaseServiceServicer):
    """Voting Phase Service - handles voting requests from coordinators."""
    
    def __init__(self, validate_fn):
        self.validate_fn = validate_fn
        self.node_id = get_node_id()
        self.friendly_node_id = get_friendly_node_name(self.node_id)
        self.pending_transactions = {}
    
    def RequestVote(self, request, context):
        """
        Participant receives VoteRequest from Coordinator's Voting Phase.
        Validates the transaction and returns vote.
        """
        tx_id = request.transaction_id
        coordinator_id = request.coordinator_id
        operation = request.operation
        
        # Server-side log: Participant receives VoteRequest
        coordinator_name = get_friendly_node_name(coordinator_id)
        print(f"Phase VOTING of {self.friendly_node_id} receives RPC RequestVote from Phase VOTING of {coordinator_name}")
        
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
                print(f"Phase VOTING of {self.friendly_node_id} sends RPC VoteResponse(COMMIT) to Phase VOTING of {coordinator_name}")
            else:
                response = twopc_pb2.VoteResponse(
                    transaction_id=tx_id,
                    participant_id=self.node_id,
                    vote_commit=False,
                    reason="Validation failed"
                )
                
                # Server-side log: Participant sends VoteAbort
                print(f"Phase VOTING of {self.friendly_node_id} sends RPC VoteResponse(ABORT) to Phase VOTING of {coordinator_name}")
        
        except Exception as e:
            response = twopc_pb2.VoteResponse(
                transaction_id=tx_id,
                participant_id=self.node_id,
                vote_commit=False,
                reason=f"Error during validation: {str(e)}"
            )
            
            # Server-side log: Participant sends VoteAbort due to error
            coordinator_name = get_friendly_node_name(coordinator_id)
            print(f"Phase VOTING of {self.friendly_node_id} sends RPC VoteResponse(ABORT) to Phase VOTING of {coordinator_name}")
        
        return response
    
    def get_pending_transaction(self, tx_id):
        """Get pending transaction data."""
        return self.pending_transactions.get(tx_id)
    
    def remove_pending_transaction(self, tx_id):
        """Remove pending transaction."""
        if tx_id in self.pending_transactions:
            del self.pending_transactions[tx_id]


def start_voting_phase_server(validate_fn):
    """Start the Voting Phase gRPC server on port 50051."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = VotingPhaseServicer(validate_fn)
    twopc_pb2_grpc.add_VotingPhaseServiceServicer_to_server(servicer, server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("[Voting Phase] gRPC server started on port 50051")
    return server, servicer


if __name__ == "__main__":
    # For standalone testing
    def dummy_validate(operation, payload):
        return True
    
    server, _ = start_voting_phase_server(dummy_validate)
    server.wait_for_termination()
