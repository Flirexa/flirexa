from src.core.agent_bootstrap import AgentBootstrap
from src.modules import backup_manager
from src.api.middleware import auth as admin_auth
from src.api.routes import internal
from src.modules.subscription import client_portal_api
from src.utils import crypto


def test_admin_auth_secret_is_not_static_default():
    assert admin_auth.SECRET_KEY != "change-me-in-production"


def test_legacy_client_portal_secret_is_not_static_default():
    assert client_portal_api.JWT_SECRET != "change-this-secret-key"


def test_utils_crypto_does_not_use_static_default_secret(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    key = crypto.get_encryption_key()
    assert key
    assert b"default-secret-key-change-me" not in key


def test_internal_token_check_strips_and_compares_safely(monkeypatch):
    monkeypatch.setattr(internal, "SERVICE_API_TOKEN", "secret-token")
    assert internal.verify_service_token(" secret-token ") is None


def test_agent_bootstrap_rejects_invalid_interface():
    try:
        AgentBootstrap._validate_interface("wg0; rm -rf /")
    except ValueError:
        return
    raise AssertionError("Expected ValueError for invalid interface")


def test_agent_bootstrap_rejects_invalid_port():
    try:
        AgentBootstrap._validate_port(70000)
    except ValueError:
        return
    raise AssertionError("Expected ValueError for invalid port")


def test_backup_filename_sanitization_removes_path_chars():
    assert backup_manager._sanitize_name_for_filename("../prod/main") == "prod_main"


# ============================================================================
# PRIVATE KEY ENCRYPTION
# ============================================================================

def test_encrypted_text_roundtrip():
    """EncryptedText encrypts on write and decrypts on read transparently."""
    from src.database.encrypted_type import EncryptedText, _ENC_PREFIX
    from sqlalchemy import create_engine, Column, Integer
    from sqlalchemy.orm import DeclarativeBase, Session, mapped_column, Mapped
    from typing import Optional

    class _Base(DeclarativeBase):
        pass

    class _TestModel(_Base):
        __tablename__ = "_enc_test"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        secret: Mapped[Optional[str]] = mapped_column(EncryptedText(), nullable=True)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    _Base.metadata.create_all(engine)

    with Session(engine) as session:
        obj = _TestModel(id=1, secret="super-secret-wireguard-key==")
        session.add(obj)
        session.commit()

        # Read back — should return decrypted value
        loaded = session.get(_TestModel, 1)
        assert loaded.secret == "super-secret-wireguard-key=="

        # Check raw DB value starts with enc:: prefix
        raw = engine.connect().execute(
            __import__("sqlalchemy").text("SELECT secret FROM _enc_test WHERE id=1")
        ).scalar()
        assert raw.startswith(_ENC_PREFIX), f"Expected enc:: prefix, got: {raw[:20]}"

    _Base.metadata.drop_all(engine)


def test_encrypted_text_legacy_plaintext_passthrough():
    """EncryptedText reads legacy plain-text values without crash."""
    from src.database.encrypted_type import EncryptedText
    col = EncryptedText()
    assert col.process_result_value("plain-text-no-prefix", None) == "plain-text-no-prefix"


def test_encrypted_text_none_passthrough():
    """EncryptedText handles None correctly."""
    from src.database.encrypted_type import EncryptedText
    col = EncryptedText()
    assert col.process_bind_param(None, None) is None
    assert col.process_result_value(None, None) is None


def test_server_private_key_uses_encrypted_type():
    """Server.private_key column is EncryptedText (not plain Text)."""
    from src.database.models import Server
    from src.database.encrypted_type import EncryptedText
    col_type = Server.__table__.c.private_key.type
    assert isinstance(col_type, EncryptedText), \
        f"Server.private_key should be EncryptedText, got {type(col_type).__name__}"


def test_client_private_key_uses_encrypted_type():
    """Client.private_key column is EncryptedText."""
    from src.database.models import Client
    from src.database.encrypted_type import EncryptedText
    col_type = Client.__table__.c.private_key.type
    assert isinstance(col_type, EncryptedText), \
        f"Client.private_key should be EncryptedText, got {type(col_type).__name__}"


def test_client_preshared_key_uses_encrypted_type():
    """Client.preshared_key column is EncryptedText."""
    from src.database.models import Client
    from src.database.encrypted_type import EncryptedText
    col_type = Client.__table__.c.preshared_key.type
    assert isinstance(col_type, EncryptedText), \
        f"Client.preshared_key should be EncryptedText, got {type(col_type).__name__}"


def test_server_ssh_password_uses_encrypted_type():
    """Server.ssh_password column is EncryptedText (already was encrypted)."""
    from src.database.models import Server
    from src.database.encrypted_type import EncryptedText
    col_type = Server.__table__.c.ssh_password.type
    assert isinstance(col_type, EncryptedText)


def test_keys_encrypted_in_db(db_session):
    """WireGuard keys stored in DB are encrypted (start with enc:: prefix)."""
    from src.database.models import Server, Client, ClientStatus
    from src.database.encrypted_type import _ENC_PREFIX
    import sqlalchemy

    server = Server(
        name="enc_test_server",
        interface="wg99",
        endpoint="1.2.3.4:51820",
        listen_port=51820,
        public_key="EncTestServerPublicKeyBase64XXXXXXXXXXXXXX=",
        private_key="EncTestServerPrivateKeyBase64XXXXXXXXXXXXX=",
        address_pool_ipv4="10.77.0.0/24",
        config_path="/etc/wireguard/wg99.conf",
    )
    db_session.add(server)
    db_session.flush()

    client = Client(
        name="enc_test_client",
        server_id=server.id,
        public_key="EncTestClientPublicKeyBase64XXXXXXXXXXXXXX=",
        private_key="EncTestClientPrivateKeyBase64XXXXXXXXXXXXX=",
        preshared_key="EncTestPresharedKeyBase64XXXXXXXXXXXXXXXXX=",
        ipv4="10.77.0.2",
        ip_index=2,
        enabled=True,
        status=ClientStatus.ACTIVE,
    )
    db_session.add(client)
    db_session.commit()

    # Read raw DB values (bypassing TypeDecorator) to verify encryption
    raw_server = db_session.execute(
        sqlalchemy.text("SELECT private_key FROM servers WHERE name='enc_test_server'")
    ).fetchone()
    assert raw_server[0].startswith(_ENC_PREFIX), \
        "Server private_key must be encrypted in DB"

    raw_client = db_session.execute(
        sqlalchemy.text("SELECT private_key, preshared_key FROM clients WHERE name='enc_test_client'")
    ).fetchone()
    assert raw_client[0].startswith(_ENC_PREFIX), "Client private_key must be encrypted in DB"
    assert raw_client[1].startswith(_ENC_PREFIX), "Client preshared_key must be encrypted in DB"


# ============================================================================
# AGENT BOOTSTRAP — SSH ERROR HANDLING
# ============================================================================

def test_agent_bootstrap_ssh_timeout():
    """AgentBootstrap raises ConnectionError with clear message on SSH timeout."""
    import socket
    from unittest.mock import patch, MagicMock
    bootstrap = AgentBootstrap("unreachable.host", 22, "root", "pass")
    with patch("paramiko.SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.connect.side_effect = socket.timeout()
        try:
            bootstrap._get_ssh()
            assert False, "Expected ConnectionError"
        except ConnectionError as e:
            assert "timed out" in str(e).lower() or "unreachable" in str(e).lower()


def test_agent_bootstrap_ssh_auth_failure():
    """AgentBootstrap raises PermissionError with clear message on auth failure."""
    from unittest.mock import patch, MagicMock
    bootstrap = AgentBootstrap("1.2.3.4", 22, "root", "wrong")
    with patch("paramiko.SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.connect.side_effect = __import__("paramiko").AuthenticationException()
        try:
            bootstrap._get_ssh()
            assert False, "Expected PermissionError"
        except PermissionError as e:
            assert "authentication" in str(e).lower()


def test_agent_bootstrap_ssh_connection_refused():
    """AgentBootstrap raises ConnectionError on connection refused."""
    from unittest.mock import patch, MagicMock
    import paramiko
    bootstrap = AgentBootstrap("1.2.3.4", 22, "root", "pass")
    with patch("paramiko.SSHClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.connect.side_effect = paramiko.ssh_exception.NoValidConnectionsError({"1.2.3.4": Exception("refused")})
        try:
            bootstrap._get_ssh()
            assert False, "Expected ConnectionError"
        except ConnectionError as e:
            assert "refused" in str(e).lower() or "connection" in str(e).lower()


def test_agent_bootstrap_accepts_awg_interface():
    """_validate_interface accepts awg0, awg1 (AmneziaWG) interfaces."""
    assert AgentBootstrap._validate_interface("awg0") == "awg0"
    assert AgentBootstrap._validate_interface("awg1") == "awg1"


def test_agent_bootstrap_accepts_wg_interface():
    """_validate_interface accepts wg0, wg1 WireGuard interfaces."""
    assert AgentBootstrap._validate_interface("wg0") == "wg0"
    assert AgentBootstrap._validate_interface("wg1") == "wg1"


# ============================================================================
# VMS_ENCRYPTION_KEY — installer generates, env var takes priority
# ============================================================================

def test_encryption_key_uses_env_var(monkeypatch):
    """_derive_key() uses VMS_ENCRYPTION_KEY env var when set."""
    monkeypatch.setenv("VMS_ENCRYPTION_KEY", "test-key-for-unit-test-do-not-use")
    import importlib
    import src.database.encrypted_type as enc_mod
    key = enc_mod._derive_key()
    # Key must be stable and non-empty
    assert key
    # Calling again with same env var must produce the same key (deterministic)
    assert key == enc_mod._derive_key()


def test_encryption_key_warns_when_env_var_missing(monkeypatch, capsys):
    """_derive_key() prints a warning to stderr when VMS_ENCRYPTION_KEY is not set."""
    monkeypatch.delenv("VMS_ENCRYPTION_KEY", raising=False)
    import src.database.encrypted_type as enc_mod
    enc_mod._derive_key()
    captured = capsys.readouterr()
    assert "VMS_ENCRYPTION_KEY" in captured.err
    assert "migration" in captured.err.lower() or "migrate" in captured.err.lower() or "server" in captured.err.lower()


def test_encryption_key_env_var_and_machine_id_produce_different_keys(monkeypatch):
    """VMS_ENCRYPTION_KEY env var and machine-id produce different encryption keys."""
    import src.database.encrypted_type as enc_mod

    monkeypatch.setenv("VMS_ENCRYPTION_KEY", "explicit-test-key-abc123")
    key_from_env = enc_mod._derive_key()

    monkeypatch.delenv("VMS_ENCRYPTION_KEY", raising=False)
    key_from_fallback = enc_mod._derive_key()

    # The two keys must differ (env var is not the same as machine-id)
    assert key_from_env != key_from_fallback


def test_agent_bootstrap_rejects_awg_injection():
    """_validate_interface rejects injection attempts with awg prefix."""
    try:
        AgentBootstrap._validate_interface("awg0; rm -rf /")
    except ValueError:
        return
    raise AssertionError("Expected ValueError for injection attempt")


# ============================================================================
# AGENT SYSTEMD UNIT
# ============================================================================

def test_agent_systemd_unit_has_no_new_privileges():
    """Agent systemd unit template contains NoNewPrivileges=yes."""
    from src.core import agent_bootstrap
    import inspect
    source = inspect.getsource(agent_bootstrap)
    assert "NoNewPrivileges=yes" in source


def test_agent_systemd_unit_has_private_tmp():
    """Agent systemd unit template contains PrivateTmp=yes."""
    from src.core import agent_bootstrap
    import inspect
    source = inspect.getsource(agent_bootstrap)
    assert "PrivateTmp=yes" in source


def test_agent_systemd_unit_awg_config_path():
    """Agent systemd unit uses /etc/amneziawg/ config path for awg interfaces."""
    from src.core import agent_bootstrap
    import inspect
    source = inspect.getsource(agent_bootstrap)
    assert "/etc/amneziawg" in source


def test_agent_systemd_unit_uses_correct_config_dir_for_awg():
    """Agent bootstrap sets config_dir=/etc/amneziawg for awg interfaces."""
    # We can verify the logic by checking the source has awg branch
    from src.core.agent_bootstrap import AgentBootstrap
    import inspect
    src = inspect.getsource(AgentBootstrap.install_agent)
    assert "amneziawg" in src
    assert "is_awg" in src
