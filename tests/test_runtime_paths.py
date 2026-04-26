from pathlib import Path


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
