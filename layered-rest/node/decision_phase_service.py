"""
Decision Phase Service - Runs as separate process on port 50052
Handles Phase 2 (Decision) of Two-Phase Commit protocol
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
from twopc_service import get_node_id, get_friendly_node_name


class DecisionPhaseServicer(twopc_pb2_grpc.DecisionPhaseServiceServicer):
    """Decision Phase Service - handles decision commands from coordinators."""
    
    def __init__(self, commit_fn, abort_fn, voting_servicer=None):
        self.commit_fn = commit_fn
        self.abort_fn = abort_fn
        self.voting_servicer = voting_servicer  # Reference to voting phase to get pending txs
        self.node_id = get_node_id()
        self.friendly_node_id = get_friendly_node_name(self.node_id)
    
    def SendDecision(self, request, context):
        """
        Participant receives final decision from Coordinator's Decision Phase.
        Commits or aborts the transaction locally.
        """
        tx_id = request.transaction_id
        coordinator_id = request.coordinator_id
        commit = request.commit
        
        # Server-side log: Participant receives GlobalDecision
        decision_type = "GlobalCommit" if commit else "GlobalAbort"
        coordinator_name = get_friendly_node_name(coordinator_id)
        print(f"Phase DECISION of {self.friendly_node_id} receives RPC SendDecision({decision_type}) from Phase DECISION of {coordinator_name}")
        
        success = False
        
        # Get transaction data from voting phase
        tx_data = None
        if self.voting_servicer:
            tx_data = self.voting_servicer.get_pending_transaction(tx_id)
        
        if tx_data:
            try:
                if commit:
                    # Commit to this node's local replica
                    self.commit_fn(tx_data['operation'], tx_data['payload'])
                    print(f"Phase DECISION of {self.friendly_node_id} committed transaction {tx_id} to local replica")
                    success = True
                else:
                    # Execute abort/cleanup
                    self.abort_fn(tx_data['operation'], tx_data['payload'])
                    print(f"Phase DECISION of {self.friendly_node_id} aborted transaction {tx_id}")
                    success = True
                
                # Clean up pending transaction in voting phase
                if self.voting_servicer:
                    self.voting_servicer.remove_pending_transaction(tx_id)
                
            except Exception as e:
                print(f"Phase DECISION of {self.friendly_node_id} error processing decision for {tx_id}: {str(e)}")
                success = False
        else:
            # Transaction not found in pending list
            print(f"Phase DECISION of {self.friendly_node_id} transaction {tx_id} not in pending list")
            success = True
        
        # Server-side log: Participant sends DecisionAck
        print(f"Phase DECISION of {self.friendly_node_id} sends RPC DecisionAck to Phase DECISION of {coordinator_name}")
        
        return twopc_pb2.DecisionAck(
            transaction_id=tx_id,
            participant_id=self.node_id,
            success=success
        )
    
    def ExecuteDecision(self, request, context):
        """
        Intra-node RPC: Voting Phase -> Decision Phase
        Coordinator's voting phase tells decision phase to make final decision.
        """
        tx_id = request.transaction_id
        all_voted_commit = request.all_voted_commit
        operation = request.operation
        payload_json = request.payload
        
        # Intra-node log
        print(f"Phase VOTING of {self.friendly_node_id} sends RPC ExecuteDecision to Phase DECISION of {self.friendly_node_id}")
        
        try:
            payload = json.loads(payload_json)
            
            if all_voted_commit:
                # All participants voted commit, so commit locally
                self.commit_fn(operation, payload)
                print(f"Phase DECISION of {self.friendly_node_id} committed transaction {tx_id} to local replica")
                
                response = twopc_pb2.DecisionCommand(
                    transaction_id=tx_id,
                    commit=True,
                    message=f"Transaction {tx_id} committed successfully"
                )
            else:
                # At least one participant voted abort
                self.abort_fn(operation, payload)
                print(f"Phase DECISION of {self.friendly_node_id} aborted transaction {tx_id}")
                
                response = twopc_pb2.DecisionCommand(
                    transaction_id=tx_id,
                    commit=False,
                    message=f"Transaction {tx_id} aborted"
                )
            
            # Intra-node log
            print(f"Phase DECISION of {self.friendly_node_id} sends RPC ExecuteDecision response to Phase VOTING of {self.friendly_node_id}")
            
            return response
            
        except Exception as e:
            print(f"Phase DECISION of {self.friendly_node_id} error executing decision: {str(e)}")
            return twopc_pb2.DecisionCommand(
                transaction_id=tx_id,
                commit=False,
                message=f"Error: {str(e)}"
            )


def start_decision_phase_server(commit_fn, abort_fn, voting_servicer=None):
    """Start the Decision Phase gRPC server on port 50052."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = DecisionPhaseServicer(commit_fn, abort_fn, voting_servicer)
    twopc_pb2_grpc.add_DecisionPhaseServiceServicer_to_server(servicer, server)
    server.add_insecure_port('[::]:50052')
    server.start()
    print("[Decision Phase] gRPC server started on port 50052")
    return server, servicer


if __name__ == "__main__":
    # For standalone testing
    def dummy_commit(operation, payload):
        print(f"COMMIT: {operation} - {payload}")
    
    def dummy_abort(operation, payload):
        print(f"ABORT: {operation} - {payload}")
    
    server, _ = start_decision_phase_server(dummy_commit, dummy_abort)
    server.wait_for_termination()
