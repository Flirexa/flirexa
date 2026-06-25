from src.database.models import ClientSegment, Client
from src.core.segment_rules import apply_segment_to_client

def test_applies_only_non_null_fields(db_session, monkeypatch):
    seg = ClientSegment(name="S", bandwidth_limit=50, traffic_limit_mb=None, expiry_date=None)
    db_session.add(seg); db_session.commit()
    c = Client(name="c", server_id=1); db_session.add(c); db_session.commit()
    captured = {}
    import src.core.segment_rules as sr
    monkeypatch.setattr(sr, "_update_client",
                        lambda db, cid, **f: captured.update({"cid": cid, **f}))
    applied = apply_segment_to_client(db_session, seg, c.id)
    assert applied == {"bandwidth_limit": 50}
    assert captured == {"cid": c.id, "bandwidth_limit": 50}
