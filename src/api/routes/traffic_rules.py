"""
VPN Management Studio Traffic Rules API
Top consumers leaderboard + auto-enforcement rules
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from ...database.connection import get_db
from ...database.models import TrafficRule
from ...core.management import ManagementCore

router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

class TopConsumerResponse(BaseModel):
    client_id: int
    client_name: str
    server_id: int
    server_name: str = "Unknown"
    bytes_rx: int
    bytes_tx: int
    bytes_total: int
    bandwidth_limit: Optional[int] = None
    auto_bandwidth_limit: Optional[int] = None
    auto_bandwidth_rule_id: Optional[int] = None


class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    period: str = Field(..., pattern=r"^(day|week|month)$")
    threshold_mb: int = Field(..., ge=1)
    bandwidth_limit_mbps: int = Field(..., ge=1)
    client_id: Optional[int] = None  # None = applies to all clients
    enabled: bool = True


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    period: Optional[str] = Field(None, pattern=r"^(day|week|month)$")
    threshold_mb: Optional[int] = Field(None, ge=1)
    bandwidth_limit_mbps: Optional[int] = Field(None, ge=1)
    client_id: Optional[int] = None
    enabled: Optional[bool] = None


class RuleResponse(BaseModel):
    id: int
    name: str
    period: str
    threshold_mb: int
    bandwidth_limit_mbps: int
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    server_name: Optional[str] = None
    enabled: bool

    class Config:
        from_attributes = True


class ClientOption(BaseModel):
    id: int
    name: str
    server_id: int
    server_name: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/top", response_model=List[TopConsumerResponse])
async def get_top_consumers(
    period: str = Query("day", pattern=r"^(day|week|month)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get top traffic consumers for a period (day, week, month)."""
    core = ManagementCore(db)
    return core.traffic.get_top_consumers(period=period, limit=limit)


@router.get("/clients", response_model=List[ClientOption])
async def list_clients_for_rules(db: Session = Depends(get_db)):
    """List all clients with server names for rule target selection."""
    from ...database.models import Client, Server
    clients = (
        db.query(Client.id, Client.name, Client.server_id, Server.name.label("server_name"))
        .join(Server, Client.server_id == Server.id)
        .order_by(Server.name, Client.name)
        .all()
    )
    return [{"id": c.id, "name": c.name, "server_id": c.server_id, "server_name": c.server_name} for c in clients]


@router.get("/rules", response_model=List[RuleResponse])
async def list_rules(db: Session = Depends(get_db)):
    """List all traffic auto-rules."""
    from ...database.models import Client, Server
    rules = db.query(TrafficRule).order_by(TrafficRule.id).all()

    # Batch fetch all referenced clients to avoid N+1 queries
    client_ids = [r.client_id for r in rules if r.client_id]
    clients_map = {}
    if client_ids:
        clients = db.query(Client).filter(Client.id.in_(client_ids)).all()
        clients_map = {c.id: c for c in clients}

    result = []
    for rule in rules:
        data = {
            "id": rule.id, "name": rule.name, "period": rule.period,
            "threshold_mb": rule.threshold_mb, "bandwidth_limit_mbps": rule.bandwidth_limit_mbps,
            "client_id": rule.client_id, "enabled": rule.enabled,
            "client_name": None, "server_name": None,
        }
        if rule.client_id and rule.client_id in clients_map:
            client = clients_map[rule.client_id]
            data["client_name"] = client.name
            server = client.server
            data["server_name"] = server.name if server else None
        result.append(data)
    return result


@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(data: RuleCreate, db: Session = Depends(get_db)):
    """Create a new traffic auto-rule."""
    # License enforcement: traffic_rules feature
    try:
        from ...modules.license.manager import get_license_manager
        mgr = get_license_manager()
        if not mgr.get_license_info().has_feature("traffic_rules"):
            raise HTTPException(
                status_code=403,
                detail="Traffic rules feature requires Business or Enterprise license."
            )
    except HTTPException:
        raise
    except Exception:
        pass

    from ...database.models import Client
    if data.client_id is not None:
        client = db.query(Client).filter(Client.id == data.client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail=f"Client with id {data.client_id} not found")

    rule = TrafficRule(
        name=data.name,
        period=data.period,
        threshold_mb=data.threshold_mb,
        bandwidth_limit_mbps=data.bandwidth_limit_mbps,
        client_id=data.client_id,
        enabled=data.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info(f"Created traffic rule: {rule.name}")
    resp = {
        "id": rule.id, "name": rule.name, "period": rule.period,
        "threshold_mb": rule.threshold_mb, "bandwidth_limit_mbps": rule.bandwidth_limit_mbps,
        "client_id": rule.client_id, "enabled": rule.enabled,
        "client_name": None, "server_name": None,
    }
    if rule.client_id:
        client = db.query(Client).filter(Client.id == rule.client_id).first()
        if client:
            resp["client_name"] = client.name
            resp["server_name"] = client.server.name if client.server else None
    return resp


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    data: RuleUpdate,
    db: Session = Depends(get_db)
):
    """Update a traffic auto-rule."""
    rule = db.query(TrafficRule).filter(TrafficRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    logger.info(f"Updated traffic rule: {rule.name}")
    from ...database.models import Client
    resp = {
        "id": rule.id, "name": rule.name, "period": rule.period,
        "threshold_mb": rule.threshold_mb, "bandwidth_limit_mbps": rule.bandwidth_limit_mbps,
        "client_id": rule.client_id, "enabled": rule.enabled,
        "client_name": None, "server_name": None,
    }
    if rule.client_id:
        client = db.query(Client).filter(Client.id == rule.client_id).first()
        if client:
            resp["client_name"] = client.name
            resp["server_name"] = client.server.name if client.server else None
    return resp


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """Delete a traffic auto-rule."""
    rule = db.query(TrafficRule).filter(TrafficRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Clear auto-limits set by this rule
    from ...database.models import Client
    clients = db.query(Client).filter(Client.auto_bandwidth_rule_id == rule_id).all()
    for client in clients:
        client.auto_bandwidth_limit = None
        client.auto_bandwidth_rule_id = None

    db.delete(rule)
    db.commit()
    logger.info(f"Deleted traffic rule: {rule.name}")
    return {"message": f"Rule '{rule.name}' deleted"}


@router.post("/check-rules")
async def trigger_check_rules(db: Session = Depends(get_db)):
    """Manually trigger traffic rules evaluation."""
    core = ManagementCore(db)
    affected = core.traffic.check_traffic_rules()
    return {"affected_clients": affected}
