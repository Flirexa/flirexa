from src.utils.runtime_paths import get_backup_root


def test_version_file_prefers_current_runtime(tmp_path, monkeypatch):
    install_root = tmp_path / "install"
    install_root.mkdir()
    current = install_root / "current"
    current.mkdir()

    (install_root / "VERSION").write_text("1.0.0\n")
    (current / "VERSION").write_text("1.0.1\n")

    monkeypatch.setenv("INSTALL_DIR", str(install_root))

    from src.utils.runtime_paths import get_runtime_root, get_version_file

    assert get_runtime_root() == current
    assert get_version_file() == current / "VERSION"


def test_version_file_falls_back_to_install_root(tmp_path, monkeypatch):
    install_root = tmp_path / "install"
    install_root.mkdir()
    (install_root / "VERSION").write_text("1.0.0\n")

    monkeypatch.setenv("INSTALL_DIR", str(install_root))

    from src.utils.runtime_paths import get_runtime_root, get_version_file

    assert get_runtime_root() == install_root
    assert get_version_file() == install_root / "VERSION"


def test_app_version_reads_runtime_version(tmp_path, monkeypatch):
    install_root = tmp_path / "install"
    current = install_root / "current"
    current.mkdir(parents=True)
    (current / "VERSION").write_text("2.2.52\n")
    monkeypatch.setenv("INSTALL_DIR", str(install_root))
    monkeypatch.delenv("APP_VERSION", raising=False)

    from src.utils.runtime_paths import get_app_version

    assert get_app_version() == "2.2.52"


def test_app_version_honors_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv("INSTALL_DIR", str(tmp_path))
    monkeypatch.setenv("APP_VERSION", "9.9.9-test")

    from src.utils.runtime_paths import get_app_version

    assert get_app_version() == "9.9.9-test"


def test_explicit_backup_path_takes_precedence(monkeypatch, tmp_path):
    backup_dir = tmp_path / "operator-backups"
    monkeypatch.setenv("VMS_BACKUP_DIR", str(backup_dir))

    assert get_backup_root(tmp_path / "install") == backup_dir.resolve()


def test_blank_backup_override_uses_persistent_install_root(monkeypatch, tmp_path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    monkeypatch.setenv("INSTALL_DIR", str(install_dir))
    monkeypatch.setenv("VMS_BACKUP_DIR", "")

    assert get_backup_root() == install_dir / "backups"
