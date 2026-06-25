"""
Tests for ClientSegment model and client segmentation
"""

from src.database.models import ClientSegment, Client


def test_segment_persists_and_links_client(db_session):
    seg = ClientSegment(name="VIP", color="#F97316", bandwidth_limit=100, traffic_limit_mb=51200)
    db_session.add(seg)
    db_session.commit()
    c = Client(name="c1", server_id=1, segment_id=seg.id)
    db_session.add(c)
    db_session.commit()
    assert db_session.get(Client, c.id).segment_id == seg.id
    assert db_session.get(ClientSegment, seg.id).name == "VIP"
