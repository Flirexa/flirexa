"""
Corporate site-to-site WireGuard VPN — database models.

Each corporate network is a private VPN that connects multiple sites (offices,
servers, branches) in a full-mesh topology.  Internet traffic is never routed
through the tunnel — only local subnets of each site are reachable from peers
(split-tunnel site-to-site).

Address space: 10.200.0.0/16
  • Each network gets its own /24:   10.200.1.0/24 … 10.200.254.0/24
  • Sites within a network get:       10.200.x.1, .2, .3, …
"""

import enum
import json
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models import Base
from src.database.encrypted_type import EncryptedText


class CorporateNetworkStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class CorporateSiteStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class CorporateNetwork(Base):
    """A private multi-site WireGuard VPN network owned by one portal user."""

    __tablename__ = "corporate_networks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Owner (portal user)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("client_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Tunnel address space assigned to this network, e.g. "10.200.3.0/24"
    vpn_subnet: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Copied from subscription at creation time
    subscription_tier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    sites: Mapped[List["CorporateNetworkSite"]] = relationship(
        "CorporateNetworkSite",
        back_populates="network",
        cascade="all, delete-orphan",
        order_by="CorporateNetworkSite.id",
    )

    def __repr__(self) -> str:
        return f"<CorporateNetwork id={self.id} name={self.name!r} subnet={self.vpn_subnet}>"


class CorporateNetworkSite(Base):
    """
    A single WireGuard peer (office, server, branch, etc.) inside a
    CorporateNetwork.  Each site holds its own key pair and knows the
    local subnets it advertises to the other peers.
    """

    __tablename__ = "corporate_network_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    network_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("corporate_networks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # WireGuard key pair (private key encrypted at rest)
    private_key: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # VPN-tunnel IP assigned to this site, e.g. "10.200.3.1"
    vpn_ip: Mapped[str] = mapped_column(String(50), nullable=False)

    # JSON list of local subnets this site advertises, e.g. '["192.168.1.0/24"]'
    local_subnets: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional public endpoint for this site, e.g. "203.0.113.5:51820"
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    listen_port: Mapped[int] = mapped_column(Integer, default=51820, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # ── Relay / routing ────────────────────────────────────────────────────
    # If True, this site acts as a relay/hub for other sites in the network.
    # Relay config includes ALL other sites as peers + IP forwarding required.
    is_relay: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    # How this site routes traffic to peers:
    #   "auto"      – direct when possible, relay for NAT pairs (default)
    #   "direct"    – always direct, never use relay
    #   "via_relay" – route ALL inter-site traffic through relay node
    routing_mode: Mapped[str] = mapped_column(
        String(20), default="auto", nullable=False, server_default="auto"
    )

    # Tracks when the config was last downloaded by the user
    config_downloaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    network: Mapped["CorporateNetwork"] = relationship(
        "CorporateNetwork", back_populates="sites"
    )

    # ── Helpers ────────────────────────────────────────────────────────────

    def get_local_subnets(self) -> List[str]:
        if not self.local_subnets:
            return []
        try:
            return json.loads(self.local_subnets)
        except Exception:
            return []

    def __repr__(self) -> str:
        return (
            f"<CorporateNetworkSite id={self.id} name={self.name!r}"
            f" vpn_ip={self.vpn_ip} net={self.network_id}>"
        )


class CorporateNetworkEvent(Base):
    """
    Audit / diagnostic event log for corporate networks.
    Records lifecycle events: site created/deleted, keys regenerated,
    config downloaded, status changes, diagnostics runs, etc.
    """

    __tablename__ = "corporate_network_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    network_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("corporate_networks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional: which site the event relates to (null = network-level event)
    site_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    site_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # e.g. "site_created", "keys_regenerated", "config_downloaded",
    #       "status_changed", "diagnostics_run", "subnet_conflict"
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Human-readable description shown in the event log
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional severity: "info" | "warning" | "error"
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CorporateNetworkEvent id={self.id} net={self.network_id} type={self.event_type!r}>"
