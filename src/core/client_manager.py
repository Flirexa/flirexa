"""
Flirexa Client Manager
Handles all client/peer CRUD operations
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, text
from loguru import logger

from ..database.models import Client, Server, ClientStatus
from .wireguard import WireGuardManager
from .amneziawg import AmneziaWGManager

class ClientManager:
    """
    Manages WireGuard client operations
    All client CRUD logic is centralized here
    """

    def __init__(
        self,
        db: Session,
        wg_manager: Optional[WireGuardManager] = None
    ):
        self.db = db
        self.wg_manager = wg_manager or WireGuardManager()

    def _get_wg(self, server: 'Server'):
        """
        Create WireGuard/AmneziaWG manager for server (local or remote).

        Returns RemoteServerAdapter for remote servers (routes to SSH or Agent).
        Returns AmneziaWGManager/WireGuardManager for local servers (direct execution).
        """
        is_awg = getattr(server, 'server_type', 'wireguard') == 'amneziawg'

        # Local server - use direct manager
        is_remote = bool(server.ssh_host) or (
            (getattr(server, "agent_mode", None) or "") == "mikrotik"
        )
        if not is_remote:
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

        from ..modules.remote_client_adapter import create_remote_manager

        return create_remote_manager(server)

    # ========================================================================
    # CRUD OPERATIONS
    # ========================================================================

    def create_client(
        self,
        name: str,
        server_id: int,
        bandwidth_limit: Optional[int] = None,
        traffic_limit_mb: Optional[int] = None,
        expiry_days: Optional[int] = None,
        telegram_user_id: Optional[int] = None,
        peer_visibility: bool = False,
        # Proxy auth (auto-generated if omitted)
        proxy_password: Optional[str] = None,
        proxy_uuid: Optional[str] = None,
    ) -> Optional[Client]:
        """
        Create a new WireGuard client

        Args:
            name: Client name (unique per server)
            server_id: ID of the server to add client to
            bandwidth_limit: Speed limit in Mbps (None = unlimited)
            traffic_limit_mb: Traffic limit in MB (None = unlimited)
            expiry_days: Days until expiry (None = no expiry)
            telegram_user_id: Optional Telegram user ID to link

        Returns:
            Created Client object or None on failure
        """
        # Get server
        server = self.db.query(Server).filter(Server.id == server_id).first()
        if not server:
            logger.error(f"Server {server_id} not found")
            return None

        # Route proxy clients to their own creation flow
        server_category = getattr(server, 'server_category', None)
        server_type = getattr(server, 'server_type', 'wireguard')
        if server_category == 'proxy' or server_type in ('hysteria2', 'tuic'):
            return self._create_proxy_client(
                name=name,
                server=server,
                bandwidth_limit=bandwidth_limit,
                traffic_limit_mb=traffic_limit_mb,
                expiry_days=expiry_days,
                telegram_user_id=telegram_user_id,
                proxy_password=proxy_password,
                proxy_uuid=proxy_uuid,
            )

        # ── VPN (WireGuard / AmneziaWG) path ─────────────────────────────────

        # Enforce supports_peer_visibility at the server level
        if peer_visibility and not getattr(server, 'supports_peer_visibility', True):
            logger.warning(
                f"Server '{server.name}' does not support peer_visibility — disabling for client '{name}'"
            )
            peer_visibility = False

        # Check if name already exists on this server
        existing = self.db.query(Client).filter(
            and_(Client.server_id == server_id, Client.name == name)
        ).first()
        if existing:
            logger.error(f"Client '{name}' already exists on server {server_id}")
            return None

        # Find next available IP
        ip_index = self._get_next_available_ip(server_id, server.address_pool_ipv4)
        if ip_index is None:
            logger.error("No available IP addresses")
            return None

        # Generate keys
        private_key, public_key = self.wg_manager.generate_keypair()
        preshared_key = self.wg_manager.generate_preshared_key()

        # Calculate IPs from CIDR. ip_index is the host offset into the
        # pool (1 = first usable, 2 = second, …). Computing through
        # ipaddress.IPv4Network correctly handles any prefix length —
        # the old `{base.octets}.{ip_index}` arithmetic only worked
        # for /24 and silently produced bad addresses on larger pools.
        #
        # Storage convention: clients.ipv4 / .ipv6 hold the bare address
        # WITHOUT any /32 or /128 suffix. Every callsite that needs CIDR
        # form already does `f"{client.ipv4}/32"` around the read. Writing
        # /32 here would give those callsites a double-suffixed string
        # ("172.27.0.7/32/32") which AmneziaWG / WireGuard apps reject.
        import ipaddress as _ipaddress
        net4 = _ipaddress.IPv4Network(server.address_pool_ipv4, strict=False)
        ipv4 = str(net4.network_address + ip_index)

        ipv6 = None
        if server.address_pool_ipv6:
            try:
                net6 = _ipaddress.IPv6Network(server.address_pool_ipv6, strict=False)
                ipv6 = str(net6.network_address + ip_index)
            except Exception:
                ipv6 = None

        # Calculate expiry date
        expiry_date = None
        if expiry_days and expiry_days > 0:
            expiry_date = datetime.now(timezone.utc) + timedelta(days=expiry_days)

        # Create client record
        client = Client(
            name=name,
            server_id=server_id,
            public_key=public_key,
            private_key=private_key,
            preshared_key=preshared_key,
            ip_index=ip_index,
            ipv4=ipv4.replace("/32", ""),
            ipv6=ipv6.replace("/128", "") if ipv6 else None,
            status=ClientStatus.ACTIVE,
            enabled=True,
            bandwidth_limit=bandwidth_limit,
            traffic_limit_mb=traffic_limit_mb,
            expiry_date=expiry_date,
            telegram_user_id=telegram_user_id,
            peer_visibility=peer_visibility,
        )

        try:
            # Add peer to WireGuard FIRST (before DB commit). Storage holds
            # the bare address; `wg set peer … allowed-ips` needs CIDR form.
            allowed_ips = [f"{ipv4}/32"]
            if ipv6:
                allowed_ips.append(f"{ipv6}/128")

            wg = self._get_wg(server)
            try:
                peer_added = wg.add_peer(
                    public_key=public_key,
                    allowed_ips=allowed_ips,
                    preshared_key=preshared_key
                )
            finally:
                wg.close()

            if peer_added is False:
                logger.error(f"Failed to add peer to WireGuard on server {server.name}")
                return None

            self.db.add(client)
            self.db.commit()
            self.db.refresh(client)

            logger.info(f"Created VPN client '{name}' with IP {client.ipv4}")
            return client

        except Exception as e:
            self.db.rollback()
            try:
                wg = self._get_wg(server)
                wg.remove_peer(public_key)
                wg.close()
            except Exception:
                logger.warning(f"Failed to cleanup WG peer for {name} after DB error")
            logger.error(f"Failed to create client: {e}")
            return None

    def _create_proxy_client(
        self,
        name: str,
        server: Server,
        bandwidth_limit: Optional[int] = None,
        traffic_limit_mb: Optional[int] = None,
        expiry_days: Optional[int] = None,
        telegram_user_id: Optional[int] = None,
        proxy_password: Optional[str] = None,
        proxy_uuid: Optional[str] = None,
    ) -> Optional[Client]:
        from ..modules.proxy_client_adapter import create_proxy_client

        return create_proxy_client(
            self,
            name=name,
            server=server,
            bandwidth_limit=bandwidth_limit,
            traffic_limit_mb=traffic_limit_mb,
            expiry_days=expiry_days,
            telegram_user_id=telegram_user_id,
            proxy_password=proxy_password,
            proxy_uuid=proxy_uuid,
        )

    def _apply_proxy_config(self, server: Server) -> bool:
        from ..modules.proxy_client_adapter import apply_proxy_config

        return apply_proxy_config(self, server)

    def get_client(self, client_id: int) -> Optional[Client]:
        """Get a client by ID"""
        return self.db.query(Client).filter(Client.id == client_id).first()

    def get_client_by_name(self, name: str, server_id: Optional[int] = None) -> Optional[Client]:
        """Get a client by name (and optionally server)"""
        query = self.db.query(Client).filter(Client.name == name)
        if server_id:
            query = query.filter(Client.server_id == server_id)
        return query.first()

    def get_client_by_public_key(self, public_key: str) -> Optional[Client]:
        """
        Get a WireGuard client by public key.
        Proxy clients (NULL public_key) are never returned here.
        """
        if not public_key:
            return None
        return self.db.query(Client).filter(
            Client.public_key == public_key,
            Client.public_key.isnot(None),
        ).first()

    def get_all_clients(
        self,
        server_id: Optional[int] = None,
        enabled_only: bool = False,
        include_expired: bool = True,
    ) -> List[Client]:
        """Get all clients with optional filters"""
        query = self.db.query(Client)

        if server_id:
            query = query.filter(Client.server_id == server_id)

        if enabled_only:
            query = query.filter(Client.enabled == True)

        if not include_expired:
            query = query.filter(
                or_(
                    Client.expiry_date == None,
                    Client.expiry_date > datetime.now(timezone.utc)
                )
            )

        return query.order_by(Client.name).all()

    def update_client(
        self,
        client_id: int,
        **kwargs
    ) -> Optional[Client]:
        """
        Update client properties

        Allowed kwargs: name, bandwidth_limit, traffic_limit_mb,
                       expiry_date, enabled, status, telegram_user_id

        Note: Use enable_client()/disable_client() for toggling enabled state
        as they properly sync WireGuard. Direct 'enabled' changes here only
        update DB without WG sync (for internal use only).
        """
        client = self.get_client(client_id)
        if not client:
            return None

        # If caller changes 'enabled', redirect to enable/disable methods
        # which properly handle WG peer add/remove
        if "enabled" in kwargs:
            new_enabled = kwargs.pop("enabled")
            if new_enabled != client.enabled:
                if new_enabled:
                    self.enable_client(client_id)
                else:
                    self.disable_client(client_id, reason=kwargs.pop("status", None))
                # Refresh client after enable/disable
                client = self.get_client(client_id)
                if not client:
                    return None

        allowed_fields = {
            "name", "bandwidth_limit", "traffic_limit_mb",
            "expiry_date", "status", "telegram_user_id",
            "customer_email",
        }

        has_updates = False
        for key, value in kwargs.items():
            if key in allowed_fields:
                setattr(client, key, value)
                has_updates = True

        if not has_updates:
            return client

        try:
            self.db.commit()
            self.db.refresh(client)
            logger.info(f"Updated client {client.name}: {kwargs}")
            return client
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update client: {e}")
            return None

    def delete_client(self, client_id: int, force: bool = False) -> bool:
        """
        Delete a client

        Uses WG-first ordering: remove WG peer, then delete DB record.
        If DB delete fails after WG removal, re-adds peer to keep consistent.

        Args:
            client_id: ID of client to delete
            force: If True, delete from WireGuard even if DB fails

        Returns:
            True if successful
        """
        client = self.get_client(client_id)
        if not client:
            return False

        server = client.server
        public_key = client.public_key
        # Save data needed to re-add peer if rollback required
        allowed_ips = [f"{client.ipv4}/32"]
        if client.ipv6:
            allowed_ips.append(f"{client.ipv6}/128")
        preshared_key = client.preshared_key
        was_enabled = client.enabled

        # Save bandwidth info before deletion for TC cleanup
        had_bandwidth_limit = bool(
            (client.bandwidth_limit and client.bandwidth_limit > 0) or
            (client.auto_bandwidth_limit and client.auto_bandwidth_limit > 0)
        )
        ip_index = client.ip_index

        is_proxy = (
            getattr(server, 'server_category', None) == 'proxy' or
            getattr(server, 'server_type', '') in ('hysteria2', 'tuic')
        ) if server else False

        try:
            wg_removed = False
            if is_proxy:
                # Proxy clients have no WG peer — skip WG operations entirely
                pass
            elif was_enabled:
                # Step 1: Remove WG peer FIRST (only for VPN clients)
                try:
                    wg = self._get_wg(server) if server else self.wg_manager
                    try:
                        wg.remove_peer(public_key)
                        wg_removed = True
                    finally:
                        wg.close()
                except Exception as e:
                    logger.warning(f"WG peer removal failed for {client.name}: {e}")
                    if not force:
                        raise

                # Step 1b: Remove TC bandwidth class if client had a limit
                if had_bandwidth_limit and server:
                    try:
                        from .traffic_manager import TrafficManager
                        tm = TrafficManager(self.db)
                        tm.set_bandwidth_limit(client_id, 0, server.interface or "wg0")
                    except Exception as e:
                        logger.warning(f"TC cleanup failed for {client.name}: {e}")

            # Step 2: Clean up FK references (subscriptions, portal links)
            try:
                from ..database.models import Subscription
                self.db.query(Subscription).filter(
                    Subscription.client_id == client_id
                ).delete()
            except Exception:
                pass
            try:
                from src.modules.subscription.subscription_models import ClientUserClients
                self.db.query(ClientUserClients).filter(
                    ClientUserClients.client_id == client_id
                ).delete()
            except Exception:
                pass  # Table may not exist if portal not used

            # Step 3: Delete from database
            self.db.delete(client)
            self.db.commit()

            logger.info(f"Deleted client '{client.name}'")

            # Step 4: Proxy servers — regenerate config without deleted client
            if is_proxy and server:
                self._apply_proxy_config(server)

            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete client: {e}")

            # Compensate: re-add WG peer if we removed it but DB delete failed
            if wg_removed and not force:
                try:
                    wg = self._get_wg(server) if server else self.wg_manager
                    wg.add_peer(public_key, allowed_ips, preshared_key)
                    wg.close()
                    logger.info(f"Rolled back WG peer removal for {client.name}")
                except Exception as re_err:
                    logger.error(f"Failed to rollback WG peer for {client.name}: {re_err}")

            return False

    # ========================================================================
    # ENABLE/DISABLE OPERATIONS
    # ========================================================================

    def enable_client(self, client_id: int) -> bool:
        """Enable a client (add to WireGuard or update proxy config)."""
        client = self.get_client(client_id)
        if not client:
            return False

        if client.enabled:
            return True  # Already enabled

        server = client.server
        is_proxy = (
            getattr(server, 'server_category', None) == 'proxy' or
            getattr(server, 'server_type', '') in ('hysteria2', 'tuic')
        ) if server else False

        try:
            if is_proxy:
                # Proxy clients: just flip the DB flag, then regenerate server config
                client.enabled = True
                client.status = ClientStatus.ACTIVE
                self.db.commit()
                self._apply_proxy_config(server)
                logger.info(f"Enabled proxy client '{client.name}'")
                return True

            # VPN clients: add WG peer first, then commit DB
            allowed_ips = [f"{client.ipv4}/32"]
            if client.ipv6:
                allowed_ips.append(f"{client.ipv6}/128")

            wg = self._get_wg(server) if server else self.wg_manager
            try:
                wg.add_peer(
                    public_key=client.public_key,
                    allowed_ips=allowed_ips,
                    preshared_key=client.preshared_key
                )
            finally:
                wg.close()

            client.enabled = True
            client.status = ClientStatus.ACTIVE
            self.db.commit()

            logger.info(f"Enabled client '{client.name}'")
            return True

        except Exception as e:
            self.db.rollback()
            if not is_proxy:
                # Compensate: remove WG peer if DB commit failed
                try:
                    wg2 = self._get_wg(client.server) if client.server else self.wg_manager
                    try:
                        wg2.remove_peer(client.public_key)
                    finally:
                        wg2.close()
                except Exception:
                    logger.warning(f"Failed to rollback WG peer add for {client.name}")
            logger.error(f"Failed to enable client: {e}")
            return False

    def disable_client(self, client_id: int, reason: Optional[str] = None) -> bool:
        """Disable a client (remove from WireGuard or update proxy config)."""
        client = self.get_client(client_id)
        if not client:
            return False

        if not client.enabled:
            return True  # Already disabled

        server = client.server
        is_proxy = (
            getattr(server, 'server_category', None) == 'proxy' or
            getattr(server, 'server_type', '') in ('hysteria2', 'tuic')
        ) if server else False

        try:
            if is_proxy:
                # Proxy clients: flip DB flag, regenerate server config
                client.enabled = False
                if reason == "expired":
                    client.status = ClientStatus.EXPIRED
                elif reason == "traffic":
                    client.status = ClientStatus.TRAFFIC_EXCEEDED
                else:
                    client.status = ClientStatus.DISABLED
                self.db.commit()
                self._apply_proxy_config(server)
                logger.info(f"Disabled proxy client '{client.name}' (reason: {reason})")
                return True

            # VPN clients: remove WG peer first, then commit DB
            wg = self._get_wg(server) if server else self.wg_manager
            try:
                wg.remove_peer(client.public_key)
            finally:
                wg.close()

            client.enabled = False
            if reason == "expired":
                client.status = ClientStatus.EXPIRED
            elif reason == "traffic":
                client.status = ClientStatus.TRAFFIC_EXCEEDED
            else:
                client.status = ClientStatus.DISABLED

            self.db.commit()

            logger.info(f"Disabled client '{client.name}' (reason: {reason})")
            return True

        except Exception as e:
            self.db.rollback()
            if not is_proxy:
                # Compensate: re-add WG peer if DB commit failed
                try:
                    wg2 = self._get_wg(client.server) if client.server else self.wg_manager
                    try:
                        wg2.add_peer(
                            public_key=client.public_key,
                            allowed_ips=[f"{client.ipv4}/32"] + ([f"{client.ipv6}/128"] if client.ipv6 else []),
                            preshared_key=client.preshared_key
                        )
                    finally:
                        wg2.close()
                except Exception:
                    logger.warning(f"Failed to rollback WG peer removal for {client.name}")
            logger.error(f"Failed to disable client: {e}")
            return False

    # ========================================================================
    # CONFIG GENERATION
    # ========================================================================

    def get_client_config(self, client_id: int) -> Optional[str]:
        """Generate client configuration file content (WireGuard, AmneziaWG, or proxy)"""
        client = self.get_client(client_id)
        if not client:
            return None

        server = client.server
        if not server:
            return None

        server_type = getattr(server, 'server_type', 'wireguard')
        server_category = getattr(server, 'server_category', 'vpn')

        # Route proxy clients to proxy config generator
        if server_category == 'proxy' or server_type in ('hysteria2', 'tuic'):
            return self._get_proxy_client_config(client, server)

        is_awg = server_type == 'amneziawg'

        # WireGuard / AmneziaWG configs require Endpoint = host:port. The
        # server.endpoint column may be stored either with or without the
        # port (operator might type just an IP in the create-server form).
        # Append listen_port whenever the field doesn't already contain a
        # port. IPv6 literals "[::1]:51820" are also handled.
        def _with_port(endpoint: str, port: int) -> str:
            if not endpoint:
                return endpoint
            stripped = endpoint.strip().rstrip("/")
            # IPv6 literal
            if stripped.startswith("["):
                return stripped if "]:" in stripped else f"{stripped}:{port}"
            # Hostname or IPv4 — has colon → already has port
            if ":" in stripped:
                return stripped
            return f"{stripped}:{port}"
        client_endpoint = _with_port(server.endpoint, server.listen_port)

        # Always use full tunnel — AmneziaVPN client handles site-based split tunneling
        # when AllowedIPs = 0.0.0.0/0. Setting specific IPs disables the client's
        # split tunneling page (isDefaultServerDefaultContainerHasSplitTunneling = true).
        allowed_ips = "0.0.0.0/0"

        # One authoritative commercial policy hook is used by every admin,
        # portal, QR and app config path because they all delegate to this
        # renderer. Open-core builds safely fall back to Server.dns.
        effective_dns = server.dns
        try:
            from ..modules.dns_protection import resolve_dns_for_client
            effective_dns = resolve_dns_for_client(self.db, client, server)
        except Exception as exc:
            logger.warning("DNS policy fallback for client {}: {}", client.id, exc)

        if is_awg:
            from .amneziawg import AWG_DEFAULT_MTU
            awg_mtu = getattr(server, 'awg_mtu', None) or AWG_DEFAULT_MTU
            mgr = AmneziaWGManager(
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
            client_ipv6 = (
                None if getattr(server, "ipv4_only", False) or not client.ipv6
                else f"{client.ipv6}/128"
            )
            return mgr.generate_client_config(
                client_private_key=client.private_key,
                client_ipv4=f"{client.ipv4}/32",
                client_ipv6=client_ipv6,
                server_public_key=server.public_key,
                server_endpoint=client_endpoint,
                preshared_key=client.preshared_key,
                dns=effective_dns,
                mtu=awg_mtu,
                allowed_ips=allowed_ips,
                persistent_keepalive=server.persistent_keepalive,
            )

        client_ipv6 = (
            None if getattr(server, "ipv4_only", False) or not client.ipv6
            else f"{client.ipv6}/128"
        )
        return self.wg_manager.generate_client_config(
            client_private_key=client.private_key,
            client_ipv4=f"{client.ipv4}/32",
            client_ipv6=client_ipv6,
            server_public_key=server.public_key,
            server_endpoint=client_endpoint,
            preshared_key=client.preshared_key,
            dns=effective_dns,
            mtu=server.mtu,
            allowed_ips=allowed_ips,
            persistent_keepalive=server.persistent_keepalive
        )

    def get_amneziavpn_share_url(self, client_id: int) -> Optional[str]:
        """
        Build a vpn://... share URL for an AmneziaWG client. Used by the QR
        endpoint — the AmneziaVPN mobile app expects this wrapper, not raw
        wg-quick text.
        """
        client = self.get_client(client_id)
        if not client:
            return None
        server = client.server
        if not server or getattr(server, 'server_type', None) != 'amneziawg':
            return None

        # Endpoint must include port for the share URL to be valid.
        endpoint = server.endpoint or ""
        if endpoint and ":" not in endpoint.lstrip("[").split("]", 1)[-1]:
            endpoint = f"{endpoint}:{server.listen_port}"

        from .amneziawg import AmneziaWGManager, AWG_DEFAULT_MTU
        awg_mtu = getattr(server, 'awg_mtu', None) or AWG_DEFAULT_MTU
        mgr = AmneziaWGManager(
            interface=server.interface,
            config_path=server.config_path,
            jc=server.awg_jc,   jmin=server.awg_jmin, jmax=server.awg_jmax,
            s1=server.awg_s1,   s2=server.awg_s2,
            h1=server.awg_h1,   h2=server.awg_h2,
            h3=server.awg_h3,   h4=server.awg_h4,
        )
        client_ipv6 = (
            None if getattr(server, "ipv4_only", False) or not client.ipv6
            else f"{client.ipv6}/128"
        )
        return mgr.generate_amneziavpn_share_url(
            client_private_key=client.private_key,
            client_public_key=client.public_key,
            client_ipv4=f"{client.ipv4}/32",
            client_ipv6=client_ipv6,
            server_public_key=server.public_key,
            server_endpoint=endpoint,
            preshared_key=client.preshared_key,
            dns=server.dns,
            mtu=awg_mtu,
            allowed_ips="0.0.0.0/0",
            persistent_keepalive=server.persistent_keepalive,
            description=server.name or "Flirexa",
        )

    def get_proxy_client_access(self, client_id: int) -> Optional[Dict]:
        """
        Return proxy client access info: URI, config, credentials.
        Used by API and client portal for Hysteria2/TUIC clients.
        """
        client = self.get_client(client_id)
        if not client:
            return None
        server = client.server
        if not server:
            return None
        server_type = getattr(server, 'server_type', '')
        result = self._get_proxy_client_config_dict(client, server)
        return result

    def _get_proxy_client_config(self, client, server) -> Optional[str]:
        """Return proxy client config as a string (YAML or JSON)."""
        d = self._get_proxy_client_config_dict(client, server)
        if not d:
            return None
        return d.get("config_yaml") or d.get("config_json") or d.get("uri")

    def _get_proxy_client_config_dict(self, client, server) -> Optional[dict]:
        """Return full proxy client config dict including URI."""
        from ..modules.proxy_client_adapter import get_proxy_client_config_dict

        return get_proxy_client_config_dict(client, server)

    def get_peer_devices(self, client_id: int) -> List[Dict[str, Any]]:
        """
        Get all devices (clients) of the same telegram_user_id as this client.
        Used for peer_visibility feature: user sees their own devices' VPN IPs.
        Returns empty list if client has no telegram_user_id, or if the server
        does not support peer_visibility.
        """
        client = self.get_client(client_id)
        if not client or not client.telegram_user_id:
            return []

        # Check server-level support
        server = client.server
        if server and not getattr(server, 'supports_peer_visibility', True):
            return []

        peers = self.db.query(Client).filter(
            and_(
                Client.telegram_user_id == client.telegram_user_id,
                Client.id != client_id,
                Client.enabled == True,
            )
        ).order_by(Client.name).all()

        return [
            {
                "id": p.id,
                "name": p.name,
                "ipv4": p.ipv4,
                "server_id": p.server_id,
                "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
            }
            for p in peers
        ]

    def save_client_config_file(
        self,
        client_id: int,
        config_dir: str = "/root"
    ) -> Optional[str]:
        """Save client config to a file and return the path"""
        client = self.get_client(client_id)
        if not client:
            return None

        config_content = self.get_client_config(client_id)
        if not config_content:
            return None

        return self.wg_manager.save_client_config(
            config_content=config_content,
            client_name=client.name,
            config_dir=config_dir
        )

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _get_next_available_ip(
        self,
        server_id: int,
        address_pool: str
    ) -> Optional[int]:
        """Find the next available IP host-offset for a server.

        Returns the integer offset into the CIDR (1 = first usable host,
        ``num_addresses - 2`` = last usable). The caller turns this back
        into a real address via ``IPv4Network(pool).network_address + n``.

        Considers both panel allocations and any commercial adapter offsets.

        Works on any prefix length (/24, /22, /16, …). The earlier code
        only scanned 2..255 which silently capped pools larger than /24.
        """
        import ipaddress as _ipaddress

        try:
            net = _ipaddress.IPv4Network(address_pool, strict=False)
        except ValueError:
            logger.error(f"Invalid address_pool_ipv4 on server {server_id}: {address_pool}")
            return None

        # Every creation path (admin UI, portal/device slots, payment
        # provisioning and bot) funnels through this allocator. Serialize the
        # check-and-reserve window per server on PostgreSQL; otherwise two API
        # workers can both observe offset N as free and mint the same address.
        # The xact lock is held until the caller commits/rolls back.
        bind = self.db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :server_id)"),
                {"namespace": 0x464C4950, "server_id": int(server_id)},
            )

        used_rows = self.db.query(Client.ip_index, Client.ipv4).filter(
            Client.server_id == server_id
        ).all()
        used_set = {row.ip_index for row in used_rows if row.ip_index is not None}

        # Imported/legacy rows can have a NULL or stale ip_index even though
        # ipv4 is valid. Trusting only ip_index was the manual-client vs portal
        # collision reported by a paid operator: the allocator reused an
        # address already present in the DB. Derive occupancy from BOTH fields.
        network_int = int(net.network_address)
        for row in used_rows:
            raw = (row.ipv4 or "").split("/", 1)[0].strip()
            if not raw:
                continue
            try:
                addr = _ipaddress.IPv4Address(raw)
            except _ipaddress.AddressValueError:
                logger.warning(
                    "Client address allocator ignored invalid IPv4 {!r} on server {}",
                    row.ipv4,
                    server_id,
                )
                continue
            if addr in net:
                used_set.add(int(addr) - network_int)

        from ..modules.remote_client_adapter import get_live_peer_ip_offsets

        used_set.update(
            get_live_peer_ip_offsets(self.db, server_id, address_pool)
        )

        # Skip .0 (network) and .1 (gateway / server-side address); cap one
        # short of broadcast. For a /22 that's offsets 2..1021.
        host_max = net.num_addresses - 1  # broadcast index (exclusive)
        for i in range(2, host_max):
            if i not in used_set:
                return i

        return None

    def get_client_count(self, server_id: Optional[int] = None) -> int:
        """Get total number of clients"""
        query = self.db.query(Client)
        if server_id:
            query = query.filter(Client.server_id == server_id)
        return query.count()

    def get_active_client_count(self, server_id: Optional[int] = None) -> int:
        """Get number of enabled clients"""
        query = self.db.query(Client).filter(Client.enabled == True)
        if server_id:
            query = query.filter(Client.server_id == server_id)
        return query.count()

    def client_exists(self, name: str, server_id: Optional[int] = None) -> bool:
        """Check if a client with given name exists"""
        query = self.db.query(Client).filter(Client.name == name)
        if server_id:
            query = query.filter(Client.server_id == server_id)
        return query.first() is not None

    def get_clients_to_export(self, server_id: int) -> List[Dict[str, Any]]:
        """Get client data formatted for export"""
        clients = self.get_all_clients(server_id=server_id)
        return [
            {
                "name": c.name,
                "ipv4": c.ipv4,
                "ipv6": c.ipv6,
                "public_key": c.public_key,
                "enabled": c.enabled,
                "bandwidth_limit": c.bandwidth_limit,
                "traffic_limit_mb": c.traffic_limit_mb,
                "expiry_date": c.expiry_date.isoformat() if c.expiry_date else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in clients
        ]
