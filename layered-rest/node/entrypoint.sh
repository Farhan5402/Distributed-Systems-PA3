#!/bin/sh
set -x

# Entrypoint script for dynamic peer discovery and Redis replica assignment
#
# Usage:
# - Discovers peer containers by their hostnames and excludes self
# - Sets PEER_NODES environment variable with comma-separated HTTP URLs
# - Assigns each node to its own Redis replica based on container order

# Wait for DNS to propagate
sleep 2

# Get the hostname of this container
SELF_HOSTNAME=$(hostname)

# Discover all containers in the same service by resolving the service name
# and building peer list excluding self
if [ -z "$PEER_NODES" ]; then
  # Get all IP addresses for the 'node' service
  PEER_IPS=$(getent hosts node | awk '{print $1}' | sort -u)
  SELF_IP=$(hostname -i)
  
  # Determine which Redis replica this node should use
  # by finding this node's position in the sorted list
  NODE_INDEX=1
  CURRENT_INDEX=1
  for ip in $PEER_IPS; do
    if [ "$ip" = "$SELF_IP" ]; then
      NODE_INDEX=$CURRENT_INDEX
      break
    fi
    CURRENT_INDEX=$((CURRENT_INDEX + 1))
  done
  
  # Set REDIS_HOST to the corresponding redis instance
  export REDIS_HOST="redis-$NODE_INDEX"
  echo "[entrypoint] Assigned to REDIS_HOST: $REDIS_HOST"
  
  # Build comma-separated list of peer URLs (HTTP for REST API)
  PEER_LIST=""
  for ip in $PEER_IPS; do
    if [ "$ip" != "$SELF_IP" ]; then
      if [ -z "$PEER_LIST" ]; then
        PEER_LIST="http://$ip:8000"
      else
        PEER_LIST="$PEER_LIST,http://$ip:8000"
      fi
    fi
  done
  
  export PEER_NODES="$PEER_LIST"
  echo "[entrypoint] Discovered PEER_NODES: $PEER_NODES"
fi

echo "[entrypoint] Self hostname: $SELF_HOSTNAME"
echo "[entrypoint] Starting FastAPI app with uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000


