"""
VPN Management Studio Timer Manager
Handles client expiry dates and automatic disabling
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from loguru import logger

from ..database.models import Client, Server, ClientStatus
from .wireguard import WireGuardManager


class TimerManager:
    """
    Manages client expiry timers
    Handles automatic disabling of expired clients
    """

    def __init__(
        self,
        db: Session,
        wg_manager: Optional[WireGuardManager] = None
    ):
        self.db = db
        self.wg_manager = wg_manager or WireGuardManager()

    def _get_wg(self, server: Server):
        """
        Create WireGuard manager for server (local or remote).

        Returns RemoteServerAdapter for remote servers (routes to SSH or Agent).
        Returns AmneziaWGManager/WireGuardManager for local servers (direct execution).
        """
        # Local server - use direct manager (AWG or standard WG)
        if not server.ssh_host:
            if getattr(server, 'server_type', 'wireguard') == 'amneziawg':
                from .amneziawg import AmneziaWGManager
                return AmneziaWGManager(
                    interface=server.interface,
                    config_path=server.config_path
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
    # TIMER OPERATIONS
    # ========================================================================

    def set_expiry(
        self,
        client_id: int,
        days: int,
        from_now: bool = True,
        extend: bool = False
    ) -> bool:
        """
        Set expiry date for a client

        Args:
            client_id: ID of the client
            days: Number of days (0 = remove expiry)
            from_now: If True, start from now; if False, start from current expiry
            extend: If True, add days to existing expiry; if False, replace

        Returns:
            True if successful
        """
        client = self.db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return False

        if days <= 0:
            # Remove expiry
            client.expiry_date = None
            self.db.commit()
            logger.info(f"Removed expiry for {client.name}")
            return True

        # Calculate new expiry date (guard against legacy naive datetimes in DB)
        def _aware(dt):
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        if extend and client.expiry_date:
            # Extend from current expiry
            base_date = max(_aware(client.expiry_date), datetime.now(timezone.utc))
            new_expiry = base_date + timedelta(days=days)
        elif not from_now and client.expiry_date and _aware(client.expiry_date) > datetime.now(timezone.utc):
            # Start from current expiry if it's in the future
            new_expiry = _aware(client.expiry_date) + timedelta(days=days)
        else:
            # Start from now
            new_expiry = datetime.now(timezone.utc) + timedelta(days=days)

        client.expiry_date = new_expiry
        self.db.commit()

        logger.info(f"Set expiry for {client.name}: {new_expiry.isoformat()}")
        return True

    def set_expiry_date(self, client_id: int, expiry_date: datetime) -> bool:
        """Set a specific expiry date for a client"""
        client = self.db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return False

        client.expiry_date = expiry_date
        self.db.commit()

        logger.info(f"Set expiry date for {client.name}: {expiry_date.isoformat()}")
        return True

    def remove_expiry(self, client_id: int) -> bool:
        """Remove expiry date from a client"""
        return self.set_expiry(client_id, 0)

    def extend_expiry(self, client_id: int, days: int) -> bool:
        """Extend expiry by adding days to current expiry"""
        return self.set_expiry(client_id, days, extend=True)

    # ========================================================================
    # EXPIRY INFO
    # ========================================================================

    def get_expiry_info(self, client_id: int) -> Optional[Dict]:
        """
        Get expiry information for a client

        Returns dict with:
            - expiry_date: datetime or None
            - days_left: int or None (negative if expired)
            - hours_left: int or None
            - is_expired: bool
            - display_text: str
        """
        client = self.db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return None

        if not client.expiry_date:
            return {
                "expiry_date": None,
                "days_left": None,
                "hours_left": None,
                "is_expired": False,
                "display_text": "No expiry",
            }

        now = datetime.now(timezone.utc)
        expiry = client.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        delta = expiry - now

        if delta.total_seconds() <= 0:
            return {
                "expiry_date": client.expiry_date,
                "days_left": 0,
                "hours_left": 0,
                "is_expired": True,
                "display_text": "Expired",
            }

        days_left = delta.days
        hours_left = int(delta.seconds / 3600)

        if days_left == 0:
            display_text = f"{hours_left}h left"
        elif days_left == 1:
            display_text = f"1 day left"
        else:
            display_text = f"{days_left} days left"

        return {
            "expiry_date": client.expiry_date,
            "days_left": days_left,
            "hours_left": hours_left,
            "is_expired": False,
            "display_text": display_text,
        }

    # ========================================================================
    # EXPIRY CHECKING
    # ========================================================================

    def check_expired_clients(self, reset_traffic: bool = True) -> List[Client]:
        """
        Check for expired clients and disable them

        Args:
            reset_traffic: Also reset traffic counter on expiry

        Returns:
            List of clients that were disabled
        """
        expired_clients = []
        now = datetime.now(timezone.utc)

        # Get all enabled clients with expiry dates.
        # Fix H-4: SELECT FOR UPDATE (skip_locked=True) prevents double-processing
        # when both the worker and the API run check_expired_clients concurrently.
        try:
            clients = self.db.query(Client).filter(
                and_(
                    Client.enabled == True,
                    Client.expiry_date != None,
                    Client.expiry_date <= now
                )
            ).with_for_update(skip_locked=True).all()
        except Exception:
            # Fallback for DBs that don't support FOR UPDATE (e.g. SQLite in tests)
            clients = self.db.query(Client).filter(
                and_(
                    Client.enabled == True,
                    Client.expiry_date != None,
                    Client.expiry_date <= now
                )
            ).all()

        proxy_servers_to_update: dict = {}  # server_id -> server object

        for client in clients:
            try:
                server = client.server

                # ── Proxy clients: no WireGuard peer to remove ──────────────────
                if client.is_proxy_client:
                    client.enabled = False
                    client.status = ClientStatus.EXPIRED
                    expired_clients.append(client)
                    if server:
                        proxy_servers_to_update[server.id] = server
                    logger.info(f"Client {client.name} disabled: timer expired (proxy)")
                    continue

                # ── WireGuard clients ────────────────────────────────────────────
                wg = self._get_wg(server) if server else self.wg_manager
                _wg_is_external = wg is not self.wg_manager

                # Fix H-5: separate WG removal from DB update so that DB is always
                # updated even if the WG peer removal fails (e.g. server unreachable).
                current_rx, current_tx = 0, 0
                wg_removal_ok = True
                try:
                    # Get traffic BEFORE removing peer (peer data is lost after removal)
                    if reset_traffic:
                        try:
                            current_rx, current_tx = wg.get_peer_transfer(client.public_key)
                        except Exception as _te:
                            logger.warning(f"Could not read traffic for {client.name} before expiry: {_te}")
                    wg.remove_peer(client.public_key)
                except Exception as e:
                    logger.warning(
                        f"WG peer removal failed for {client.name}: {e} "
                        f"— disabling in DB anyway (peer may remain active)"
                    )
                    wg_removal_ok = False
                finally:
                    if _wg_is_external:
                        wg.close()

                # Always update DB status — regardless of WG outcome
                client.enabled = False
                client.status = ClientStatus.EXPIRED

                # Apply saved traffic data
                if reset_traffic:
                    client.traffic_baseline_rx = current_rx
                    client.traffic_baseline_tx = current_tx
                    client.traffic_used_rx = 0
                    client.traffic_used_tx = 0
                    client.traffic_reset_date = now

                expired_clients.append(client)
                logger.info(
                    f"Client {client.name} disabled: timer expired"
                    + ("" if wg_removal_ok else " (WG removal failed)")
                )

            except Exception as e:
                logger.error(f"Failed to disable expired client {client.name}: {e}")

        if expired_clients:
            self.db.commit()
            # Re-apply proxy configs for all affected proxy servers
            if proxy_servers_to_update:
                from .client_manager import ClientManager
                cm = ClientManager(self.db)
                for srv in proxy_servers_to_update.values():
                    cm._apply_proxy_config(srv)

        return expired_clients

    def get_expiring_soon(
        self,
        within_days: int = 7,
        server_id: Optional[int] = None
    ) -> List[Client]:
        """Get clients expiring within the specified days"""
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(days=within_days)

        query = self.db.query(Client).filter(
            and_(
                Client.enabled == True,
                Client.expiry_date != None,
                Client.expiry_date > now,
                Client.expiry_date <= threshold
            )
        )

        if server_id:
            query = query.filter(Client.server_id == server_id)

        return query.order_by(Client.expiry_date).all()

    def get_expired_clients(self, server_id: Optional[int] = None) -> List[Client]:
        """Get all expired clients (whether disabled or not)"""
        now = datetime.now(timezone.utc)

        query = self.db.query(Client).filter(
            and_(
                Client.expiry_date != None,
                Client.expiry_date <= now
            )
        )

        if server_id:
            query = query.filter(Client.server_id == server_id)

        return query.order_by(Client.expiry_date).all()

    # ========================================================================
    # BULK OPERATIONS
    # ========================================================================

    def set_expiry_for_all(
        self,
        days: int,
        server_id: Optional[int] = None,
        only_without_expiry: bool = True
    ) -> int:
        """
        Set expiry for multiple clients

        Args:
            days: Days from now
            server_id: Optional filter by server
            only_without_expiry: Only set for clients without existing expiry

        Returns:
            Number of clients updated
        """
        query = self.db.query(Client).filter(Client.enabled == True)

        if server_id:
            query = query.filter(Client.server_id == server_id)

        if only_without_expiry:
            query = query.filter(Client.expiry_date == None)

        clients = query.all()
        new_expiry = datetime.now(timezone.utc) + timedelta(days=days)

        for client in clients:
            client.expiry_date = new_expiry

        self.db.commit()

        logger.info(f"Set expiry for {len(clients)} clients: {new_expiry.isoformat()}")
        return len(clients)

    def extend_expiry_for_all(
        self,
        days: int,
        server_id: Optional[int] = None
    ) -> int:
        """
        Extend expiry for all clients with existing expiry

        Returns:
            Number of clients updated
        """
        query = self.db.query(Client).filter(
            and_(
                Client.enabled == True,
                Client.expiry_date != None
            )
        )

        if server_id:
            query = query.filter(Client.server_id == server_id)

        clients = query.all()
        count = 0

        for client in clients:
            exp = client.expiry_date if client.expiry_date.tzinfo else client.expiry_date.replace(tzinfo=timezone.utc)
            base_date = max(exp, datetime.now(timezone.utc))
            client.expiry_date = base_date + timedelta(days=days)
            count += 1

        self.db.commit()

        logger.info(f"Extended expiry for {count} clients by {days} days")
        return count

    # ========================================================================
    # SUMMARY
    # ========================================================================

    def get_expiry_summary(self, server_id: Optional[int] = None) -> Dict:
        """Get summary of expiry status for all clients"""
        now = datetime.now(timezone.utc)

        query_base = self.db.query(Client).filter(Client.enabled == True)
        if server_id:
            query_base = query_base.filter(Client.server_id == server_id)

        total = query_base.count()

        no_expiry = query_base.filter(Client.expiry_date == None).count()

        expired = query_base.filter(Client.expiry_date <= now).count()

        expiring_today = query_base.filter(
            and_(
                Client.expiry_date > now,
                Client.expiry_date <= now + timedelta(days=1)
            )
        ).count()

        expiring_week = query_base.filter(
            and_(
                Client.expiry_date > now,
                Client.expiry_date <= now + timedelta(days=7)
            )
        ).count()

        expiring_month = query_base.filter(
            and_(
                Client.expiry_date > now,
                Client.expiry_date <= now + timedelta(days=30)
            )
        ).count()

        return {
            "total_clients": total,
            "no_expiry": no_expiry,
            "expired": expired,
            "expiring_today": expiring_today,
            "expiring_week": expiring_week,
            "expiring_month": expiring_month,
        }
