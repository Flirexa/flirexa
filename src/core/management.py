"""
VPN Management Studio Management Core
Central manager that coordinates all subsystems
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger
import asyncio
import threading

from .client_manager import ClientManager
from .server_manager import ServerManager
from .traffic_manager import TrafficManager
from .timer_manager import TimerManager
from .wireguard import WireGuardManager

from ..database.models import (
    Client, Server, AuditLog, AuditAction,
    ClientStatus, ServerStatus
)


class ManagementCore:
    """
    Central management core

    This class provides a unified interface to all management operations.
    It coordinates between ClientManager, ServerManager, TrafficManager,
    and TimerManager to ensure consistent state.

    Usage:
        with get_db_context() as db:
            core = ManagementCore(db)
            client = core.create_client("MyPhone", server_id=1)
    """

    def __init__(self, db: Session):
        """
        Initialize Management Core

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

        # Initialize managers
        self.wg_manager = WireGuardManager()
        self.clients = ClientManager(db, self.wg_manager)
        self.servers = ServerManager(db)
        self.traffic = TrafficManager(db, self.wg_manager)
        self.timers = TimerManager(db, self.wg_manager)

        # Background task state
        self._monitor_task = None
        self._monitor_running = False

    # ========================================================================
    # CLIENT OPERATIONS (Convenience methods)
    # ========================================================================

    def create_client(
        self,
        name: str,
        server_id: Optional[int] = None,
        bandwidth_limit: Optional[int] = None,
        traffic_limit_mb: Optional[int] = None,
        expiry_days: Optional[int] = None,
        telegram_user_id: Optional[int] = None,
        peer_visibility: bool = False,
    ) -> Optional[Client]:
        """
        Create a new VPN client

        Args:
            name: Client name
            server_id: Server ID (uses default if not specified)
            bandwidth_limit: Speed limit in Mbps
            traffic_limit_mb: Traffic limit in MB
            expiry_days: Days until expiry
            telegram_user_id: Optional linked Telegram user

        Returns:
            Created Client or None on failure
        """
        # Get default server if not specified
        if server_id is None:
            default_server = self.servers.get_default_server()
            if not default_server:
                logger.error("No servers configured")
                return None
            server_id = default_server.id

        # Create client
        client = self.clients.create_client(
            name=name,
            server_id=server_id,
            bandwidth_limit=bandwidth_limit,
            traffic_limit_mb=traffic_limit_mb,
            expiry_days=expiry_days,
            telegram_user_id=telegram_user_id,
            peer_visibility=peer_visibility,
        )

        if client:
            # Apply bandwidth limit if specified
            if bandwidth_limit and bandwidth_limit > 0:
                server = self.servers.get_server(server_id)
                if server:
                    self.traffic.set_bandwidth_limit(
                        client.id,
                        bandwidth_limit,
                        server.interface
                    )

            # Log the action
            self._log_action(
                action=AuditAction.CLIENT_CREATE,
                target_type="client",
                target_id=client.id,
                target_name=client.name,
                details={"server_id": server_id}
            )

        return client

    def get_client(self, client_id: int) -> Optional[Client]:
        """Get a client by ID"""
        return self.clients.get_client(client_id)

    def get_client_by_name(self, name: str) -> Optional[Client]:
        """Get a client by name"""
        return self.clients.get_client_by_name(name)

    def get_all_clients(self, server_id: Optional[int] = None) -> List[Client]:
        """Get all clients"""
        return self.clients.get_all_clients(server_id=server_id)

    def delete_client(self, client_id: int) -> bool:
        """Delete a client"""
        client = self.clients.get_client(client_id)
        if not client:
            return False

        client_name = client.name
        result = self.clients.delete_client(client_id)

        if result:
            self._log_action(
                action=AuditAction.CLIENT_DELETE,
                target_type="client",
                target_id=client_id,
                target_name=client_name,
            )

        return result

    def enable_client(self, client_id: int) -> bool:
        """Enable a client"""
        result = self.clients.enable_client(client_id)

        if result:
            client = self.clients.get_client(client_id)
            self._log_action(
                action=AuditAction.CLIENT_ENABLE,
                target_type="client",
                target_id=client_id,
                target_name=client.name if client else None,
            )

        return result

    def disable_client(self, client_id: int, reason: Optional[str] = None) -> bool:
        """Disable a client"""
        result = self.clients.disable_client(client_id, reason)

        if result:
            client = self.clients.get_client(client_id)
            self._log_action(
                action=AuditAction.CLIENT_DISABLE,
                target_type="client",
                target_id=client_id,
                target_name=client.name if client else None,
                details={"reason": reason}
            )

        return result

    def get_client_config(self, client_id: int) -> Optional[str]:
        """Get client configuration file content"""
        return self.clients.get_client_config(client_id)

    # ========================================================================
    # TRAFFIC OPERATIONS
    # ========================================================================

    def set_bandwidth_limit(self, client_id: int, bandwidth_mbps: int) -> bool:
        """Set bandwidth limit for a client"""
        client = self.clients.get_client(client_id)
        if not client:
            return False

        server = client.server
        result = self.traffic.set_bandwidth_limit(
            client_id,
            bandwidth_mbps,
            server.interface if server else "wg0"
        )

        if result:
            # Also update client record
            self.clients.update_client(client_id, bandwidth_limit=bandwidth_mbps if bandwidth_mbps > 0 else None)

        return result

    def set_traffic_limit(
        self,
        client_id: int,
        limit_mb: int,
        duration_days: int = 0,
        sync_with_expiry: bool = False
    ) -> bool:
        """Set traffic limit for a client"""
        return self.traffic.set_traffic_limit(
            client_id,
            limit_mb,
            duration_days,
            sync_with_expiry
        )

    def reset_traffic_counter(self, client_id: int) -> bool:
        """Reset traffic counter for a client"""
        result = self.traffic.reset_traffic_counter(client_id)

        if result:
            client = self.clients.get_client(client_id)
            self._log_action(
                action=AuditAction.CLIENT_TRAFFIC_RESET,
                target_type="client",
                target_id=client_id,
                target_name=client.name if client else None,
            )

        return result

    def get_client_traffic(self, client_id: int):
        """Get traffic statistics for a client"""
        client = self.clients.get_client(client_id)
        if not client:
            return None
        return self.traffic.get_client_traffic(client)

    # ========================================================================
    # TIMER OPERATIONS
    # ========================================================================

    def set_expiry(self, client_id: int, days: int) -> bool:
        """Set expiry timer for a client"""
        return self.timers.set_expiry(client_id, days)

    def extend_expiry(self, client_id: int, days: int) -> bool:
        """Extend expiry timer for a client"""
        return self.timers.extend_expiry(client_id, days)

    def remove_expiry(self, client_id: int) -> bool:
        """Remove expiry timer from a client"""
        return self.timers.remove_expiry(client_id)

    def get_expiry_info(self, client_id: int) -> Optional[Dict]:
        """Get expiry information for a client"""
        return self.timers.get_expiry_info(client_id)

    # ========================================================================
    # SERVER OPERATIONS
    # ========================================================================

    def get_server(self, server_id: int) -> Optional[Server]:
        """Get a server by ID"""
        return self.servers.get_server(server_id)

    def get_all_servers(self) -> List[Server]:
        """Get all servers"""
        return self.servers.get_all_servers()

    def get_server_stats(self, server_id: int) -> Optional[Dict]:
        """Get statistics for a server"""
        return self.servers.get_server_stats(server_id)

    def start_server(self, server_id: int) -> bool:
        """Start a WireGuard server"""
        return self.servers.start_server(server_id)

    def stop_server(self, server_id: int) -> bool:
        """Stop a WireGuard server"""
        return self.servers.stop_server(server_id)

    # ========================================================================
    # MONITORING
    # ========================================================================

    def check_all_limits(self) -> Dict:
        """
        Check all limits (expiry and traffic) and disable violating clients

        Returns:
            Dict with lists of disabled clients
        """
        # Sync live WG traffic counters to DB first (makes DB values accurate)
        self.traffic.sync_traffic_to_db()

        expired = self.timers.check_expired_clients()
        traffic_exceeded = self.traffic.check_traffic_limits()

        # Check auto-rules (apply/remove bandwidth limits based on usage)
        rules_affected = self.traffic.check_traffic_rules()

        # Cleanup old daily records periodically (once a day check is enough)
        self.traffic.cleanup_old_daily_records()

        return {
            "expired_clients": [c.name for c in expired],
            "traffic_exceeded_clients": [c.name for c in traffic_exceeded],
            "rules_affected": rules_affected,
            "total_disabled": len(expired) + len(traffic_exceeded),
        }

    def start_monitoring(self, interval_seconds: int = 60) -> None:
        """
        Start background monitoring thread

        Periodically checks expiry and traffic limits
        """
        if self._monitor_running:
            logger.warning("Monitoring already running")
            return

        self._monitor_running = True

        def monitor_loop():
            while self._monitor_running:
                try:
                    result = self.check_all_limits()
                    if result["total_disabled"] > 0:
                        logger.info(f"Monitoring: disabled {result['total_disabled']} clients")
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")

                # Sleep in small intervals to allow quick shutdown
                for _ in range(interval_seconds):
                    if not self._monitor_running:
                        break
                    import time
                    time.sleep(1)

        self._monitor_task = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_task.start()
        logger.info(f"Started monitoring (interval: {interval_seconds}s)")

    def stop_monitoring(self) -> None:
        """Stop background monitoring"""
        self._monitor_running = False
        if self._monitor_task:
            self._monitor_task.join(timeout=5)
        logger.info("Stopped monitoring")

    # ========================================================================
    # SYSTEM STATUS
    # ========================================================================

    def get_system_status(self) -> Dict:
        """Get overall system status"""
        servers = self.get_all_servers()

        # Count clients from database (fast, no SSH)
        from ..database.models import Client
        total_clients = self.db.query(Client).count()
        active_clients = self.db.query(Client).filter(Client.enabled == True).count()

        # Count online servers from database (fast, no SSH)
        online_servers = sum(1 for s in servers if getattr(s, "effective_lifecycle_status", None) == "online")

        expiry_summary = self.timers.get_expiry_summary()

        # Get traffic summary from database (fast, no SSH)
        # Avoid calling get_traffic_summary() as it triggers SSH for all remote clients
        from ..database.models import Client
        clients_with_traffic = self.db.query(Client).filter(Client.enabled == True).all()
        total_rx = sum(c.traffic_used_rx or 0 for c in clients_with_traffic)
        total_tx = sum(c.traffic_used_tx or 0 for c in clients_with_traffic)
        exceeded_count = sum(1 for c in clients_with_traffic if c.traffic_limit_mb and (c.traffic_used_rx + c.traffic_used_tx) > c.traffic_limit_mb * 1024 * 1024)

        traffic_summary = {
            "total_clients": len(clients_with_traffic),
            "total_rx": total_rx,
            "total_rx_formatted": self.traffic.format_bytes(total_rx),
            "total_tx": total_tx,
            "total_tx_formatted": self.traffic.format_bytes(total_tx),
            "total": total_rx + total_tx,
            "total_formatted": self.traffic.format_bytes(total_rx + total_tx),
            "exceeded_count": exceeded_count,
            "warning_count": 0,  # Skip warning calculation for speed
        }

        return {
            "servers": {
                "total": len(servers),
                "online": online_servers,
                "offline": len(servers) - online_servers,
            },
            "clients": {
                "total": total_clients,
                "active": active_clients,
                "disabled": total_clients - active_clients,
            },
            "expiry": expiry_summary,
            "traffic": traffic_summary,
            "timestamp": datetime.now().isoformat(),
        }

    # ========================================================================
    # AUDIT LOGGING
    # ========================================================================

    def _log_action(
        self,
        action: AuditAction,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        target_name: Optional[str] = None,
        details: Optional[Dict] = None,
        user_id: Optional[int] = None,
        user_type: str = "admin",
    ) -> None:
        """Log an action to the audit log"""
        try:
            log = AuditLog(
                user_id=user_id,
                user_type=user_type,
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                details=details,
            )
            self.db.add(log)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {e}")

    def get_audit_logs(
        self,
        limit: int = 100,
        action: Optional[AuditAction] = None,
        target_type: Optional[str] = None,
    ) -> List[AuditLog]:
        """Get recent audit logs"""
        query = self.db.query(AuditLog)

        if action:
            query = query.filter(AuditLog.action == action)

        if target_type:
            query = query.filter(AuditLog.target_type == target_type)

        return query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    # ========================================================================
    # CLIENT INFO (COMBINED)
    # ========================================================================

    def get_client_full_info(self, client_id: int) -> Optional[Dict]:
        """
        Get complete information about a client

        Combines client data, traffic stats, expiry info, and last handshake
        """
        client = self.clients.get_client(client_id)
        if not client:
            return None

        traffic = self.traffic.get_client_traffic(client)
        expiry = self.timers.get_expiry_info(client_id)

        # Use server-specific WG manager for handshake
        server = client.server
        if server and server.ssh_host:
            from .remote_adapter import RemoteServerAdapter
            wg = RemoteServerAdapter(
                server=server,
                interface=server.interface,
                config_path=server.config_path
            )
            try:
                last_handshake = wg.get_peer_latest_handshake(client.public_key)
            finally:
                wg.close()
        elif server:
            # Local server — use server-specific interface (AWG or WG)
            if getattr(server, 'server_type', 'wireguard') == 'amneziawg':
                from .amneziawg import AmneziaWGManager
                wg = AmneziaWGManager(interface=server.interface, config_path=server.config_path)
            else:
                wg = WireGuardManager(interface=server.interface, config_path=server.config_path)
            last_handshake = wg.get_peer_latest_handshake(client.public_key)
        else:
            last_handshake = self.wg_manager.get_peer_latest_handshake(client.public_key)

        return {
            "id": client.id,
            "name": client.name,
            "ipv4": client.ipv4,
            "ipv6": client.ipv6,
            "enabled": client.enabled,
            "status": client.status.value,
            "server_id": client.server_id,
            "server_name": client.server.name if client.server else None,
            "bandwidth_limit": client.bandwidth_limit,
            "traffic": {
                "rx_bytes": traffic.rx_bytes,
                "tx_bytes": traffic.tx_bytes,
                "total_bytes": traffic.total_bytes,
                "limit_mb": client.traffic_limit_mb,
                "percent_used": traffic.percent_used,
                "is_exceeded": traffic.is_exceeded,
                "rx_formatted": self.traffic.format_bytes(traffic.rx_bytes),
                "tx_formatted": self.traffic.format_bytes(traffic.tx_bytes),
                "total_formatted": self.traffic.format_bytes(traffic.total_bytes),
            },
            "expiry": expiry,
            "last_handshake": last_handshake.isoformat() if last_handshake else None,
            "created_at": client.created_at.isoformat() if client.created_at else None,
        }

    def get_all_clients_info(self, server_id: Optional[int] = None) -> List[Dict]:
        """Get info for all clients"""
        clients = self.get_all_clients(server_id=server_id)
        return [self.get_client_full_info(c.id) for c in clients]
