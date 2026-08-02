from src.database.models import Client
from src.modules.client_address_integrity import audit_server_client_addresses


def _client(server_id, name, key_suffix, ip_index, ipv4):
    return Client(
        name=name,
        server_id=server_id,
        public_key=f"AuditPublicKey{key_suffix:028d}=",
        private_key=f"AuditPrivateKey{key_suffix:027d}=",
        ip_index=ip_index,
        ipv4=ipv4,
        enabled=True,
    )


def test_address_audit_is_scoped_per_server(db_session, sample_server):
    db_session.add_all([
        _client(sample_server.id, "one", 1, 2, "10.66.66.2"),
        _client(sample_server.id, "two", 2, 3, "10.66.66.2"),
    ])
    db_session.commit()

    report = audit_server_client_addresses(db_session, sample_server.id)
    codes = [issue["code"] for issue in report["issues"]]
    assert report["healthy"] is False
    assert "duplicate_ipv4" in codes
    assert "ip_index_mismatch" in codes


def test_address_audit_accepts_consistent_rows(db_session, sample_server):
    db_session.add(_client(sample_server.id, "ok", 3, 7, "10.66.66.7"))
    db_session.commit()

    report = audit_server_client_addresses(db_session, sample_server.id)
    assert report["healthy"] is True
    assert report["issues"] == []
