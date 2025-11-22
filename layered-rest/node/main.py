
import os
import requests
import redis
import json
import grpc
import threading
import sys
from concurrent import futures
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

# Add proto to path for generated files
sys.path.insert(0, '/app/proto')

# Import 2PC components
from twopc_service import TwoPhaseCommitServicer, TwoPhaseCommitCoordinator
import twopc_pb2_grpc


# Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

app = FastAPI()

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

# 2PC Coordinator
coordinator = TwoPhaseCommitCoordinator()


def get_peers():
    peers = os.getenv("PEER_NODES", "")
    print(f"[DEBUG] PEER_NODES: {peers}")
    return [p.strip() for p in peers.split(",") if p.strip()]


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


# 2PC Validation, Commit, and Abort functions
def validate_operation(operation: str, payload: dict) -> bool:
    """Validate if an operation can be committed."""
    try:
        if operation == "add_track":
            track_data = payload
            # Check if track already exists
            queue = get_queue()
            if any(t.id == track_data['id'] for t in queue):
                return False  # Duplicate track
            return True
        
        elif operation == "remove_track":
            track_id = payload['id']
            queue = get_queue()
            return any(t.id == track_id for t in queue)
        
        elif operation == "vote":
            track_id = payload['id']
            queue = get_queue()
            return any(t.id == track_id for t in queue)
        
        return True
    except Exception as e:
        print(f"[ERROR] Validation error: {e}")
        return False


def commit_operation(operation: str, payload: dict):
    """Commit an operation locally."""
    if operation == "add_track":
        track = Track(**payload)
        queue = get_queue()
        queue.append(track)
        queue.sort(key=lambda x: (-x.votes, x.id))
        set_queue(queue)
    
    elif operation == "remove_track":
        track_id = payload['id']
        queue = get_queue()
        queue = [t for t in queue if t.id != track_id]
        set_queue(queue)
    
    elif operation == "vote":
        track_id = payload['id']
        up = payload.get('up', True)
        queue = get_queue()
        for t in queue:
            if t.id == track_id:
                t.votes += 1 if up else -1
        queue.sort(key=lambda x: (-x.votes, x.id))
        set_queue(queue)


def abort_operation(operation: str, payload: dict):
    """Abort/rollback an operation (cleanup if needed)."""
    # For this implementation, abort is mostly a no-op
    # as we haven't modified state yet during voting phase
    print(f"[2PC] Aborting operation {operation} with payload {payload}")


# Initialize 2PC gRPC server
def start_grpc_server():
    """Start the gRPC server for 2PC communication."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = TwoPhaseCommitServicer(
        validate_fn=validate_operation,
        commit_fn=commit_operation,
        abort_fn=abort_operation
    )
    twopc_pb2_grpc.add_TwoPhaseCommitServiceServicer_to_server(servicer, server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("[2PC] gRPC server started on port 50051")
    server.wait_for_termination()


@app.on_event("startup")
async def startup_event():
    """Start gRPC server in background thread when FastAPI starts."""
    grpc_thread = threading.Thread(target=start_grpc_server, daemon=True)
    grpc_thread.start()
    print("[2PC] Background gRPC server thread started")


def broadcast_queue():
    peers = get_peers()
    queue = get_queue()
    print(f"[DEBUG] Broadcasting queue to peers: {peers}")
    for peer in peers:
        try:
            print(f"[DEBUG] Sending sync to {peer}/sync with queue: {[t.dict() for t in queue]}")
            resp = requests.post(f"{peer}/sync", json=[t.dict() for t in queue], timeout=3)
            print(f"[DEBUG] Sync response from {peer}: {resp.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to sync with {peer}: {e}")



@app.post("/add_track")
def add_track(track: Track):
    """Add a track using 2PC protocol."""
    # Execute 2PC as coordinator (coordinator also participates via gRPC to self)
    success, message = coordinator.execute_2pc("add_track", track.dict())
    
    if success:
        # Transaction committed via 2PC on all nodes (including this one)
        queue = get_queue()
        return {"message": message, "queue": queue}
    else:
        raise HTTPException(status_code=400, detail=message)


@app.post("/remove_track")
def remove_track(action: TrackAction):
    """Remove a track using 2PC protocol."""
    success, message = coordinator.execute_2pc("remove_track", action.dict())
    
    if success:
        # Transaction committed via 2PC on all nodes (including this one)
        queue = get_queue()
        return {"message": message, "queue": queue}
    else:
        raise HTTPException(status_code=400, detail=message)


@app.post("/vote")
def vote_track(action: TrackAction, up: bool = True):
    """Vote for a track using 2PC protocol."""
    payload = {"id": action.id, "up": up}
    success, message = coordinator.execute_2pc("vote", payload)
    
    if success:
        # Transaction committed via 2PC on all nodes (including this one)
        queue = get_queue()
        return {"queue": queue}
    else:
        raise HTTPException(status_code=400, detail=message)


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
    track = queue.pop(0)
    set_queue(queue)
    add_to_history(track)
    # No 2PC needed for play_next as it's a read operation followed by local state change
    return {"now_playing": track}


@app.get("/history")
def api_get_history():
    return get_history()


# Sync endpoint for receiving queue updates from peers
# Sync endpoint for receiving queue updates from peers
@app.post("/sync")
def sync_queue(new_queue: List[Track]):
    print(f"[DEBUG] Received sync: {new_queue}")
    queue = [Track(**t.dict()) if isinstance(t, Track) else Track(**t) for t in new_queue]
    set_queue(queue)
    print(f"[DEBUG] Queue after sync: {queue}")
    return {"message": "Queue synchronized", "queue": queue}


# Test utility endpoint to clear queue and history (for test isolation)
@app.post("/clear")
def clear_all():
    redis_client.delete(QUEUE_KEY)
    redis_client.delete(HISTORY_KEY)
    return {"message": "Queue and history cleared"}
