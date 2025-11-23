"""
Two-Phase Commit Helper Functions
Shared utilities for voting and decision phase services
"""

import os
import socket
from typing import List


# Global cache for hostname-to-node-name mapping
_hostname_cache = {}
_ip_to_hostname_cache = {}


def get_node_id():
    """Get the current node's hostname as its ID."""
    # First check if we have REDIS_HOST which has the node number
    redis_host = os.environ.get('REDIS_HOST', '')
    if redis_host and 'redis-' in redis_host:
        # Extract node number from redis-X
        try:
            node_num = redis_host.split('-')[1]
            return f"layered-rest-node-{node_num}"
        except:
            pass
    
    # Fall back to hostname
    return os.environ.get('HOSTNAME', 'unknown-node')


def get_friendly_node_name(identifier: str) -> str:
    """
    Convert hostname or IP:port to friendly node name (e.g., Node-1, Node-2).
    
    Args:
        identifier: Either a hostname or IP:port string
    
    Returns:
        Friendly name like "Node-1" or original if mapping not found
    """
    original_identifier = identifier
    
    # Remove port if present
    if ':' in identifier:
        identifier = identifier.split(':')[0]
    
    # Check cache first (before any modifications)
    if original_identifier in _hostname_cache:
        return _hostname_cache[original_identifier]
    
    # Check if it's an IP address (has digits and dots in pattern X.X.X.X)
    is_ip = all(part.isdigit() for part in identifier.replace(':', '').split('.') if part)
    
    # Remove Docker network suffix only if it's NOT an IP address
    if '.' in identifier and not is_ip:
        identifier = identifier.split('.')[0]
    
    # Try to resolve IP to hostname
    if is_ip:
        # It's an IP address
        if identifier in _ip_to_hostname_cache:
            hostname = _ip_to_hostname_cache[identifier]
        else:
            try:
                hostname = socket.gethostbyaddr(identifier)[0]
                _ip_to_hostname_cache[identifier] = hostname
                # Remove network suffix from resolved hostname
                if '.' in hostname and 'layered-rest' in hostname:
                    hostname = hostname.split('.')[0]
            except:
                hostname = identifier
    else:
        hostname = identifier
    
    # Map hostname to friendly name
    # Docker compose creates hostnames like layered-rest-node-1, layered-rest-node-2, etc.
    if 'node' in hostname.lower():
        # Extract node number from hostname
        parts = hostname.split('-')
        for i, part in enumerate(parts):
            if 'node' in part.lower() and i + 1 < len(parts):
                try:
                    node_num = int(parts[i + 1])
                    friendly_name = f"Node-{node_num}"
                    _hostname_cache[original_identifier] = friendly_name
                    _hostname_cache[identifier] = friendly_name
                    _hostname_cache[hostname] = friendly_name
                    return friendly_name
                except (ValueError, IndexError):
                    pass
    
    # If no mapping found, return as is
    _hostname_cache[original_identifier] = hostname
    return hostname


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
