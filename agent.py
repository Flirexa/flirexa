#!/usr/bin/env python3
"""
VPN Manager Agent - WireGuard Management Agent for Remote Servers
Runs on child servers, receives commands via HTTP API from master
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List, Dict
import subprocess
import os
import sys
import time
import json
import logging
import re
from datetime import datetime, timezone
import psutil

try:
    import socket as _socket
    from loguru import logger as _loguru_logger

    _LOG_DIR = os.getenv("LOG_DIR", "/var/log/vpnmanager")
    _LOG_FILE = os.path.join(_LOG_DIR, "agent.log")
    _AGENT_HOSTNAME = _socket.gethostname()

    def _agent_version() -> str:
        vf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
        try:
            with open(vf) as _f:
                return _f.read().strip()
        except OSError:
            return "1.3.0"  # fall back to hardcoded AGENT_VERSION

    def _json_format(record: dict) -> str:
        entry = {
            "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hostname": _AGENT_HOSTNAME,
            "version": _agent_version(),
            "component": "agent",
            "level": record["level"].name,
            "message": record["message"],
        }
        exc = record.get("exception")
        if exc is not None and exc.value is not None:
            entry["error"] = str(exc.value)
        return json.dumps(entry, ensure_ascii=False) + "\n"

    _loguru_logger.remove()
    _loguru_logger.add(sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | agent | <level>{message}</level>",
        backtrace=False, diagnose=False)
    def _file_sink(message, _path=_LOG_FILE):
        import threading
        line = _json_format(message.record)
        # Simple append — logrotate handles cleanup; no rotation lock needed for agent
        try:
            with open(_path, "a", encoding="utf-8") as _fh:
                _fh.write(line)
        except OSError:
            pass

    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        _loguru_logger.add(_file_sink, level="INFO", enqueue=True, backtrace=False, diagnose=False)
    except (PermissionError, OSError):
        pass  # No file logging if dir not writable

    logger = _loguru_logger

except ImportError:
    import logging as logger  # type: ignore

# ============================================================================
# CONFIG
# ============================================================================

AGENT_VERSION = "1.3.0"
_AGENT_START_TIME = datetime.now(timezone.utc)

API_KEY = (
    os.getenv("AGENT_API_KEY", "")
    or os.getenv("SPONGEBOT_AGENT_API_KEY", "")
    or os.getenv("VPNMANAGER_AGENT_API_KEY", "")
)
if not API_KEY:
    print("FATAL: AGENT_API_KEY environment variable must be set")
    print("Legacy fallback names: SPONGEBOT_AGENT_API_KEY, VPNMANAGER_AGENT_API_KEY")
    sys.exit(1)
INTERFACE = os.getenv("WG_INTERFACE", "wg0")
_IS_AWG = INTERFACE.startswith("awg")
_WG_CMD = "awg" if _IS_AWG else "wg"
_WGQUICK_CMD = "awg-quick" if _IS_AWG else "wg-quick"
_DEFAULT_CONFIG_DIR = "/etc/amneziawg" if _IS_AWG else "/etc/wireguard"
CONFIG_PATH = os.getenv("WG_CONFIG_PATH", f"{_DEFAULT_CONFIG_DIR}/{INTERFACE}.conf")

# ============================================================================
# APP
# ============================================================================

app = FastAPI(title="VPN Manager Agent", version="1.2.0")

# ============================================================================
# AUTH
# ============================================================================

def verify_api_key(x_api_key: str = Header(...)):
    """Verify API key from header"""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ============================================================================
# SCHEMAS
# ============================================================================

class PeerCreate(BaseModel):
    public_key: str
    allowed_ips: str
    preshared_key: Optional[str] = None

class PeerUpdate(BaseModel):
    public_key: str
    allowed_ips: Optional[str] = None
    preshared_key: Optional[str] = None

class PeerDelete(BaseModel):
    public_key: str

class BandwidthLimit(BaseModel):
    ip: str
    limit_mbps: int
    ip_index: int = 100    # tc classid = 1:{ip_index}
    remove: bool = False   # True = remove the limit

class BandwidthSyncItem(BaseModel):
    ip: str
    limit_mbps: int
    ip_index: int

class BandwidthSyncRequest(BaseModel):
    limits: List[BandwidthSyncItem] = []

class ConfigContent(BaseModel):
    content: str

class RestoreRequest(BaseModel):
    config: str
    peers: List[Dict] = []

# ============================================================================
# LOCAL WIREGUARD MANAGER (copy of existing code, no SSH)
# ============================================================================

def run_cmd(cmd: List[str], input_data: Optional[str] = None) -> subprocess.CompletedProcess:
    """Execute command locally (no SSH)"""
    try:
        return subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {e.stderr}")

def wg_set_peer(public_key: str, allowed_ips: str, preshared_key: Optional[str] = None) -> bool:
    """Add or update peer"""
    cmd = [_WG_CMD, "set", INTERFACE, "peer", public_key, "allowed-ips", allowed_ips]

    if preshared_key:
        cmd.extend(["preshared-key", "/dev/stdin"])
        run_cmd(cmd, input_data=preshared_key)
    else:
        run_cmd(cmd)

    return True

def wg_remove_peer(public_key: str) -> bool:
    """Remove peer"""
    cmd = [_WG_CMD, "set", INTERFACE, "peer", public_key, "remove"]
    run_cmd(cmd)
    return True

def wg_show_dump() -> List[Dict]:
    """Get all peers from wg show dump"""
    result = run_cmd([_WG_CMD, "show", INTERFACE, "dump"])
    lines = result.stdout.strip().split("\n")

    peers = []
    for line in lines[1:]:  # Skip interface line
        parts = line.split("\t")
        if len(parts) >= 6:
            peers.append({
                "public_key": parts[0],
                "preshared_key": parts[1] if parts[1] != "(none)" else None,
                "endpoint": parts[2] if parts[2] != "(none)" else None,
                "allowed_ips": parts[3],
                "latest_handshake": int(parts[4]) if parts[4] != "0" else None,
                "transfer_rx": int(parts[5]),
                "transfer_tx": int(parts[6]),
            })

    return peers

def is_interface_up() -> bool:
    """Check if interface is up"""
    result = run_cmd([_WG_CMD, "show", INTERFACE])
    return "interface:" in result.stdout.lower()

def wg_save_config() -> bool:
    """Save current WireGuard/AmneziaWG runtime state to config file.
    Uses wg-quick/awg-quick save first, falls back to wg/awg showconf if that fails."""
    try:
        subprocess.run(
            [_WGQUICK_CMD, "save", INTERFACE],
            capture_output=True, text=True, check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: dump current config and write manually
        try:
            result = subprocess.run(
                [_WG_CMD, "showconf", INTERFACE],
                capture_output=True, text=True, check=True
            )
            with open(CONFIG_PATH, "w") as f:
                f.write(result.stdout)
            os.chmod(CONFIG_PATH, 0o600)
            return True
        except Exception:
            return False

IFB_DEVICE = "ifb0"  # Virtual device for ingress (upload) shaping


def tc_ensure_qdisc() -> bool:
    """Set up HTB qdisc on egress AND ingress (via IFB) if not already present."""
    try:
        result = subprocess.run(
            ["tc", "qdisc", "show", "dev", INTERFACE],
            capture_output=True, text=True
        )
        if "htb" in result.stdout:
            # Also ensure IFB is set up
            _ensure_ifb()
            return True

        # Delete any existing qdisc
        subprocess.run(
            ["tc", "qdisc", "del", "dev", INTERFACE, "root"],
            stderr=subprocess.DEVNULL
        )

        # Create HTB root qdisc (egress — limits download)
        subprocess.run(
            ["tc", "qdisc", "add", "dev", INTERFACE,
             "root", "handle", "1:", "htb", "default", "9999"],
            check=True, capture_output=True, text=True
        )

        # Create root class (1 Gbps)
        subprocess.run(
            ["tc", "class", "add", "dev", INTERFACE,
             "parent", "1:", "classid", "1:1", "htb",
             "rate", "1000mbit"],
            check=True, capture_output=True, text=True
        )

        # Set up IFB for ingress (upload) shaping
        _ensure_ifb()

        return True
    except Exception:
        return False


def _ensure_ifb() -> bool:
    """Set up IFB device for ingress (upload) shaping."""
    try:
        # Check if IFB already configured
        result = subprocess.run(
            ["tc", "qdisc", "show", "dev", IFB_DEVICE],
            capture_output=True, text=True
        )
        if "htb" in result.stdout:
            return True

        # Load ifb kernel module
        subprocess.run(["modprobe", "ifb", "numifbs=1"], stderr=subprocess.DEVNULL)

        # Bring up ifb0
        subprocess.run(["ip", "link", "set", "dev", IFB_DEVICE, "up"],
                        stderr=subprocess.DEVNULL)

        # Redirect ingress from wg0 to ifb0
        subprocess.run(
            ["tc", "qdisc", "add", "dev", INTERFACE, "handle", "ffff:", "ingress"],
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["tc", "filter", "add", "dev", INTERFACE, "parent", "ffff:",
             "protocol", "ip", "u32", "match", "u32", "0", "0",
             "action", "mirred", "egress", "redirect", "dev", IFB_DEVICE],
            stderr=subprocess.DEVNULL
        )

        # Create HTB on ifb0 (same structure as egress)
        subprocess.run(
            ["tc", "qdisc", "del", "dev", IFB_DEVICE, "root"],
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["tc", "qdisc", "add", "dev", IFB_DEVICE,
             "root", "handle", "2:", "htb", "default", "9999"],
            capture_output=True, text=True
        )
        subprocess.run(
            ["tc", "class", "add", "dev", IFB_DEVICE,
             "parent", "2:", "classid", "2:1", "htb",
             "rate", "1000mbit"],
            capture_output=True, text=True
        )
        return True
    except Exception:
        return False


def _filter_exists_for_class(dev: str, class_id: str) -> bool:
    """Check if a tc filter already routes traffic to the given class on device."""
    try:
        result = subprocess.run(
            ["tc", "filter", "show", "dev", dev],
            capture_output=True, text=True
        )
        return (f"flowid {class_id} " in result.stdout or
                f"flowid {class_id}\n" in result.stdout or
                result.stdout.rstrip().endswith(f"flowid {class_id}"))
    except Exception:
        return False


def _ensure_class(dev: str, parent: str, class_id: str, rate: str):
    """Create or update tc class on device."""
    change = subprocess.run(
        ["tc", "class", "change", "dev", dev,
         "parent", parent, "classid", class_id, "htb",
         "rate", rate, "ceil", rate],
        capture_output=True
    )
    if change.returncode != 0:
        subprocess.run(
            ["tc", "class", "add", "dev", dev,
             "parent", parent, "classid", class_id, "htb",
             "rate", rate, "ceil", rate],
            capture_output=True, text=True
        )


def tc_set_bandwidth(ip: str, limit_mbps: int, ip_index: int) -> bool:
    """Set bandwidth limit for a specific client (both download and upload)"""
    tc_ensure_qdisc()
    rate = f"{limit_mbps}mbit"

    # === EGRESS (download: server → client) on wg0 ===
    egress_class = f"1:{ip_index}"
    _ensure_class(INTERFACE, "1:1", egress_class, rate)

    if not _filter_exists_for_class(INTERFACE, egress_class):
        subprocess.run(
            ["tc", "filter", "add", "dev", INTERFACE,
             "protocol", "ip", "parent", "1:0", "prio", "1",
             "u32", "match", "ip", "dst", f"{ip}/32",
             "flowid", egress_class],
            capture_output=True
        )

    # === INGRESS (upload: client → server) on ifb0 ===
    ingress_class = f"2:{ip_index}"
    _ensure_class(IFB_DEVICE, "2:1", ingress_class, rate)

    if not _filter_exists_for_class(IFB_DEVICE, ingress_class):
        subprocess.run(
            ["tc", "filter", "add", "dev", IFB_DEVICE,
             "protocol", "ip", "parent", "2:0", "prio", "1",
             "u32", "match", "ip", "src", f"{ip}/32",
             "flowid", ingress_class],
            capture_output=True
        )

    return True


def _remove_class_and_filters(dev: str, parent_filter: str, class_id: str):
    """Remove tc class and its filters from a device."""
    # Remove filters pointing to this class
    try:
        result = subprocess.run(
            ["tc", "filter", "show", "dev", dev],
            capture_output=True, text=True
        )
        lines = result.stdout.split("\n")
        for i, line in enumerate(lines):
            if f"flowid {class_id} " in line or f"flowid {class_id}\n" in line or line.strip().endswith(f"flowid {class_id}"):
                for j in range(i, max(i - 3, -1), -1):
                    if "fh " in lines[j]:
                        parts = lines[j].split()
                        for k, p in enumerate(parts):
                            if p == "fh" and k + 1 < len(parts):
                                subprocess.run(
                                    ["tc", "filter", "del", "dev", dev,
                                     "parent", parent_filter, "handle", parts[k + 1],
                                     "prio", "1", "u32"],
                                    stderr=subprocess.DEVNULL
                                )
                        break
    except Exception:
        pass

    # Delete class
    subprocess.run(
        ["tc", "class", "del", "dev", dev, "classid", class_id],
        stderr=subprocess.DEVNULL
    )


def tc_remove_bandwidth(ip_index: int) -> bool:
    """Remove bandwidth limit for a specific client (both directions)"""
    _remove_class_and_filters(INTERFACE, "1:0", f"1:{ip_index}")
    _remove_class_and_filters(IFB_DEVICE, "2:0", f"2:{ip_index}")
    return True


def tc_get_class_indices(device: str) -> set:
    """Return set of ip_index values for child HTB classes on device (excludes root 1:1 / 2:1)."""
    try:
        result = subprocess.run(
            ["tc", "class", "show", "dev", device],
            capture_output=True, text=True
        )
        indices = set()
        for line in result.stdout.splitlines():
            # e.g. "class htb 1:7 parent 1:1 prio 0 rate 10Mbit ..."
            m = re.search(r'class htb \d+:(\d+) parent \d+:\d+', line)
            if m:
                idx = int(m.group(1))
                if idx != 1:   # skip root class
                    indices.add(idx)
        return indices
    except Exception:
        return set()

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint — no auth required. Returns VPN interface diagnostics."""
    uptime_seconds = int((datetime.now(timezone.utc) - _AGENT_START_TIME).total_seconds())

    vpn_up = False
    peer_count = 0
    peers_active_5m = 0
    try:
        vpn_up = is_interface_up()
        if vpn_up:
            peers = wg_show_dump()
            peer_count = len(peers)
            now = time.time()
            peers_active_5m = sum(
                1 for p in peers
                if p.get("latest_handshake") and (now - p["latest_handshake"]) < 300
            )
    except Exception:
        pass

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": AGENT_VERSION,
        "interface": INTERFACE,
        "vpn_interface_status": "up" if vpn_up else "down",
        "peer_count": peer_count,
        "peers_active_5m": peers_active_5m,
        "config_path": CONFIG_PATH,
        "uptime_seconds": uptime_seconds,
    }

@app.get("/stats")
async def get_stats(authenticated: bool = Depends(verify_api_key)):
    """Get interface and peer statistics"""
    peers = wg_show_dump()

    # System stats
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "interface": INTERFACE,
        "is_up": is_interface_up(),
        "peers_count": len(peers),
        "peers": peers,
        "system": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/peer/create")
async def create_peer(
    peer: PeerCreate,
    authenticated: bool = Depends(verify_api_key)
):
    """Create or update peer"""
    try:
        wg_set_peer(peer.public_key, peer.allowed_ips, peer.preshared_key)
        wg_save_config()
        return {
            "success": True,
            "message": f"Peer {peer.public_key[:16]}... created/updated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/peer/delete")
async def delete_peer(
    peer: PeerDelete,
    authenticated: bool = Depends(verify_api_key)
):
    """Delete peer"""
    try:
        wg_remove_peer(peer.public_key)
        wg_save_config()
        return {
            "success": True,
            "message": f"Peer {peer.public_key[:16]}... deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/peer/enable")
async def enable_peer(
    peer: PeerUpdate,
    authenticated: bool = Depends(verify_api_key)
):
    """Enable peer (add to WireGuard)"""
    if not peer.allowed_ips:
        raise HTTPException(status_code=400, detail="allowed_ips required")

    try:
        wg_set_peer(peer.public_key, peer.allowed_ips, peer.preshared_key)
        wg_save_config()
        return {
            "success": True,
            "message": f"Peer {peer.public_key[:16]}... enabled"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/peer/disable")
async def disable_peer(
    peer: PeerDelete,
    authenticated: bool = Depends(verify_api_key)
):
    """Disable peer (remove from WireGuard)"""
    try:
        wg_remove_peer(peer.public_key)
        wg_save_config()
        return {
            "success": True,
            "message": f"Peer {peer.public_key[:16]}... disabled"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/peer/set_bandwidth")
async def set_bandwidth(
    limit: BandwidthLimit,
    authenticated: bool = Depends(verify_api_key)
):
    """Set or remove bandwidth limit for peer"""
    try:
        if limit.remove:
            tc_remove_bandwidth(limit.ip_index)
            return {
                "success": True,
                "message": f"Bandwidth limit removed for ip_index {limit.ip_index}"
            }
        else:
            tc_set_bandwidth(limit.ip, limit.limit_mbps, limit.ip_index)
            return {
                "success": True,
                "message": f"Bandwidth limit set: {limit.limit_mbps} Mbps for {limit.ip} (class 1:{limit.ip_index})"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/bandwidth/sync")
async def sync_bandwidth(
    data: BandwidthSyncRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Sync bandwidth limits to desired state.

    Removes any stale TC rules not present in the provided list,
    then applies all provided limits. Safe to call on startup.
    Solves the case where TC rules exist from a previous system
    (e.g. old wireguard-bot) that are no longer reflected in the DB.
    """
    try:
        desired = {item.ip_index: item for item in data.limits}

        # Remove stale classes not in desired state
        current_egress = tc_get_class_indices(INTERFACE)
        current_ingress = tc_get_class_indices(IFB_DEVICE)
        stale = (current_egress | current_ingress) - set(desired.keys())
        for idx in stale:
            tc_remove_bandwidth(idx)

        # Apply desired limits (set_bandwidth is idempotent)
        for item in desired.values():
            tc_set_bandwidth(item.ip, item.limit_mbps, item.ip_index)

        return {
            "success": True,
            "stale_removed": len(stale),
            "limits_applied": len(desired),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONFIG ENDPOINTS
# ============================================================================

@app.post("/config/save")
async def save_config(authenticated: bool = Depends(verify_api_key)):
    """Save current WireGuard runtime state to config file"""
    success = wg_save_config()
    if success:
        return {"success": True, "message": "Config saved to file"}
    raise HTTPException(status_code=500, detail="Failed to save config")

@app.post("/config/write")
async def write_config(
    data: ConfigContent,
    authenticated: bool = Depends(verify_api_key)
):
    """Write provided config content directly to config file"""
    try:
        with open(CONFIG_PATH, "w") as f:
            f.write(data.content)
        os.chmod(CONFIG_PATH, 0o600)
        return {"success": True, "message": "Config written to file"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {str(e)}")

@app.get("/config")
async def get_config(authenticated: bool = Depends(verify_api_key)):
    """Get current WireGuard config file content (private keys redacted)"""
    try:
        with open(CONFIG_PATH, "r") as f:
            lines = f.readlines()
        # Redact PrivateKey lines to prevent key leakage
        redacted = []
        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("privatekey"):
                key_parts = stripped.split("=", 1)
                redacted.append(f"{key_parts[0]} = [REDACTED]\n")
            else:
                redacted.append(line)
        return {"content": "".join(redacted), "path": CONFIG_PATH}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")

# ============================================================================
# ROOT
# ============================================================================

@app.get("/backup")
async def backup_full(authenticated: bool = Depends(verify_api_key)):
    """Return full WG config + all peers as JSON for backup"""
    try:
        # Get config file content
        config_content = ""
        try:
            with open(CONFIG_PATH, "r") as f:
                config_content = f.read()
        except Exception as e:
            config_content = f"# Error reading config: {e}"

        # Get all peers from runtime
        peers = wg_show_dump()

        return {
            "config": config_content,
            "config_path": CONFIG_PATH,
            "interface": INTERFACE,
            "peers": peers,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/restore")
async def restore_full(
    req: RestoreRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """Restore WG config and peers from backup data"""
    try:
        result = {"config_written": False, "peers_added": 0, "errors": []}

        # Write config file
        if req.config:
            try:
                with open(CONFIG_PATH, "w") as f:
                    f.write(req.config)
                os.chmod(CONFIG_PATH, 0o600)
                result["config_written"] = True
            except Exception as e:
                result["errors"].append(f"Config write failed: {e}")

        # Add peers
        for peer_data in req.peers:
            try:
                pub_key = peer_data.get("public_key")
                ipv4 = peer_data.get("ipv4", "")
                ipv6 = peer_data.get("ipv6")
                psk = peer_data.get("preshared_key")

                if not pub_key or not ipv4:
                    continue

                allowed_ips = f"{ipv4}/32"
                if ipv6:
                    allowed_ips += f",{ipv6}/128"

                wg_set_peer(pub_key, allowed_ips, psk)
                result["peers_added"] += 1
            except Exception as e:
                result["errors"].append(f"Peer {peer_data.get('name', '?')}: {e}")

        # Save config after adding peers
        if result["peers_added"] > 0:
            wg_save_config()

        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "VPN Manager Agent",
        "version": "1.3.0",
        "interface": INTERFACE,
        "status": "running"
    }

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("AGENT_PORT", "8001"))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
