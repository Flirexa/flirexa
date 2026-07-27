"""Regression contracts for nginx/TLS provisioning."""

import os
from pathlib import Path
import re
import subprocess


WEB_ACCESS_SCRIPT = Path("scripts/configure-web-access.sh")


def _function_library(tmp_path: Path) -> Path:
    source = WEB_ACCESS_SCRIPT.read_text(encoding="utf-8")
    library_source, entrypoint = source.rsplit('\nmain "$@"', 1)
    assert not entrypoint.strip()
    library = tmp_path / "configure-web-access-functions.sh"
    library.write_text(library_source, encoding="utf-8")
    return library


def _fake_openssl(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    counter = tmp_path / "generation-count"
    executable = fake_bin / "openssl"
    executable.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

if [[ " $* " == *" -check "* ]]; then
    input=""
    while [[ $# -gt 0 ]]; do
        if [[ "$1" == "-in" ]]; then
            input="$2"
            break
        fi
        shift
    done
    [[ -n "$input" ]] && grep -qx "VALID-DHPARAM" "$input"
    exit
fi

output=""
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "-out" ]]; then
        output="$2"
        break
    fi
    shift
done
[[ -n "$output" ]]
printf 'generated\n' >> "$FAKE_OPENSSL_COUNTER"
printf 'VALID-DHPARAM\n' > "$output"
[[ "${FAKE_OPENSSL_FAIL:-0}" != "1" ]]
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return fake_bin, counter


def _run_ensure_dhparam(
    tmp_path: Path,
    *,
    initial_content: str | None = None,
    fail_generation: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    library = _function_library(tmp_path)
    fake_bin, counter = _fake_openssl(tmp_path)
    dhparam = tmp_path / "ssl" / "vpnmanager-dhparam.pem"
    if initial_content is not None:
        dhparam.parent.mkdir()
        dhparam.write_text(initial_content, encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_OPENSSL_COUNTER": str(counter),
            "FAKE_OPENSSL_FAIL": "1" if fail_generation else "0",
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; DHPARAM="$2"; ensure_dhparam; ensure_dhparam',
            "bash",
            str(library),
            str(dhparam),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    return result, dhparam, counter


def test_self_signed_mode_prepares_dhparam_before_rendering_nginx():
    source = WEB_ACCESS_SCRIPT.read_text(encoding="utf-8")
    body = re.search(
        r"apply_selfsigned_ip_mode\(\) \{(?P<body>.*?)\n\}\n\nwrite_final_config",
        source,
        flags=re.DOTALL,
    )

    assert body is not None
    function_body = body.group("body")
    assert function_body.index("ensure_dhparam") < function_body.index(
        'cat > "$NGINX_CONF"'
    )
    assert function_body.index("ensure_dhparam") < function_body.rindex("nginx -t")


def test_dhparam_generation_is_validated_atomic_and_idempotent(tmp_path: Path):
    result, dhparam, counter = _run_ensure_dhparam(
        tmp_path,
        initial_content="PARTIAL\n",
    )

    assert result.returncode == 0, result.stderr
    assert dhparam.read_text(encoding="utf-8") == "VALID-DHPARAM\n"
    assert counter.read_text(encoding="utf-8").splitlines() == ["generated"]
    assert not list(dhparam.parent.glob("vpnmanager-dhparam.pem.tmp.*"))
    assert dhparam.stat().st_mode & 0o777 == 0o644


def test_failed_dhparam_generation_leaves_no_partial_target(tmp_path: Path):
    result, dhparam, _counter = _run_ensure_dhparam(
        tmp_path,
        fail_generation=True,
    )

    assert result.returncode != 0
    assert "Failed to generate valid DH parameters" in result.stderr
    assert not dhparam.exists()
    assert not list(dhparam.parent.glob("vpnmanager-dhparam.pem.tmp.*"))
