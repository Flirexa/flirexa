"""
VPN Management Studio Input Validators
"""

import re
from typing import Tuple


def validate_client_name(name: str) -> Tuple[bool, str]:
    """
    Validate client name

    Args:
        name: Client name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Name cannot be empty"

    if len(name) > 100:
        return False, "Name too long (max 100 characters)"

    if len(name) < 1:
        return False, "Name too short (min 1 character)"

    # Allow only alphanumeric, dash, underscore
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        return False, "Name can only contain letters, numbers, dash and underscore"

    # Don't allow starting with dash
    if name.startswith('-'):
        return False, "Name cannot start with a dash"

    # Reserved names
    reserved = ['all', 'none', 'default', 'server', 'admin', 'root']
    if name.lower() in reserved:
        return False, f"'{name}' is a reserved name"

    return True, ""


def validate_ip_address(ip: str) -> Tuple[bool, str]:
    """
    Validate IPv4 address

    Args:
        ip: IP address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip:
        return False, "IP address cannot be empty"

    # Simple IPv4 regex
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False, "Invalid IP address format"

    # Check each octet
    octets = ip.split('.')
    for octet in octets:
        value = int(octet)
        if value < 0 or value > 255:
            return False, "IP address octets must be 0-255"

    return True, ""


def validate_port(port: int) -> Tuple[bool, str]:
    """
    Validate port number

    Args:
        port: Port number to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(port, int):
        return False, "Port must be an integer"

    if port < 1 or port > 65535:
        return False, "Port must be between 1 and 65535"

    # Common privileged ports
    if port < 1024:
        return True, "Warning: Port below 1024 requires root"

    return True, ""


def validate_endpoint(endpoint: str) -> Tuple[bool, str]:
    """
    Validate WireGuard endpoint (ip:port or domain:port)

    Args:
        endpoint: Endpoint to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not endpoint:
        return False, "Endpoint cannot be empty"

    if ':' not in endpoint:
        return False, "Endpoint must be in format host:port"

    parts = endpoint.rsplit(':', 1)
    if len(parts) != 2:
        return False, "Invalid endpoint format"

    host, port_str = parts

    # Validate port
    try:
        port = int(port_str)
        port_valid, port_msg = validate_port(port)
        if not port_valid:
            return False, port_msg
    except ValueError:
        return False, "Port must be a number"

    # Validate host (IP or domain)
    if not host:
        return False, "Host cannot be empty"

    # Check if it's an IP
    ip_valid, _ = validate_ip_address(host)
    if not ip_valid:
        # Check if it's a valid domain
        domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$'
        if not re.match(domain_pattern, host):
            return False, "Invalid hostname or IP address"

    return True, ""


def validate_wireguard_key(key: str) -> Tuple[bool, str]:
    """
    Validate WireGuard key (base64, 44 chars)

    Args:
        key: Key to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not key:
        return False, "Key cannot be empty"

    # WireGuard keys are base64-encoded 32 bytes = 44 chars
    if len(key) != 44:
        return False, "Key must be 44 characters"

    # Check if valid base64
    import base64
    try:
        decoded = base64.b64decode(key)
        if len(decoded) != 32:
            return False, "Key must decode to 32 bytes"
    except Exception:
        return False, "Key must be valid base64"

    return True, ""


def validate_dns(dns: str) -> Tuple[bool, str]:
    """
    Validate DNS servers string

    Args:
        dns: Comma-separated DNS servers

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not dns:
        return False, "DNS cannot be empty"

    servers = [s.strip() for s in dns.split(',')]

    for server in servers:
        valid, msg = validate_ip_address(server)
        if not valid:
            return False, f"Invalid DNS server '{server}': {msg}"

    return True, ""
