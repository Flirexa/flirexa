"""
VPN Management Studio Client Portal — HTTP client for calling Admin API internal endpoints.
Used by client portal to manage WireGuard clients without direct DB/core access.
"""

import logging
from typing import Optional, List, Dict, Any

import httpx

logger = logging.getLogger(__name__)


class AdminAPIClient:
    """HTTP client for Admin API internal endpoints"""

    def __init__(self, base_url: str, service_token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"X-Service-Token": self.service_token}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/internal{path}"

    async def create_client(
        self,
        name: str,
        server_id: Optional[int] = None,
        bandwidth_limit: Optional[int] = None,
        traffic_limit_mb: Optional[int] = None,
        expiry_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a WireGuard client via admin API"""
        payload = {"name": name}
        if server_id is not None:
            payload["server_id"] = server_id
        if bandwidth_limit is not None:
            payload["bandwidth_limit"] = bandwidth_limit
        if traffic_limit_mb is not None:
            payload["traffic_limit_mb"] = traffic_limit_mb
        if expiry_days is not None:
            payload["expiry_days"] = expiry_days

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self._url("/clients"),
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to create client via admin API: {e}")
            return None

    async def get_clients_by_ids(self, ids: List[int]) -> List[Dict[str, Any]]:
        """Get WireGuard clients by list of IDs"""
        if not ids:
            return []

        ids_str = ",".join(str(i) for i in ids)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self._url("/clients/by-ids"),
                    params={"ids": ids_str},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to get clients by IDs via admin API: {e}")
            return []

    async def get_client_config(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Get WireGuard config for a client"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self._url(f"/clients/{client_id}/config"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to get client config via admin API: {e}")
            return None

    async def get_client_qrcode(self, client_id: int) -> Optional[bytes]:
        """Get QR code PNG bytes for a client"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self._url(f"/clients/{client_id}/qrcode"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.error(f"Failed to get client QR code via admin API: {e}")
            return None

    async def delete_client(self, client_id: int) -> bool:
        """Delete a WireGuard client via admin API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.delete(
                    self._url(f"/clients/{client_id}"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to delete client via admin API: {e}")
            return False

    async def update_client_limits(
        self,
        client_id: int,
        bandwidth_limit: Optional[int] = None,
        traffic_limit_mb: Optional[int] = None,
        expiry_date: Optional[str] = None,
        enabled: Optional[bool] = None,
        status: Optional[str] = None,
        reset_traffic: bool = False,
    ) -> bool:
        """Update limits on a WireGuard client"""
        payload = {}
        if bandwidth_limit is not None:
            payload["bandwidth_limit"] = bandwidth_limit
        if traffic_limit_mb is not None:
            payload["traffic_limit_mb"] = traffic_limit_mb
        if expiry_date is not None:
            payload["expiry_date"] = expiry_date
        if enabled is not None:
            payload["enabled"] = enabled
        if status is not None:
            payload["status"] = status
        if reset_traffic:
            payload["reset_traffic"] = True

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.put(
                    self._url(f"/clients/{client_id}/limits"),
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to update client limits via admin API: {e}")
            return False

    async def get_default_server(self) -> Optional[Dict[str, Any]]:
        """Get default server info"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self._url("/servers/default"),
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"Failed to get default server via admin API: {e}")
            return None
