from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database.connection import get_db
from ...database.models import ClientSegment, Client
from ...core.segment_rules import apply_segment_to_client
from ...core.management import ManagementCore

router = APIRouter()

class SegmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=16)
    notes: Optional[str] = None
    bandwidth_limit: Optional[int] = Field(None, ge=0)
    traffic_limit_mb: Optional[int] = Field(None, ge=0)
    expiry_date: Optional[datetime] = None
    auto_bandwidth_rule_id: Optional[int] = None

class SegmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=16)
    notes: Optional[str] = None
    bandwidth_limit: Optional[int] = Field(None, ge=0)
    traffic_limit_mb: Optional[int] = Field(None, ge=0)
    expiry_date: Optional[datetime] = None
    auto_bandwidth_rule_id: Optional[int] = None

class SegmentResponse(BaseModel):
    id: int
    name: str
    color: Optional[str]
    notes: Optional[str]
    bandwidth_limit: Optional[int]
    traffic_limit_mb: Optional[int]
    expiry_date: Optional[datetime]
    auto_bandwidth_rule_id: Optional[int]
    member_count: int = 0
    class Config: from_attributes = True

def _with_count(db: Session, seg: ClientSegment) -> dict:
    n = db.query(func.count(Client.id)).filter(Client.segment_id == seg.id).scalar() or 0
    return {**SegmentResponse.model_validate(seg).model_dump(), "member_count": int(n)}

@router.get("", response_model=List[SegmentResponse])
def list_segments(db: Session = Depends(get_db)):
    return [_with_count(db, s) for s in db.query(ClientSegment).order_by(ClientSegment.name).all()]

@router.post("", response_model=SegmentResponse, status_code=201)
def create_segment(data: SegmentCreate, db: Session = Depends(get_db)):
    if db.query(ClientSegment).filter(ClientSegment.name == data.name).first():
        raise HTTPException(409, "Segment name already exists")
    seg = ClientSegment(**data.model_dump())
    db.add(seg); db.commit(); db.refresh(seg)
    return _with_count(db, seg)

@router.put("/{segment_id}", response_model=SegmentResponse)
def update_segment(segment_id: int, data: SegmentUpdate, apply: bool = Query(False), db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(seg, k, v)
    db.commit(); db.refresh(seg)
    if apply:
        for (cid,) in db.query(Client.id).filter(Client.segment_id == seg.id).all():
            apply_segment_to_client(db, seg, cid)
    return _with_count(db, seg)

@router.delete("/{segment_id}")
def delete_segment(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    db.query(Client).filter(Client.segment_id == seg.id).update({"segment_id": None})
    db.delete(seg); db.commit()
    return {"status": "ok"}


class MembersBody(BaseModel):
    client_ids: List[int]


@router.post("/{segment_id}/members")
def add_members(segment_id: int, body: MembersBody, db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    assigned = []
    for cid in body.client_ids:
        c = db.get(Client, cid)
        if not c:
            continue
        c.segment_id = seg.id
        assigned.append(cid)
    db.commit()
    for cid in assigned:
        apply_segment_to_client(db, seg, cid)
    return {"status": "ok", "count": len(assigned)}


@router.delete("/{segment_id}/members")
def remove_members(segment_id: int, body: MembersBody, db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    db.query(Client).filter(
        Client.id.in_(body.client_ids),
        Client.segment_id == segment_id,
    ).update({"segment_id": None}, synchronize_session=False)
    db.commit()
    return {"status": "ok"}


@router.post("/{segment_id}/apply")
def apply_to_members(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    ids = [cid for (cid,) in db.query(Client.id).filter(Client.segment_id == seg.id).all()]
    for cid in ids:
        apply_segment_to_client(db, seg, cid)
    return {"status": "ok", "applied": len(ids)}


@router.post("/{segment_id}/enable")
def enable_members(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    core = ManagementCore(db)
    ids = [cid for (cid,) in db.query(Client.id).filter(Client.segment_id == segment_id).all()]
    for cid in ids:
        core.enable_client(cid)
    return {"status": "ok", "count": len(ids)}


@router.post("/{segment_id}/disable")
def disable_members(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(ClientSegment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    core = ManagementCore(db)
    ids = [cid for (cid,) in db.query(Client.id).filter(Client.segment_id == segment_id).all()]
    for cid in ids:
        core.disable_client(cid)
    return {"status": "ok", "count": len(ids)}
