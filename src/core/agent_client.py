"""
VPN Management Studio Agent Client
HTTP client for communicating with remote agents
"""

from typing import Optional, List, Dict
import requests
from loguru import logger


class AgentClient:
    """
    HTTP client for Agent API
    Replaces SSH calls after agent is installed
    """

    def __init__(
        self,
        agent_url: str,
        api_key: str,
        timeout: int = 30
    ):
        """
        Args:
            agent_url: Agent API URL (e.g., "http://203.0.113.10:8001")
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        self.agent_url = agent_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key})

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to agent"""
        url = f"{self.agent_url}{endpoint}"
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Agent request failed: {method} {url} - {e}")
            raise

    def health_check(self) -> bool:
        """Check if agent is healthy"""
        try:
            response = self._request("GET", "/health")
            data = response.json()
            return data.get("status") == "healthy"
        except Exception:
            return False

    def get_stats(self) -> Optional[Dict]:
        """Get interface and peer statistics"""
        try:
            response = self._request("GET", "/stats")
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return None

    def create_peer(
        self,
        public_key: str,
        allowed_ips: str,
        preshared_key: Optional[str] = None
    ) -> bool:
        """Create or update peer"""
        try:
            self._request("POST", "/peer/create", json={
                "public_key": public_key,
                "allowed_ips": allowed_ips,
                "preshared_key": preshared_key
            })
            logger.debug(f"Peer created via agent: {public_key[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to create peer: {e}")
            return False

    def delete_peer(self, public_key: str) -> bool:
        """Delete peer"""
        try:
            self._request("POST", "/peer/delete", json={
                "public_key": public_key
            })
            logger.debug(f"Peer deleted via agent: {public_key[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to delete peer: {e}")
            return False

    def enable_peer(
        self,
        public_key: str,
        allowed_ips: str,
        preshared_key: Optional[str] = None
    ) -> bool:
        """Enable peer (add to WireGuard)"""
        try:
            self._request("POST", "/peer/enable", json={
                "public_key": public_key,
                "allowed_ips": allowed_ips,
                "preshared_key": preshared_key
            })
            logger.debug(f"Peer enabled via agent: {public_key[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to enable peer: {e}")
            return False

    def disable_peer(self, public_key: str) -> bool:
        """Disable peer (remove from WireGuard)"""
        try:
            self._request("POST", "/peer/disable", json={
                "public_key": public_key
            })
            logger.debug(f"Peer disabled via agent: {public_key[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to disable peer: {e}")
            return False

    def set_bandwidth(self, ip: str, limit_mbps: int, ip_index: int = 100, remove: bool = False) -> bool:
        """Set or remove bandwidth limit for peer"""
        try:
            self._request("POST", "/peer/set_bandwidth", json={
                "ip": ip,
                "limit_mbps": limit_mbps,
                "ip_index": ip_index,
                "remove": remove,
            })
            if remove:
                logger.debug(f"Bandwidth removed via agent: ip_index={ip_index}")
            else:
                logger.debug(f"Bandwidth set via agent: {ip} -> {limit_mbps} Mbps (class 1:{ip_index})")
            return True
        except Exception as e:
            logger.error(f"Failed to set bandwidth: {e}")
            return False

    def sync_bandwidth(self, limits: list) -> bool:
        """
        Sync bandwidth limits to desired state.
        Removes stale TC rules on the agent not present in limits,
        applies all provided limits.

        Args:
            limits: list of {"ip": str, "limit_mbps": int, "ip_index": int}
        """
        try:
            self._request("POST", "/bandwidth/sync", json={"limits": limits})
            logger.debug(f"Bandwidth synced via agent: {len(limits)} limits")
            return True
        except Exception as e:
            logger.error(f"Failed to sync bandwidth: {e}")
            return False

    # ========================================================================
    # CONFIG OPERATIONS
    # ========================================================================

    def save_config(self) -> bool:
        """Tell agent to save current WG state to config file"""
        try:
            self._request("POST", "/config/save")
            logger.debug("Config saved via agent")
            return True
        except Exception as e:
            logger.error(f"Failed to save config via agent: {e}")
            return False

    def write_config(self, content: str) -> bool:
        """Write config content to agent's config file"""
        try:
            self._request("POST", "/config/write", json={"content": content})
            logger.debug("Config written via agent")
            return True
        except Exception as e:
            logger.error(f"Failed to write config via agent: {e}")
            return False

    def read_config(self) -> Optional[str]:
        """Read config file from agent"""
        try:
            response = self._request("GET", "/config")
            data = response.json()
            return data.get("content")
        except Exception as e:
            logger.error(f"Failed to read config via agent: {e}")
            return None

    def close(self):
        """Close HTTP session"""
        self.session.close()
