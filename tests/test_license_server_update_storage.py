from pathlib import Path
import subprocess


TOOL = Path("license_server/tools/prepare_update_storage.sh")


def test_update_storage_permission_tool_is_guarded_and_valid_shell():
    source = TOOL.read_text(encoding="utf-8")

    subprocess.run(["bash", "-n", str(TOOL)], check=True)
    assert "EUID" in source
    assert '"$LICENSE_ROOT" == "/"' in source
    assert 'install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0775' in source
    assert 'runuser -u "$SERVICE_USER" -- test -w "$path"' in source
    assert "chown -R" not in source
