"""
VPN Management Studio Database Models
SQLAlchemy ORM models for the unified database
"""

from datetime import datetime, date
from enum import Enum as PyEnum
from typing import Optional, List
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Boolean,
    DateTime,
    Float,
    Text,
    ForeignKey,
    Enum,
    Index,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from src.database.encrypted_type import EncryptedText


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


# ============================================================================
# ENUMS
# ============================================================================

class UpdateStatus(str, PyEnum):
    """Update operation status"""
    PENDING     = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED  = "downloaded"
    VERIFIED    = "verified"
    READY_TO_APPLY = "ready_to_apply"
    APPLYING    = "applying"
    SUCCESS     = "success"
    FAILED      = "failed"
    ROLLBACK_REQUIRED = "rollback_required"
    ROLLED_BACK = "rolled_back"
    ROLLING_BACK = "rolling_back"


class UpdateType(str, PyEnum):
    """Semver update type"""
    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


class ClientStatus(str, PyEnum):
    """Client connection status"""
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    TRAFFIC_EXCEEDED = "traffic_exceeded"
    PENDING = "pending"


class ServerStatus(str, PyEnum):
    """Server status"""
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class ServerLifecycleStatus(str, PyEnum):
    """Canonical lifecycle status for server orchestration."""
    CREATING = "creating"
    BOOTSTRAP_PENDING = "bootstrap_pending"
    BOOTSTRAPPING = "bootstrapping"
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"
    # When a paid subscription lapses, servers beyond the FREE per-protocol
    # quota are stopped and parked here. They can't be started until the
    # operator re-activates a paid license. Removed manually via DELETE.
    SUSPENDED_NO_LICENSE = "suspended_no_license"


class SubscriptionStatus(str, PyEnum):
    """Subscription status"""
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


class PaymentStatus(str, PyEnum):
    """Payment status"""
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    FAILED = "failed"
    REFUNDED = "refunded"


class AuditAction(str, PyEnum):
    """Audit log action types"""
    CLIENT_CREATE = "client_create"
    CLIENT_UPDATE = "client_update"
    CLIENT_DELETE = "client_delete"
    CLIENT_ENABLE = "client_enable"
    CLIENT_DISABLE = "client_disable"
    CLIENT_TRAFFIC_RESET = "client_traffic_reset"
    SERVER_CREATE = "server_create"
    SERVER_UPDATE = "server_update"
    SERVER_DELETE = "server_delete"
    SERVER_STATUS_CHANGE = "server_status_change"
    SUBSCRIPTION_CREATE = "subscription_create"
    SUBSCRIPTION_RENEW = "subscription_renew"
    SUBSCRIPTION_CANCEL = "subscription_cancel"
    PAYMENT_CREATE = "payment_create"
    PAYMENT_COMPLETE = "payment_complete"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    CONFIG_CHANGE = "config_change"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    BACKUP_CREATE = "backup_create"
    BACKUP_RESTORE = "backup_restore"
    BACKUP_DELETE = "backup_delete"


class LicenseType(str, PyEnum):
    """License types"""
    TRIAL = "trial"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# ============================================================================
# MODELS
# ============================================================================

class Server(Base):
    """WireGuard server configuration"""
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # WireGuard configuration
    interface: Mapped[str] = mapped_column(String(20), default="wg0")
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    listen_port: Mapped[int] = mapped_column(Integer, default=51820)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    private_key: Mapped[str] = mapped_column(EncryptedText(), nullable=False)

    # Network configuration
    address_pool_ipv4: Mapped[str] = mapped_column(String(50), default="10.66.66.0/24")
    address_pool_ipv6: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dns: Mapped[str] = mapped_column(String(255), default="1.1.1.1,1.0.0.1")

    # Server settings
    mtu: Mapped[int] = mapped_column(Integer, default=1420)
    persistent_keepalive: Mapped[int] = mapped_column(Integer, default=25)
    config_path: Mapped[str] = mapped_column(String(255), default="/etc/wireguard/wg0.conf")

    # Status and limits
    status: Mapped[ServerStatus] = mapped_column(
        Enum(ServerStatus), default=ServerStatus.ONLINE
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default=ServerLifecycleStatus.ONLINE.value, nullable=False, server_default=ServerLifecycleStatus.ONLINE.value
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )
    max_clients: Mapped[int] = mapped_column(Integer, default=250)
    max_bandwidth_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # SSH remote management
    ssh_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user: Mapped[str] = mapped_column(String(50), default="root")
    ssh_password: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)
    ssh_private_key: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)

    # Default server for auto-provisioned clients (subscriptions, client portal)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    # Agent mode (HTTP API instead of SSH)
    agent_mode: Mapped[Optional[str]] = mapped_column(
        String(10), default="ssh", nullable=True
    )  # "ssh" or "agent"
    agent_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    agent_api_key: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)

    # Server type: "wireguard" | "amneziawg" | "hysteria2" | "tuic"
    server_type: Mapped[str] = mapped_column(String(20), default="wireguard", nullable=False, server_default="wireguard")

    # Server category: "vpn" (wireguard/amneziawg) | "proxy" (hysteria2/tuic)
    server_category: Mapped[str] = mapped_column(String(20), default="vpn", nullable=False, server_default="vpn")

    # AmneziaWG obfuscation parameters (only used when server_type == "amneziawg")
    awg_jc: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    awg_jmin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    awg_jmax: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    awg_s1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    awg_s2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    awg_h1: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    awg_h2: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    awg_h3: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    awg_h4: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # AmneziaWG MTU (None = use safe default 1280 for AWG, 1420 for WG)
    awg_mtu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Whether this server supports peer_visibility (device-to-device routing)
    supports_peer_visibility: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )

    # Split tunneling support: when True, client configs use VPN subnet AllowedIPs
    # instead of 0.0.0.0/0, enabling AmneziaVPN app's site-based split tunneling
    split_tunnel_support: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )

    # Drift detection (migration 010)
    drift_detected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    drift_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    drift_detected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reconcile_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Proxy protocol fields (hysteria2 / tuic) — NULL for VPN servers
    proxy_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    proxy_tls_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # self_signed | acme | manual
    proxy_cert_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    proxy_key_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    proxy_config_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    proxy_service_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    proxy_obfs_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Hysteria2 OBFS
    proxy_auth_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Hysteria2 server-level auth password (shared by all clients)

    # Relationships
    clients: Mapped[List["Client"]] = relationship("Client", back_populates="server")

    @property
    def is_proxy(self) -> bool:
        """True for proxy-category servers (Hysteria2, TUIC)."""
        return getattr(self, 'server_category', 'vpn') == 'proxy'

    @property
    def is_vpn(self) -> bool:
        """True for VPN-category servers (WireGuard, AmneziaWG)."""
        return not self.is_proxy

    @property
    def effective_lifecycle_status(self) -> str:
        """Return canonical lifecycle_status with legacy status fallback."""
        if getattr(self, "lifecycle_status", None):
            return self.lifecycle_status
        return map_legacy_status_to_lifecycle(self.status).value

    @property
    def legacy_status(self) -> ServerStatus:
        """Return legacy status enum derived from lifecycle_status."""
        return map_lifecycle_to_legacy_status(self.effective_lifecycle_status)

    def __repr__(self):
        return f"<Server(id={self.id}, name='{self.name}', type='{self.server_type}')>"


def map_legacy_status_to_lifecycle(status: Optional[ServerStatus | str]) -> ServerLifecycleStatus:
    """Map legacy ServerStatus to canonical lifecycle status."""
    value = status.value if isinstance(status, ServerStatus) else str(status or "").lower()
    mapping = {
        ServerStatus.ONLINE.value: ServerLifecycleStatus.ONLINE,
        ServerStatus.OFFLINE.value: ServerLifecycleStatus.OFFLINE,
        ServerStatus.ERROR.value: ServerLifecycleStatus.FAILED,
        ServerStatus.MAINTENANCE.value: ServerLifecycleStatus.DEGRADED,
    }
    return mapping.get(value, ServerLifecycleStatus.OFFLINE)


def map_lifecycle_to_legacy_status(lifecycle_status: Optional[ServerLifecycleStatus | str]) -> ServerStatus:
    """Map canonical lifecycle status back to the legacy ServerStatus enum."""
    value = lifecycle_status.value if isinstance(lifecycle_status, ServerLifecycleStatus) else str(lifecycle_status or "").lower()
    mapping = {
        ServerLifecycleStatus.ONLINE.value: ServerStatus.ONLINE,
        ServerLifecycleStatus.OFFLINE.value: ServerStatus.OFFLINE,
        ServerLifecycleStatus.DEGRADED.value: ServerStatus.MAINTENANCE,
        ServerLifecycleStatus.FAILED.value: ServerStatus.ERROR,
        ServerLifecycleStatus.CREATING.value: ServerStatus.OFFLINE,
        ServerLifecycleStatus.BOOTSTRAP_PENDING.value: ServerStatus.OFFLINE,
        ServerLifecycleStatus.BOOTSTRAPPING.value: ServerStatus.OFFLINE,
        ServerLifecycleStatus.DELETING.value: ServerStatus.OFFLINE,
        ServerLifecycleStatus.DELETED.value: ServerStatus.OFFLINE,
    }
    return mapping.get(value, ServerStatus.OFFLINE)


class Client(Base):
    """
    Client/peer record.

    For VPN (WireGuard / AmneziaWG) clients:
        public_key  — real WG base64 public key (44 chars, required)
        private_key — encrypted WG private key
        ip_index / ipv4 / ipv6 — assigned VPN addresses

    For proxy (Hysteria2 / TUIC) clients:
        public_key  — NULL (no WG key semantics; do not use as identifier)
        ip_index / ipv4 — NULL (no VPN IP pool)
        proxy_password — encrypted auth credential
        proxy_uuid     — UUID for TUIC auth (NULL for Hysteria2)

    Use `client.is_proxy_client` to distinguish, not the presence of public_key.
    """
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    server_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("servers.id"), nullable=False
    )

    # WireGuard keys — NULL for proxy clients (no WG semantics for proxy)
    public_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    private_key: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)
    preshared_key: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)

    # IP addresses (NULL for proxy clients that have no VPN IP)
    ip_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ipv4: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    ipv6: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Proxy auth (hysteria2: name+password, tuic: uuid+password)
    proxy_password: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)
    proxy_uuid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Status
    status: Mapped[ClientStatus] = mapped_column(
        Enum(ClientStatus), default=ClientStatus.ACTIVE
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Bandwidth limiting (Mbps)
    bandwidth_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_bandwidth_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_bandwidth_rule_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Traffic tracking
    traffic_limit_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    traffic_limit_expiry: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    traffic_used_rx: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_used_tx: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_baseline_rx: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_baseline_tx: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_reset_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Expiry/Timer
    expiry_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Telegram user link (for client bot)
    telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=True
    )

    # Peer visibility: devices of the same telegram_user_id can see each other via VPN IP
    peer_visibility: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_handshake: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    server: Mapped["Server"] = relationship("Server", back_populates="clients")
    telegram_user: Mapped[Optional["TelegramUser"]] = relationship(
        "TelegramUser", back_populates="clients"
    )
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="client"
    )

    # Unique constraint on name per server
    __table_args__ = (
        UniqueConstraint("server_id", "name", name="uq_client_server_name"),
        UniqueConstraint("server_id", "ip_index", name="uq_client_server_ip"),
        Index("ix_client_public_key", "public_key"),
        Index("ix_client_enabled", "enabled"),
        Index("ix_client_status", "status"),
        Index("ix_client_server_status", "server_id", "status"),
        Index("ix_client_expiry", "expiry_date"),
    )

    @property
    def is_proxy_client(self) -> bool:
        """
        True for Hysteria2 / TUIC clients.

        Primary signal: public_key is NULL (set explicitly to None during creation).
        Secondary signal: proxy_password is present (belt-and-suspenders).

        WireGuard/AmneziaWG clients always have a non-null public_key and never
        have proxy_password set, so combining both signals avoids false positives
        from partially-created or legacy records.

        For the most reliable check when the `server` relationship is loaded,
        use `belongs_to_proxy_server` instead.
        """
        # Fix L-2: avoid false positives from WG clients that happen to have
        # proxy_password set (legacy/misconfigured records).
        # A genuine proxy client always has public_key=None (no WG key).
        # proxy_password present on a WG client does NOT make it a proxy client.
        return self.public_key is None

    @property
    def belongs_to_proxy_server(self) -> bool:
        """
        True if this client belongs to a proxy server (Hysteria2 / TUIC).

        Uses the server relationship when loaded (most authoritative source).
        Falls back to is_proxy_client if the relationship is not loaded to
        avoid an N+1 query in list views.

        Prefer this over is_proxy_client in code paths where server is already
        joined/loaded (e.g. client detail views, restore flows).
        """
        if self.server is not None:
            return getattr(self.server, 'server_category', 'vpn') == 'proxy'
        return self.is_proxy_client

    @property
    def belongs_to_vpn_server(self) -> bool:
        """Convenience inverse of belongs_to_proxy_server."""
        return not self.belongs_to_proxy_server

    @property
    def wg_public_key(self) -> str:
        """
        Return the WireGuard public key.
        Raises ValueError for proxy clients that have no WG key.
        Use this instead of .public_key in WG-specific code to catch mistakes early.
        """
        if self.public_key is None:
            raise ValueError(
                f"Client '{self.name}' (id={self.id}) is a proxy client and has no "
                "WireGuard public key. Check is_proxy_client before calling wg_public_key."
            )
        return self.public_key

    def __repr__(self):
        return f"<Client(id={self.id}, name='{self.name}', ipv4='{self.ipv4}')>"


class TelegramUser(Base):
    """Telegram user for client bot integration"""
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Status
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    language: Mapped[str] = mapped_column(String(10), default="ru")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_activity: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    clients: Mapped[List["Client"]] = relationship(
        "Client", back_populates="telegram_user"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment", back_populates="telegram_user"
    )

    def __repr__(self):
        return f"<TelegramUser(id={self.id}, telegram_id={self.telegram_id})>"


class AdminUser(Base):
    """Admin panel users"""
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner, admin, manager
    permissions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list for manager role
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self):
        return f"<AdminUser(id={self.id}, username={self.username}, role={self.role})>"


class Plan(Base):
    """Subscription plan definitions"""
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Plan features
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    traffic_limit_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bandwidth_limit_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)

    # Pricing (in cents/kopecks for precision)
    price_usd: Mapped[int] = mapped_column(Integer, default=0)
    price_rub: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    features: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="plan"
    )

    def __repr__(self):
        return f"<Plan(id={self.id}, name='{self.name}')>"


class Subscription(Base):
    """Client subscriptions"""
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clients.id"), nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plans.id"), nullable=False
    )

    # Subscription period
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Status
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE
    )

    # Payment link
    payment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payments.id"), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="subscriptions")
    plan: Mapped["Plan"] = relationship("Plan", back_populates="subscriptions")
    payment: Mapped[Optional["Payment"]] = relationship(
        "Payment", back_populates="subscription"
    )

    def __repr__(self):
        return f"<Subscription(id={self.id}, client_id={self.client_id})>"


class Payment(Base):
    """Payment records"""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=True
    )

    # Payment details
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # In smallest units
    currency: Mapped[str] = mapped_column(String(10), nullable=False)  # USD, RUB, BTC, etc.

    # Provider info
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # mock, btc, usdt, ton
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tx_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Crypto specific
    wallet_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    crypto_amount: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Extra data
    payment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    telegram_user: Mapped[Optional["TelegramUser"]] = relationship(
        "TelegramUser", back_populates="payments"
    )
    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription", back_populates="payment", uselist=False
    )

    __table_args__ = (
        Index("ix_payment_status", "status"),
        Index("ix_payment_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Payment(id={self.id}, amount={self.amount}, status='{self.status}')>"


class TrafficDaily(Base):
    """Daily traffic accumulation per client"""
    __tablename__ = "traffic_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(DateTime, nullable=False)  # just the date part
    bytes_rx: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_tx: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        UniqueConstraint("client_id", "date", name="uq_traffic_daily_client_date"),
        Index("ix_traffic_daily_date", "date"),
    )


class TrafficRule(Base):
    """Auto-enforcement rules: if client exceeds threshold in period, apply bandwidth limit"""
    __tablename__ = "traffic_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # 'day', 'week', 'month'
    threshold_mb: Mapped[int] = mapped_column(Integer, nullable=False)  # MB threshold
    bandwidth_limit_mbps: Mapped[int] = mapped_column(Integer, nullable=False)  # applied limit
    client_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)  # None = all clients
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<TrafficRule(id={self.id}, name='{self.name}', period='{self.period}')>"


class AuditLog(Base):
    """Audit log for all system actions"""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Who performed the action
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    user_type: Mapped[str] = mapped_column(String(20), default="admin")  # admin, client, system

    # Action details
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # client, server, etc.
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Details
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_audit_action", "action"),
        Index("ix_audit_created_at", "created_at"),
        Index("ix_audit_user_id", "user_id"),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}')>"


class SystemConfig(Base):
    """System configuration key-value store"""
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), default="string")  # string, int, bool, json

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<SystemConfig(key='{self.key}')>"


class License(Base):
    """License information (stub for future)"""
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    license_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    license_type: Mapped[LicenseType] = mapped_column(
        Enum(LicenseType), default=LicenseType.TRIAL
    )

    # Limits
    max_clients: Mapped[int] = mapped_column(Integer, default=10)
    max_servers: Mapped[int] = mapped_column(Integer, default=1)

    # Features
    features: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Validity
    activated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self):
        return f"<License(type='{self.license_type}')>"


class UpdateHistory(Base):
    """Records every update / rollback operation."""
    __tablename__ = "update_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Version info
    from_version: Mapped[str] = mapped_column(String(32), nullable=False)
    to_version:   Mapped[str] = mapped_column(String(32), nullable=False)
    update_type:  Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # patch/minor/major
    channel: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # Status
    status: Mapped[UpdateStatus] = mapped_column(
        Enum(UpdateStatus), default=UpdateStatus.PENDING, index=True
    )

    # Timing
    started_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    progress_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Who triggered it
    started_by: Mapped[str] = mapped_column(String(128), default="admin")

    # Rollback
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    staging_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    package_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_release_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    db_backup_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    db_backup_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    db_backup_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    db_backup_valid: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False)  # True if this record IS a rollback
    rollback_of_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("update_history.id"), nullable=True)

    # Result
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # full apply log
    last_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Manifest snapshot (what was applied)
    manifest_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    package_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    package_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    requires_migration: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    requires_restart: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_uh_status_started", "status", "started_at"),
    )

    def __repr__(self):
        return f"<UpdateHistory({self.from_version}→{self.to_version} {self.status})>"


class ServerBootstrapLog(Base):
    """Persisted bootstrap task — survives API restarts."""
    __tablename__ = "server_bootstrap_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    server_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running / complete / failed / interrupted
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # newline-joined log lines
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PushNotification(Base):
    """Push notifications for app users"""
    __tablename__ = "push_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # NULL = broadcast to all
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), default="info")  # info, update, warning, promo
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_pn_user_unread", "user_id", "is_read"),
    )

# ============================================================================
