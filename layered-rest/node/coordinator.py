"""
2PC Coordinator - Orchestrates both voting and decision phases via gRPC
Communicates with local voting/decision phases and remote nodes
"""

import grpc
import json
import uuid
import os
from typing import List, Dict, Tuple
import sys
sys.path.insert(0, '/app/proto')
import twopc_pb2
import twopc_pb2_grpc

from twopc_service import get_node_id, get_friendly_node_name, get_grpc_peers


class TwoPhaseCommitCoordinator:
    """Coordinator that uses gRPC to communicate with voting and decision phases."""
    
    def __init__(self):
        self.node_id = get_node_id()
        self.friendly_node_id = get_friendly_node_name(self.node_id)
    
    def execute_2pc(self, operation: str, payload: Dict) -> Tuple[bool, str]:
        """
        Execute 2PC protocol as coordinator using separate phase services.
        
        Flow:
        1. Coordinator's Voting Phase sends VoteRequest to all participants' Voting Phases
        2. Coordinator's Voting Phase receives VoteResponses
        3. Coordinator's Voting Phase calls local Decision Phase via gRPC (intra-node)
        4. Coordinator's Decision Phase sends GlobalDecision to all participants' Decision Phases
        5. Coordinator's Decision Phase receives DecisionAcks
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        tx_id = str(uuid.uuid4())
        peers = get_grpc_peers()  # Gets other nodes (excluding self)
        
        print(f"Phase VOTING of {self.friendly_node_id} starting 2PC for transaction {tx_id}")
        
        # Phase 1: Voting Phase - collect votes from all peer nodes
        votes = self._voting_phase(tx_id, operation, payload, peers)
        
        # Determine global decision based on peer votes
        all_commit = all(vote for vote in votes.values()) if votes else True
        
        # Intra-node communication: Voting Phase -> Decision Phase (local gRPC call)
        print(f"Phase VOTING of {self.friendly_node_id} sends RPC ExecuteDecision to Phase DECISION of {self.friendly_node_id}")
        
        try:
            # Call local Decision Phase service on port 50052
            channel = grpc.insecure_channel('localhost:50052')
            stub = twopc_pb2_grpc.DecisionPhaseServiceStub(channel)
            
            decision_request = twopc_pb2.VotingResult(
                transaction_id=tx_id,
                operation=operation,
                payload=json.dumps(payload),
                all_voted_commit=all_commit,
                coordinator_id=self.node_id
            )
            
            # Execute decision locally via Decision Phase service
            decision_response = stub.ExecuteDecision(decision_request, timeout=5)
            channel.close()
            
            print(f"Phase DECISION of {self.friendly_node_id} sends RPC ExecuteDecision response to Phase VOTING of {self.friendly_node_id}")
            
            if decision_response.commit:
                # Inform all peers to commit via their Decision Phase services
                self._decision_phase(tx_id, True, peers)
                return True, decision_response.message
            else:
                # Inform all peers to abort
                self._decision_phase(tx_id, False, peers)
                return False, decision_response.message
                
        except Exception as e:
            print(f"Phase VOTING of {self.friendly_node_id} error calling local Decision Phase: {str(e)}")
            # Inform peers to abort
            self._decision_phase(tx_id, False, peers)
            return False, f"Transaction {tx_id} aborted due to error"
    
    def _voting_phase(self, tx_id: str, operation: str, payload: Dict, peers: List[str]) -> Dict[str, bool]:
        """
        Voting phase: Send VoteRequest to all participants' Voting Phase services (port 50051).
        
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
                # Client-side log: Coordinator sends VoteRequest to peer's Voting Phase
                peer_name = get_friendly_node_name(peer)
                print(f"Phase VOTING of {self.friendly_node_id} sends RPC RequestVote to Phase VOTING of {peer_name}")
                
                # Connect to peer's Voting Phase service on port 50051
                peer_voting_addr = peer  # peer is already IP:50051
                channel = grpc.insecure_channel(peer_voting_addr)
                stub = twopc_pb2_grpc.VotingPhaseServiceStub(channel)
                
                response = stub.RequestVote(vote_request, timeout=5)
                votes[peer] = response.vote_commit
                
                # Client-side log: Coordinator receives VoteResponse
                vote_type = "COMMIT" if response.vote_commit else "ABORT"
                print(f"Phase VOTING of {self.friendly_node_id} receives RPC VoteResponse({vote_type}) from Phase VOTING of {peer_name}")
                
                channel.close()
            
            except Exception as e:
                peer_name = get_friendly_node_name(peer)
                print(f"Phase VOTING of {self.friendly_node_id} error contacting {peer_name}: {str(e)}")
                votes[peer] = False  # Treat failure as abort vote
        
        return votes
    
    def _decision_phase(self, tx_id: str, commit: bool, peers: List[str]) -> bool:
        """
        Decision phase: Send GlobalDecision to all participants' Decision Phase services (port 50052).
        
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
                # Client-side log: Coordinator sends GlobalDecision to peer's Decision Phase
                peer_name = get_friendly_node_name(peer)
                print(f"Phase DECISION of {self.friendly_node_id} sends RPC SendDecision({decision_type}) to Phase DECISION of {peer_name}")
                
                # Connect to peer's Decision Phase service on port 50052
                peer_ip = peer.split(':')[0]  # Extract IP from IP:50051
                peer_decision_addr = f"{peer_ip}:50052"
                channel = grpc.insecure_channel(peer_decision_addr)
                stub = twopc_pb2_grpc.DecisionPhaseServiceStub(channel)
                
                response = stub.SendDecision(decision, timeout=5)
                
                # Client-side log: Coordinator receives DecisionAck
                print(f"Phase DECISION of {self.friendly_node_id} receives RPC DecisionAck from Phase DECISION of {peer_name}")
                
                if not response.success:
                    all_acked = False
                    print(f"Phase DECISION of {self.friendly_node_id} warning: {peer_name} failed to acknowledge decision")
                
                channel.close()
            
            except Exception as e:
                peer_name = get_friendly_node_name(peer)
                print(f"Phase DECISION of {self.friendly_node_id} error sending decision to {peer_name}: {str(e)}")
                all_acked = False
        
        return all_acked
