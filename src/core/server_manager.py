"""
VPN Management Studio Server Manager
Handles WireGuard server configuration and management
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from loguru import logger
import os
import subprocess

from ..database.models import (
    Server,
    Client,
    ClientStatus,
    ServerStatus,
    ServerLifecycleStatus,
    map_lifecycle_to_legacy_status,
    map_legacy_status_to_lifecycle,
)
from .wireguard import WireGuardManager
from .amneziawg import AmneziaWGManager


# Global cache for server stats (shared across all ServerManager instances)
_GLOBAL_STATS_CACHE: Dict[int, Dict] = {}
_GLOBAL_STATS_CACHE_TIME: Dict[int, datetime] = {}
_STATS_CACHE_TTL = 30  # seconds


class ServerManager:
    """
    Manages WireGuard server configurations
    Supports multi-server setup
    """

    def __init__(self, db: Session):
        self.db = db

    def _is_proxy(self, server: Server) -> bool:
        """Return True if server is a proxy protocol (Hysteria2/TUIC)."""
        return getattr(server, 'server_category', None) == 'proxy' or \
               getattr(server, 'server_type', '') in ('hysteria2', 'tuic')

    def _get_proxy_manager(self, server: Server):
        """
        Create Hysteria2Manager or TUICManager for a proxy server.
        Returns the manager instance (caller must call .close() when done).
        """
        server_type = getattr(server, 'server_type', '')
        common = dict(
            config_path=server.proxy_config_path or f"/etc/{server_type}/config.{'yaml' if server_type == 'hysteria2' else 'json'}",
            service_name=server.proxy_service_name or ("hysteria-server" if server_type == "hysteria2" else "tuic-server"),
            listen_port=server.listen_port or (8443 if server_type == "hysteria2" else 8444),
            domain=server.proxy_domain,
            tls_mode=server.proxy_tls_mode or "self_signed",
            cert_path=server.proxy_cert_path or f"/etc/{server_type}/server.crt",
            key_path=server.proxy_key_path or f"/etc/{server_type}/server.key",
            ssh_host=server.ssh_host,
            ssh_port=server.ssh_port or 22,
            ssh_user=server.ssh_user or "root",
            ssh_password=server.ssh_password,
            ssh_private_key=server.ssh_private_key,
        )
        if server_type == "hysteria2":
            from .hysteria2 import Hysteria2Manager
            return Hysteria2Manager(**common, obfs_password=server.proxy_obfs_password,
                                    auth_password=server.proxy_auth_password)
        else:
            from .tuic import TUICManager
            return TUICManager(**{k: v for k, v in common.items() if k != "obfs_password"})

    def _get_wg(self, server: Server):
        """
        Create WireGuard/AmneziaWG manager for server (local or remote).
        """
        is_awg = getattr(server, 'server_type', 'wireguard') == 'amneziawg'

        # Local server
        if not server.ssh_host:
            if is_awg:
                return AmneziaWGManager(
                    interface=server.interface,
                    config_path=server.config_path,
                    jc=server.awg_jc,
                    jmin=server.awg_jmin,
                    jmax=server.awg_jmax,
                    s1=server.awg_s1,
                    s2=server.awg_s2,
                    h1=server.awg_h1,
                    h2=server.awg_h2,
                    h3=server.awg_h3,
                    h4=server.awg_h4,
                )
            return WireGuardManager(
                interface=server.interface,
                config_path=server.config_path
            )

        # Remote server - use RemoteServerAdapter (SSH or Agent mode)
        from .remote_adapter import RemoteServerAdapter
        return RemoteServerAdapter(
            server=server,
            interface=server.interface,
            config_path=server.config_path
        )

    # ========================================================================
    # CRUD OPERATIONS
    # ========================================================================

    def create_server(
        self,
        name: str,
        endpoint: str,
        public_key: str,
        private_key: str,
        interface: str = "wg0",
        listen_port: int = 51820,
        address_pool_ipv4: str = "10.66.66.0/24",
        address_pool_ipv6: Optional[str] = "fd42:42:42::/64",
        dns: str = "1.1.1.1,1.0.0.1",
        config_path: Optional[str] = None,
        max_clients: int = 250,
        description: Optional[str] = None,
        location: Optional[str] = None,
        ssh_host: Optional[str] = None,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_password: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
        server_type: str = "wireguard",
        awg_jc: Optional[int] = None,
        awg_jmin: Optional[int] = None,
        awg_jmax: Optional[int] = None,
        awg_s1: Optional[int] = None,
        awg_s2: Optional[int] = None,
        awg_h1: Optional[int] = None,
        awg_h2: Optional[int] = None,
        awg_h3: Optional[int] = None,
        awg_h4: Optional[int] = None,
        awg_mtu: Optional[int] = None,
        supports_peer_visibility: bool = True,
        split_tunnel_support: bool = False,
        ipv4_only: bool = False,
        # Proxy protocol fields
        server_category: Optional[str] = None,
        proxy_domain: Optional[str] = None,
        proxy_tls_mode: Optional[str] = None,
        proxy_cert_path: Optional[str] = None,
        proxy_key_path: Optional[str] = None,
        proxy_config_path: Optional[str] = None,
        proxy_service_name: Optional[str] = None,
        proxy_obfs_password: Optional[str] = None,
        proxy_auth_password: Optional[str] = None,
    ) -> Optional[Server]:
        """
        Create a new WireGuard server configuration

        Args:
            name: Unique server name
            endpoint: Public endpoint (ip:port)
            public_key: Server's public key
            private_key: Server's private key (will be encrypted)
            interface: WireGuard interface name (wg0, wg1, etc.)
            listen_port: Port to listen on
            address_pool_ipv4: IPv4 address pool (CIDR notation)
            address_pool_ipv6: IPv6 address pool (optional)
            dns: DNS servers for clients
            config_path: Path to WireGuard config file
            max_clients: Maximum number of clients
            description: Optional description
            location: Optional location string

        Returns:
            Created Server object or None on failure
        """
        # Check if server with same name exists
        existing = self.db.query(Server).filter(Server.name == name).first()
        if existing:
            logger.error(f"Server '{name}' already exists")
            return None

        # Check if interface is already used (skip for remote servers)
        if not ssh_host:
            interface_exists = self.db.query(Server).filter(
                Server.interface == interface,
                Server.ssh_host == None,
            ).first()
            if interface_exists:
                logger.error(f"Interface '{interface}' is already in use by {interface_exists.name}")
                return None

        # Determine category from type if not explicitly provided
        is_proxy = server_type in ("hysteria2", "tuic")
        if server_category is None:
            server_category = "proxy" if is_proxy else "vpn"

        if config_path is None:
            if server_type == "amneziawg":
                config_path = f"/etc/amnezia/amneziawg/{interface}.conf"
            elif is_proxy:
                config_path = proxy_config_path or f"/etc/{server_type}/config.{'yaml' if server_type == 'hysteria2' else 'json'}"
            else:
                config_path = f"/etc/wireguard/{interface}.conf"

        server = Server(
            name=name,
            interface=interface,
            endpoint=endpoint,
            listen_port=listen_port,
            public_key=public_key,
            private_key=private_key,
            address_pool_ipv4=address_pool_ipv4,
            address_pool_ipv6=address_pool_ipv6,
            dns=dns,
            config_path=config_path,
            max_clients=max_clients,
            status=ServerStatus.OFFLINE,
            lifecycle_status=ServerLifecycleStatus.OFFLINE.value,
            is_active=True,
            description=description,
            location=location,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            ssh_private_key=ssh_private_key,
            server_type=server_type,
            server_category=server_category,
            awg_jc=awg_jc,
            awg_jmin=awg_jmin,
            awg_jmax=awg_jmax,
            awg_s1=awg_s1,
            awg_s2=awg_s2,
            awg_h1=awg_h1,
            awg_h2=awg_h2,
            awg_h3=awg_h3,
            awg_h4=awg_h4,
            awg_mtu=awg_mtu,
            supports_peer_visibility=supports_peer_visibility,
            split_tunnel_support=split_tunnel_support,
            ipv4_only=ipv4_only,
            proxy_domain=proxy_domain,
            proxy_tls_mode=proxy_tls_mode,
            proxy_cert_path=proxy_cert_path,
            proxy_key_path=proxy_key_path,
            proxy_config_path=proxy_config_path,
            proxy_service_name=proxy_service_name,
            proxy_obfs_password=proxy_obfs_password,
            proxy_auth_password=proxy_auth_password,
        )

        try:
            self.db.add(server)
            self.db.commit()
            self.db.refresh(server)

            # For local servers, align initial status with the actual interface state.
            if not server.ssh_host:
                self.check_server_status(server.id)
                self.db.refresh(server)

            logger.info(f"Created server '{name}' with interface {interface}")
            return server

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create server: {e}")
            return None

    def get_server(self, server_id: int) -> Optional[Server]:
        """Get server by ID"""
        return self.db.query(Server).filter(Server.id == server_id).first()

    def get_server_by_name(self, name: str) -> Optional[Server]:
        """Get server by name"""
        return self.db.query(Server).filter(Server.name == name).first()

    def get_server_by_interface(self, interface: str) -> Optional[Server]:
        """Get server by interface name"""
        return self.db.query(Server).filter(Server.interface == interface).first()

    def get_all_servers(self, include_offline: bool = True) -> List[Server]:
        """Get all servers"""
        query = self.db.query(Server)

        if not include_offline:
            query = query.filter(Server.lifecycle_status == ServerLifecycleStatus.ONLINE.value)

        return query.order_by(Server.name).all()

    def update_server(
        self,
        server_id: int,
        **kwargs
    ) -> Optional[Server]:
        """
        Update server properties

        Allowed kwargs: name, endpoint, listen_port, dns, max_clients,
                       description, location, status
        """
        server = self.get_server(server_id)
        if not server:
            return None

        allowed_fields = {
            "name", "display_name", "endpoint", "listen_port", "dns", "max_clients",
            "description", "location", "status", "mtu", "persistent_keepalive",
            "max_bandwidth_mbps", "supports_peer_visibility", "split_tunnel_support",
            "ipv4_only", "is_active",
        }

        for key, value in kwargs.items():
            if key == "status" and value is not None:
                self._transition_status(server, value, "update_server")
            elif key in allowed_fields:
                setattr(server, key, value)

        try:
            self.db.commit()
            self.db.refresh(server)
            logger.info(f"Updated server {server.name}: {kwargs}")
            return server
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update server: {e}")
            return None

    def _transition_status(self, server: "Server", new_status: "ServerStatus | ServerLifecycleStatus | str", reason: str = "") -> None:
        """
        Single authority for all server status transitions.
        Logs each transition to the audit log and updates DB.
        All status mutations in ServerManager must go through here.
        """
        old_status = server.legacy_status
        old_lifecycle_status = server.effective_lifecycle_status

        if isinstance(new_status, ServerStatus):
            new_lifecycle_status = map_legacy_status_to_lifecycle(new_status)
            new_legacy_status = new_status
        else:
            lifecycle_value = new_status.value if isinstance(new_status, ServerLifecycleStatus) else str(new_status)
            new_lifecycle_status = ServerLifecycleStatus(lifecycle_value)
            new_legacy_status = map_lifecycle_to_legacy_status(new_lifecycle_status)

        if old_status == new_legacy_status and old_lifecycle_status == new_lifecycle_status.value:
            return  # no-op
        server.status = new_legacy_status
        server.lifecycle_status = new_lifecycle_status.value
        logger.info(
            "SERVER_STATUS_CHANGE server_id=%d name=%r legacy:%s→%s lifecycle:%s→%s reason=%r",
            server.id, server.name,
            old_status.value if old_status else "None",
            new_legacy_status.value,
            old_lifecycle_status,
            new_lifecycle_status.value,
            reason or "operation",
        )
        try:
            from ..database.models import AuditLog, AuditAction
            self.db.add(AuditLog(
                user_type="system",
                action=AuditAction.SERVER_STATUS_CHANGE,
                target_type="server",
                target_id=server.id,
                target_name=server.name,
                details={
                    "old_status": old_status.value if old_status else None,
                    "new_status": new_legacy_status.value,
                    "old_lifecycle_status": old_lifecycle_status,
                    "new_lifecycle_status": new_lifecycle_status.value,
                    "reason": reason or "operation",
                },
            ))
        except Exception as _ae:
            logger.debug("Could not write status-change audit log: %s", _ae)

    def delete_server(self, server_id: int, force: bool = False) -> bool:
        """
        Delete a server

        Args:
            server_id: ID of server to delete
            force: If True, delete even if has clients

        Returns:
            True if successful
        """
        server = self.get_server(server_id)
        if not server:
            return False

        # Block deletion while any client records remain unless force=True.
        # This project does not implement a deleted status; clients are hard-deleted.
        active_clients = self.db.query(Client).filter(
            Client.server_id == server_id
        ).all()

        if len(active_clients) > 0 and not force:
            logger.error(f"Cannot delete server with {len(active_clients)} active clients. Use force=True")
            return False

        try:
            all_clients = self.db.query(Client).filter(
                Client.server_id == server_id
            ).all()

            if self._is_proxy(server):
                # Proxy servers: stop, disable and remove the per-interface unit
                mgr = self._get_proxy_manager(server)
                try:
                    mgr.purge_service()
                except Exception as e:
                    logger.warning(f"Failed to purge proxy service for {server.name}: {e}")
                finally:
                    mgr.close()
            else:
                wg = self._get_wg(server)

                # Remove WG peers for all clients before deleting from DB
                wg_failures = []
                for client in all_clients:
                    try:
                        if client.public_key:
                            wg.remove_peer(client.public_key)
                    except Exception as e:
                        wg_failures.append(client.name)
                        logger.warning(f"Failed to remove WG peer for {client.name}: {e}")

                if wg_failures and not force:
                    wg.close()
                    logger.error(f"Cannot delete server: {len(wg_failures)} WG peer removals failed: {wg_failures}")
                    return False

                # Stop the interface if running
                try:
                    if wg.is_interface_up():
                        wg.stop_interface()
                except Exception as e:
                    logger.warning(f"Failed to stop interface: {e}")

                wg.close()

            # Uninstall agent from remote server if in agent mode
            if getattr(server, 'agent_mode', None) == 'agent' and server.ssh_host:
                try:
                    from .agent_bootstrap import AgentBootstrap
                    bootstrap = AgentBootstrap(
                        ssh_host=server.ssh_host,
                        ssh_port=server.ssh_port or 22,
                        ssh_user=server.ssh_user or "root",
                        ssh_password=server.ssh_password,
                        ssh_private_key_content=getattr(server, 'ssh_private_key', None),
                    )
                    bootstrap.uninstall_agent()
                    logger.info(f"Agent uninstalled from {server.name} during server deletion")
                except Exception as e:
                    logger.warning(f"Could not uninstall agent from {server.name} (best-effort): {e}")

            # Delete related records first (subscriptions, client-user links)
            from ..database.models import Subscription
            for client in all_clients:
                self.db.query(Subscription).filter(
                    Subscription.client_id == client.id
                ).delete()
            self.db.query(Client).filter(Client.server_id == server_id).delete()

            # Delete server
            self.db.delete(server)
            self.db.commit()

            logger.info(f"Deleted server '{server.name}' (removed {len(all_clients)} clients)")
            if 'wg_failures' in dir() and wg_failures:
                logger.warning(f"Note: {len(wg_failures)} WG peers may remain orphaned (force=True)")
            return True

        except Exception as e:
            self.db.rollback()
            try:
                if 'wg' in dir():
                    wg.close()
            except Exception:
                pass
            logger.error(f"Failed to delete server: {e}")
            return False

    # ========================================================================
    # SERVER STATUS
    # ========================================================================

    def check_server_status(self, server_id: int) -> ServerStatus:
        """Check and update server status"""
        server = self.get_server(server_id)
        if not server:
            return ServerStatus.ERROR

        if self._is_proxy(server):
            mgr = self._get_proxy_manager(server)
            try:
                active = mgr.is_service_active()
                self._transition_status(server, ServerStatus.ONLINE if active else ServerStatus.OFFLINE, "check_status")
            finally:
                mgr.close()
            self.db.commit()
            return server.legacy_status

        wg = self._get_wg(server)
        try:
            if wg.is_interface_up():
                self._transition_status(server, ServerStatus.ONLINE, "check_status")
            else:
                self._transition_status(server, ServerStatus.OFFLINE, "check_status")
        finally:
            wg.close()
        self.db.commit()
        return server.legacy_status

    def start_server(self, server_id: int) -> bool:
        """Start a server (WireGuard interface or proxy service)."""
        server = self.get_server(server_id)
        if not server:
            return False

        # Servers parked by license enforcement can't be brought back up
        # without a paid license. The route layer surfaces this as a
        # 403 with an Upgrade hint; in core we just refuse silently.
        from ..database.models import ServerLifecycleStatus
        if server.lifecycle_status == ServerLifecycleStatus.SUSPENDED_NO_LICENSE.value:
            from loguru import logger
            logger.info(
                "start_server refused: server id={} is suspended (no license)",
                server_id,
            )
            return False

        if self._is_proxy(server):
            mgr = self._get_proxy_manager(server)
            try:
                ok = mgr.start_service()
                self._transition_status(server, ServerStatus.ONLINE if ok else ServerStatus.ERROR, "start_server")
                self.db.commit()
                self.clear_stats_cache(server_id)
                return ok
            finally:
                mgr.close()

        # WG / AmneziaWG: make sure the on-disk config exists before
        # `wg-quick up` / `awg-quick up` runs, otherwise the start fails
        # with "config does not exist". Writing it every start is cheap
        # and idempotent, and it picks up new peers added since last start.
        try:
            self.save_server_config(server_id)
        except Exception as e:
            logger.warning(f"save_server_config before start failed: {e}")

        wg = self._get_wg(server)
        try:
            if wg.start_interface():
                self._transition_status(server, ServerStatus.ONLINE, "start_server")
                self.db.commit()
                self.clear_stats_cache(server_id)
                return True
            self._transition_status(server, ServerStatus.ERROR, "start_server:failed")
            self.db.commit()
            self.clear_stats_cache(server_id)
            return False
        finally:
            wg.close()

    def stop_server(self, server_id: int) -> bool:
        """Stop a server (WireGuard interface or proxy service)."""
        server = self.get_server(server_id)
        if not server:
            return False

        if self._is_proxy(server):
            mgr = self._get_proxy_manager(server)
            try:
                ok = mgr.stop_service()
                self._transition_status(server, ServerStatus.OFFLINE if ok else ServerStatus.ERROR, "stop_server")
                self.db.commit()
                self.clear_stats_cache(server_id)
                return ok
            finally:
                mgr.close()

        wg = self._get_wg(server)
        try:
            if wg.stop_interface():
                self._transition_status(server, ServerStatus.OFFLINE, "stop_server")
                self.db.commit()
                self.clear_stats_cache(server_id)
                return True
            self._transition_status(server, ServerStatus.ERROR, "stop_server:failed")
            self.db.commit()
            self.clear_stats_cache(server_id)
            return False
        finally:
            wg.close()

    def restart_server(self, server_id: int) -> bool:
        """Restart a server (WireGuard interface or proxy service)."""
        server = self.get_server(server_id)
        if not server:
            return False

        if self._is_proxy(server):
            mgr = self._get_proxy_manager(server)
            try:
                ok = mgr.restart_service()
                self._transition_status(server, ServerStatus.ONLINE if ok else ServerStatus.ERROR, "restart_server")
                self.db.commit()
                self.clear_stats_cache(server_id)
                return ok
            finally:
                mgr.close()

        stopped = self.stop_server(server_id)
        if not stopped:
            logger.warning(f"Stop failed for server {server_id}, attempting start anyway")
        result = self.start_server(server_id)
        self.clear_stats_cache(server_id)
        return result

    # ========================================================================
    # SERVER STATS
    # ========================================================================

    def get_server_stats(self, server_id: int, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get statistics for a server

        Args:
            server_id: Server ID
            force_refresh: Skip cache and fetch fresh data

        Returns:
            Server statistics dict or None
        """
        server = self.get_server(server_id)
        if not server:
            return None

        # Check cache (only for remote servers to avoid slow SSH connections)
        now = datetime.now(timezone.utc)
        if not force_refresh and server.ssh_host:
            if server_id in _GLOBAL_STATS_CACHE and server_id in _GLOBAL_STATS_CACHE_TIME:
                cache_age = (now - _GLOBAL_STATS_CACHE_TIME[server_id]).total_seconds()
                if cache_age < _STATS_CACHE_TTL:
                    logger.debug(f"Returning cached stats for server {server.name} (age: {cache_age:.1f}s)")
                    return _GLOBAL_STATS_CACHE[server_id]

        # Get client counts
        total_clients = self.db.query(Client).filter(
            Client.server_id == server_id
        ).count()

        active_clients = self.db.query(Client).filter(
            Client.server_id == server_id,
            Client.enabled == True
        ).count()

        # Get interface/service info
        total_rx = 0
        total_tx = 0

        if not self._is_proxy(server):
            wg = self._get_wg(server)
            try:
                wg_info = wg.get_interface_info()
                if wg_info and wg_info.get("peers_count", 0) > 0:
                    peers = wg.get_all_peers()
                    for peer in peers:
                        total_rx += peer.transfer_rx
                        total_tx += peer.transfer_tx
            finally:
                wg.close()

        stats = {
            "server_id": server_id,
            "name": server.name,
            "interface": server.interface,
            "status": server.legacy_status.value,
            "lifecycle_status": server.effective_lifecycle_status,
            "endpoint": server.endpoint,
            "total_clients": total_clients,
            "active_clients": active_clients,
            "max_clients": server.max_clients,
            "capacity_percent": (total_clients / server.max_clients * 100) if server.max_clients > 0 else 0,
            "total_rx": total_rx,
            "total_tx": total_tx,
            "total_traffic": total_rx + total_tx,
            "is_online": server.effective_lifecycle_status == ServerLifecycleStatus.ONLINE.value,
            "is_active": server.is_active,
        }

        # Cache results for remote servers
        if server.ssh_host:
            _GLOBAL_STATS_CACHE[server_id] = stats
            _GLOBAL_STATS_CACHE_TIME[server_id] = now
            logger.debug(f"Cached stats for remote server {server.name}")

        return stats

    def get_all_server_stats(self) -> List[Dict]:
        """Get stats for all servers"""
        servers = self.get_all_servers()
        return [self.get_server_stats(s.id) for s in servers]

    def clear_stats_cache(self, server_id: Optional[int] = None):
        """
        Clear cached stats for a server or all servers

        Args:
            server_id: Server ID to clear cache for, or None to clear all
        """
        if server_id is None:
            _GLOBAL_STATS_CACHE.clear()
            _GLOBAL_STATS_CACHE_TIME.clear()
            logger.debug("Cleared all stats cache")
        else:
            _GLOBAL_STATS_CACHE.pop(server_id, None)
            _GLOBAL_STATS_CACHE_TIME.pop(server_id, None)
            logger.debug(f"Cleared stats cache for server {server_id}")

    # ========================================================================
    # CONFIG GENERATION
    # ========================================================================

    def generate_server_config(self, server_id: int) -> Optional[str]:
        """Generate WireGuard/AmneziaWG server configuration file content"""
        server = self.get_server(server_id)
        if not server:
            return None

        # Get all enabled clients
        clients = self.db.query(Client).filter(
            Client.server_id == server_id,
            Client.enabled == True
        ).all()

        # Build peers list for config generators
        peers = []
        for client in clients:
            allowed_ips = f"{client.ipv4}/32"
            if client.ipv6:
                allowed_ips = f"{allowed_ips},{client.ipv6}/128"
            peers.append({
                "name": client.name,
                "public_key": client.public_key,
                "preshared_key": client.preshared_key,
                "allowed_ips": allowed_ips,
            })

        address = server.address_pool_ipv4.split("/")[0].rsplit(".", 1)[0] + ".1/24"
        if server.address_pool_ipv6:
            ipv6_addr = server.address_pool_ipv6.split("/")[0].rstrip(":") + "::1/64"
            address = f"{address},{ipv6_addr}"

        if getattr(server, "server_type", "wireguard") == "amneziawg":
            from src.core.amneziawg import AmneziaWGManager, AWG_DEFAULT_MTU
            mgr = AmneziaWGManager(
                interface=server.interface,
                jc=server.awg_jc or 4,
                jmin=server.awg_jmin or 50,
                jmax=server.awg_jmax or 100,
                s1=server.awg_s1 or 80,
                s2=server.awg_s2 or 40,
                h1=server.awg_h1 or 0,
                h2=server.awg_h2 or 0,
                h3=server.awg_h3 or 0,
                h4=server.awg_h4 or 0,
            )
            mtu = server.awg_mtu or AWG_DEFAULT_MTU
            return mgr.generate_server_config(
                private_key=server.private_key,
                address=address,
                listen_port=server.listen_port,
                mtu=mtu,
                peers=peers,
            )

        # Standard WireGuard
        # Auto-detect egress interface at PostUp time via shell substitution
        wg_subnet = server.address_pool_ipv4.split("/")[0].rsplit(".", 1)[0] + ".0/" + (server.address_pool_ipv4.split("/")[1] if "/" in server.address_pool_ipv4 else "24")
        config = (
            f"[Interface]\n"
            f"Address = {address}\n"
            f"ListenPort = {server.listen_port}\n"
            f"PrivateKey = {server.private_key}\n"
            f"PostUp = ETH=$(ip route | awk '/^default/{{print $5; exit}}'); "
            f"iptables -t nat -A POSTROUTING -s {wg_subnet} -o $ETH -j MASQUERADE; "
            f"iptables -A FORWARD -i {server.interface} -j ACCEPT; "
            f"iptables -A FORWARD -o {server.interface} -j ACCEPT; "
            f"ip route add {wg_subnet} dev {server.interface} 2>/dev/null || true\n"
            f"PostDown = ETH=$(ip route | awk '/^default/{{print $5; exit}}'); "
            f"iptables -t nat -D POSTROUTING -s {wg_subnet} -o $ETH -j MASQUERADE; "
            f"iptables -D FORWARD -i {server.interface} -j ACCEPT; "
            f"iptables -D FORWARD -o {server.interface} -j ACCEPT; "
            f"ip route del {wg_subnet} dev {server.interface} 2>/dev/null || true\n"
        )
        for peer in peers:
            config += f"\n[Peer]\n"
            if peer.get("name"):
                config += f"# {peer['name']}\n"
            config += f"PublicKey = {peer['public_key']}\n"
            if peer.get("preshared_key"):
                config += f"PresharedKey = {peer['preshared_key']}\n"
            config += f"AllowedIPs = {peer['allowed_ips']}\n"

        return config

    def save_server_config(self, server_id: int) -> bool:
        """Save server config to file"""
        server = self.get_server(server_id)
        if not server:
            return False

        config_content = self.generate_server_config(server_id)
        if not config_content:
            return False

        wg = self._get_wg(server)
        try:
            wg.write_config_file(config_content)
            logger.info(f"Saved config for server {server.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False
        finally:
            wg.close()

    # ========================================================================
    # AGENT MANAGEMENT (bootstrap layer using SSH)
    # ========================================================================

    def install_agent(
        self,
        server_id: int,
        agent_code_path: str = None,
        port: int = 8001
    ) -> bool:
        """
        Install agent on remote server using SSH bootstrap

        Args:
            server_id: Server ID
            agent_code_path: Path to agent.py on master server
            port: Agent API port

        Returns:
            Dict with installation result details
        """
        server = self.get_server(server_id)
        if not server:
            logger.error(f"Server {server_id} not found")
            return False

        if not server.ssh_host:
            logger.error(f"Server {server.name} is local, cannot install agent")
            return False

        # Note: agent_mode == "agent" guard removed intentionally.
        # Re-install is allowed; the route layer does a health-check guard.

        # Resolve agent.py path if not provided
        if not agent_code_path:
            agent_code_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "agent.py"
            )

        # Use SSH bootstrap to install agent
        from .agent_bootstrap import AgentBootstrap

        bootstrap = AgentBootstrap(
            ssh_host=server.ssh_host,
            ssh_port=server.ssh_port or 22,
            ssh_user=server.ssh_user or "root",
            ssh_password=server.ssh_password,
            ssh_private_key_content=getattr(server, 'ssh_private_key', None),
        )

        # Generate full server config so bootstrap can write it on fresh servers
        server_config_content = self.generate_server_config(server.id)

        try:
            success, agent_url, error_or_key = bootstrap.install_agent(
                agent_code_path=agent_code_path,
                interface=server.interface,
                port=port,
                server_config_content=server_config_content,
            )

            if success:
                server.agent_mode = "agent"
                server.agent_url = agent_url
                server.agent_api_key = error_or_key  # api_key on success
                self.db.commit()
                logger.info(f"EVENT:BOOTSTRAP_SUCCESS agent installed on {server.name}: {agent_url}")
                return True, None
            else:
                logger.error(f"EVENT:BOOTSTRAP_FAILURE agent install failed on {server.name}: {error_or_key}")
                return False, error_or_key

        except Exception as e:
            logger.error(f"EVENT:BOOTSTRAP_FAILURE agent install exception on server_id={server_id}: {e}")
            return False, str(e)

    def uninstall_agent(self, server_id: int) -> dict:
        """Uninstall agent from remote server"""
        server = self.get_server(server_id)
        if not server or not server.ssh_host:
            return False

        from .agent_bootstrap import AgentBootstrap

        bootstrap = AgentBootstrap(
            ssh_host=server.ssh_host,
            ssh_port=server.ssh_port or 22,
            ssh_user=server.ssh_user or "root",
            ssh_password=server.ssh_password,
            ssh_private_key_content=getattr(server, 'ssh_private_key', None),
        )

        try:
            if bootstrap.uninstall_agent():
                # Switch back to SSH mode
                server.agent_mode = "ssh"
                server.agent_url = None
                server.agent_api_key = None
                self.db.commit()

                logger.info(f"✅ Agent uninstalled from {server.name}")
                return True
            return False

        except Exception as e:
            logger.error(f"Agent uninstall failed: {e}")
            return False

    def switch_to_agent_mode(self, server_id: int) -> bool:
        """Switch server to agent mode (agent must be already installed)"""
        server = self.get_server(server_id)
        if not server or not server.ssh_host:
            return False

        if not server.agent_url or not server.agent_api_key:
            logger.error(f"Agent not installed on {server.name}")
            return False

        server.agent_mode = "agent"
        self.db.commit()
        logger.info(f"Switched {server.name} to agent mode")
        return True

    def switch_to_ssh_mode(self, server_id: int) -> bool:
        """Switch server to SSH mode (fallback/legacy)"""
        server = self.get_server(server_id)
        if not server:
            return False

        server.agent_mode = "ssh"
        self.db.commit()
        logger.info(f"Switched {server.name} to SSH mode")
        return True

    # ========================================================================
    # INITIALIZATION
    # ========================================================================

    def create_initial_server_from_config(
        self,
        name: str = "Main Server",
        config_path: str = "/etc/wireguard/wg0.conf",
        endpoint: str = "203.0.113.1:51820",
    ) -> Optional[Server]:
        """
        Create initial server from existing WireGuard config

        This is used during migration to create the first server entry
        from an existing WireGuard installation.
        """
        # Check if we already have a server with this interface
        if self.get_server_by_interface("wg0"):
            logger.warning("Server with wg0 interface already exists")
            return self.get_server_by_interface("wg0")

        # Generate or extract keys
        wg = WireGuardManager(interface="wg0", config_path=config_path)

        # Try to read existing config for public key
        if wg.is_interface_up():
            info = wg.get_interface_info()
            public_key = info.get("public_key") if info else None
        else:
            public_key = None

        if not public_key:
            # Generate new keys
            private_key, public_key = wg.generate_keypair()
        else:
            # We need the private key - try to read from config
            config_content = wg.read_config_file()
            private_key = None
            if config_content:
                for line in config_content.split("\n"):
                    if line.strip().startswith("PrivateKey"):
                        private_key = line.split("=")[1].strip()
                        break

            if not private_key:
                private_key, public_key = wg.generate_keypair()

        return self.create_server(
            name=name,
            endpoint=endpoint,
            public_key=public_key,
            private_key=private_key,
            interface="wg0",
            listen_port=51820,
            address_pool_ipv4="10.66.66.0/24",
            address_pool_ipv6="fd42:42:42::/64",
            dns="1.1.1.1,1.0.0.1",
            config_path=config_path,
            description="Main WireGuard server (migrated)",
        )

    def get_default_server(self) -> Optional[Server]:
        """Get the default server for auto-provisioning (is_default=True, falls back to first)"""
        default = self.db.query(Server).filter(Server.is_default == True).first()
        if default:
            return default
        return self.db.query(Server).order_by(Server.id).first()

    def set_default_server(self, server_id: int) -> bool:
        """Mark a server as default, clearing is_default on all others"""
        try:
            self.db.query(Server).update({Server.is_default: False})
            server = self.db.query(Server).filter(Server.id == server_id).first()
            if not server:
                self.db.rollback()
                return False
            server.is_default = True
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to set default server: {e}")
            return False
