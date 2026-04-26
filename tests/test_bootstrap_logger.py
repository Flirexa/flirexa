from src.database.models import AuditAction, AuditLog, Server, ServerBootstrapLog, ServerStatus
from src.modules.bootstrap_logger import mark_interrupted_tasks


def test_mark_interrupted_tasks_marks_related_server_error(db_session, monkeypatch):
    server = Server(
        name="bootstrap-target",
        interface="wg99",
        endpoint="1.2.3.4:51820",
        public_key="A" * 43 + "=",
        private_key="B" * 43 + "=",
        address_pool_ipv4="10.66.66.0/24",
        dns="1.1.1.1",
        max_clients=10,
        config_path="/etc/wireguard/wg99.conf",
        status=ServerStatus.OFFLINE,
    )
    db_session.add(server)
    db_session.commit()
    db_session.refresh(server)

    rec = ServerBootstrapLog(task_id="task-1", server_id=server.id, status="running")
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)

    monkeypatch.setattr("src.database.connection.SessionLocal", lambda: db_session)
    db_session.close = lambda: None

    mark_interrupted_tasks()

    db_session.refresh(rec)
    db_session.refresh(server)

    assert rec.status == "interrupted"
    assert rec.error is not None
    assert server.status == ServerStatus.ERROR

    audit = (
        db_session.query(AuditLog)
        .filter_by(target_id=server.id, action=AuditAction.SERVER_STATUS_CHANGE)
        .first()
    )
    assert audit is not None
    assert audit.details["reason"] == "bootstrap_interrupted_on_api_restart"
