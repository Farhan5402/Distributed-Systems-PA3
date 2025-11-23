#!/bin/sh
set -x

# Entrypoint script for dynamic peer discovery and Redis replica assignment
#
# Usage:
# - Discovers peer containers by their hostnames and excludes self
# - Sets PEER_NODES environment variable with comma-separated HTTP URLs
# - Uses NODE_ID environment variable to determine Redis replica

# Wait for DNS to propagate
sleep 2

# Get the hostname of this container
SELF_HOSTNAME=$(hostname)

# Discover all containers in the same service by resolving the service name
# and building peer list excluding self
if [ -z "$PEER_NODES" ]; then
  # NODE_ID should be set by docker-compose.yml
  if [ -z "$NODE_ID" ]; then
    echo "[entrypoint] ERROR: NODE_ID not set!"
    exit 1
  fi
  
  # REDIS_HOST should also be set by docker-compose.yml
  if [ -z "$REDIS_HOST" ]; then
    export REDIS_HOST="redis-$NODE_ID"
  fi
  
  echo "[entrypoint] NODE_ID: $NODE_ID"
  echo "[entrypoint] REDIS_HOST: $REDIS_HOST"
  
  # Build peer list by checking all possible nodes (1-5)
  PEER_LIST=""
  for i in 1 2 3 4 5; do
    if [ "$i" != "$NODE_ID" ]; then
      # Check if the node is reachable
      if getent hosts "node-$i" >/dev/null 2>&1; then
        NODE_IP=$(getent hosts "node-$i" | awk '{print $1}' | head -1)
        if [ -z "$PEER_LIST" ]; then
          PEER_LIST="http://$NODE_IP:8000"
        else
          PEER_LIST="$PEER_LIST,http://$NODE_IP:8000"
        fi
      fi
    fi
  done
  
  export PEER_NODES="$PEER_LIST"
  echo "[entrypoint] Discovered PEER_NODES: $PEER_NODES"
fi

echo "[entrypoint] Self hostname: $SELF_HOSTNAME"
echo "[entrypoint] Starting FastAPI app with uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000


