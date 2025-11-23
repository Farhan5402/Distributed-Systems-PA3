
import os
import requests
import redis
import json
import asyncio
import grpc
from concurrent import futures
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager

# Import Raft implementation
from raft_node import RaftNode, RaftServiceServicer
import proto.raft_pb2_grpc as raft_pb2_grpc


# Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# Raft node instance (global)
raft_node: Optional[RaftNode] = None
grpc_server: Optional[grpc.Server] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - start/stop Raft node"""
    global raft_node, grpc_server
    
    # Get node configuration
    node_id = os.getenv("NODE_ID", "node-1")
    peers_str = os.getenv("RAFT_PEERS", "")
    peers = [p.strip() for p in peers_str.split(",") if p.strip()]
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))
    
    print(f"[INIT] Starting Raft node {node_id}")
    print(f"[INIT] Peers: {peers}")
    print(f"[INIT] gRPC port: {grpc_port}")
    
    # Create and start Raft node
    raft_node = RaftNode(
        node_id=node_id,
        peers=peers,
        apply_fn=apply_committed_operation,
        get_last_applied_fn=get_last_applied,
        set_last_applied_fn=set_last_applied
    )
    raft_node.start()
    
    # Start gRPC server for Raft RPCs
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    raft_pb2_grpc.add_RaftServiceServicer_to_server(
        RaftServiceServicer(raft_node),
        grpc_server
    )
    grpc_server.add_insecure_port(f'[::]:{grpc_port}')
    grpc_server.start()
    print(f"[INIT] gRPC server started on port {grpc_port}")
    
    yield  # Application runs
    
    # Shutdown
    print("[SHUTDOWN] Stopping Raft node and gRPC server")
    raft_node.stop()
    grpc_server.stop(grace=2)


app = FastAPI(lifespan=lifespan)

# Models
class Track(BaseModel):
    id: int
    title: str
    artist: str
    duration: int  # seconds
    votes: int = 0

class TrackAction(BaseModel):
    id: int


# Redis-backed storage
QUEUE_KEY = "music_queue"
HISTORY_KEY = "music_history"
LAST_APPLIED_KEY = "raft_last_applied"


def get_queue():
    data = redis_client.lrange(QUEUE_KEY, 0, -1)
    return [Track(**json.loads(item)) for item in data]

def set_queue(tracks: List[Track]):
    redis_client.delete(QUEUE_KEY)
    if tracks:
        redis_client.rpush(QUEUE_KEY, *[t.json() for t in tracks])

def get_history():
    data = redis_client.lrange(HISTORY_KEY, 0, -1)
    return [Track(**json.loads(item)) for item in data]

def add_to_history(track: Track):
    redis_client.rpush(HISTORY_KEY, track.json())


def get_last_applied() -> int:
    """Get last applied log index from Redis"""
    try:
        value = redis_client.get(LAST_APPLIED_KEY)
        return int(value) if value else 0
    except Exception:
        return 0


def set_last_applied(index: int):
    """Save last applied log index to Redis"""
    redis_client.set(LAST_APPLIED_KEY, index)


def apply_committed_operation(operation: str, payload: dict):
    """
    Apply a committed Raft operation to the state machine (Redis).
    This is called by the Raft node when an entry is committed.
    """
    print(f"[STATE_MACHINE] Applying operation: {operation} with payload: {payload}")
    
    try:
        if operation == "add_track":
            track = Track(**payload)
            queue = get_queue()
            queue.append(track)
            queue.sort(key=lambda x: (-x.votes, x.id))
            set_queue(queue)
        
        elif operation == "remove_track":
            track_id = payload["id"]
            queue = get_queue()
            queue = [t for t in queue if t.id != track_id]
            set_queue(queue)
        
        elif operation == "vote":
            track_id = payload["id"]
            up = payload.get("up", True)
            queue = get_queue()
            for t in queue:
                if t.id == track_id:
                    t.votes += 1 if up else -1
            queue.sort(key=lambda x: (-x.votes, x.id))
            set_queue(queue)
        
        elif operation == "play_next":
            queue = get_queue()
            if queue:
                track = queue.pop(0)
                set_queue(queue)
                add_to_history(track)
        
        elif operation == "clear":
            redis_client.delete(QUEUE_KEY)
            redis_client.delete(HISTORY_KEY)
        
        else:
            print(f"[STATE_MACHINE] Unknown operation: {operation}")
    
    except Exception as e:
        print(f"[STATE_MACHINE] Error applying operation {operation}: {e}")


def submit_to_raft(operation: str, payload: dict) -> bool:
    """
    Submit an operation to the Raft log.
    If this node is not the leader, return False.
    If leader, submit and wait for commit.
    """
    global raft_node
    
    if not raft_node:
        raise HTTPException(status_code=503, detail="Raft not initialized")
    
    if not raft_node.is_leader():
        leader = raft_node.get_leader()
        if leader:
            raise HTTPException(
                status_code=307,
                detail=f"Not the leader. Current leader is {leader}",
                headers={"X-Leader-Id": leader}
            )
        else:
            raise HTTPException(
                status_code=503,
                detail="No leader available. Election in progress."
            )
    
    # Submit to Raft
    success = raft_node.submit_operation(operation, payload, timeout=10.0)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to commit operation")
    
    return True



@app.post("/add_track")
def add_track(track: Track):
    submit_to_raft("add_track", track.dict())
    return {"message": "Track added", "queue": get_queue()}


@app.post("/remove_track")
def remove_track(action: TrackAction):
    submit_to_raft("remove_track", action.dict())
    return {"message": "Track removed", "queue": get_queue()}


@app.post("/vote")
def vote_track(action: TrackAction, up: bool = True):
    submit_to_raft("vote", {"id": action.id, "up": up})
    return {"queue": get_queue()}


@app.get("/queue")
def api_get_queue():
    return get_queue()


@app.get("/metadata/{track_id}")
def get_metadata(track_id: int):
    queue = get_queue()
    for t in queue:
        if t.id == track_id:
            return t
    raise HTTPException(status_code=404, detail="Track not found")


@app.post("/play_next")
def play_next():
    queue = get_queue()
    if not queue:
        raise HTTPException(status_code=400, detail="Queue empty")
    submit_to_raft("play_next", {})
    # Get updated queue and history
    return {"now_playing": get_history()[-1] if get_history() else None}


@app.get("/history")
def api_get_history():
    return get_history()


# Test utility endpoint to clear queue and history (for test isolation)
@app.post("/clear")
def clear_all():
    submit_to_raft("clear", {})
    return {"message": "Queue and history cleared"}


# Raft status endpoint
@app.get("/raft/status")
def raft_status():
    """Get Raft node status"""
    if not raft_node:
        return {"error": "Raft not initialized"}
    
    with raft_node.lock:
        return {
            "node_id": raft_node.node_id,
            "state": raft_node.state.value,
            "term": raft_node.current_term,
            "leader": raft_node.leader_id,
            "log_size": len(raft_node.log),
            "commit_index": raft_node.commit_index,
            "is_leader": raft_node.state.value == "LEADER"
        }
