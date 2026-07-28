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


def test_web_package_install_retries_and_keeps_failure_diagnostics():
    source = WEB_ACCESS_SCRIPT.read_text(encoding="utf-8")

    assert "wait_for_package_manager()" in source
    assert "for attempt in 1 2 3 4 5" in source
    assert "DPkg::Lock::Timeout=60" in source
    assert 'tail -n 8 "$apt_log"' in source
    assert 'rm -f -- "$apt_log"' in source


def test_web_package_command_retries_until_success(tmp_path: Path):
    library = _function_library(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    counter = tmp_path / "apt-count"
    apt = fake_bin / "apt-get"
    apt.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
count=0
[[ ! -f "$FAKE_APT_COUNTER" ]] || count="$(<"$FAKE_APT_COUNTER")"
count=$((count + 1))
printf '%s\n' "$count" > "$FAKE_APT_COUNTER"
if (( count < 3 )); then
    printf 'simulated apt failure %s\n' "$count" >&2
    exit 42
fi
""",
        encoding="utf-8",
    )
    apt.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_APT_COUNTER": str(counter),
        }
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; wait_for_package_manager() { return 0; }; '
                'sleep() { :; }; apt_retry "install test packages" install -y nginx'
            ),
            "bash",
            str(library),
        ],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert counter.read_text(encoding="utf-8").strip() == "3"
    assert "attempt 1/5" in result.stdout
    assert "simulated apt failure 2" in result.stderr


def test_self_signed_mode_does_not_install_unneeded_certbot_packages():
    source = WEB_ACCESS_SCRIPT.read_text(encoding="utf-8")
    package_body = source[
        source.index("install_packages() {"):
        source.index("# Generate a valid 2048-bit DH group")
    ]

    assert "local required=(nginx openssl)" in package_body
    assert (
        'if [[ "$MODE" == "portal_admin_ip" || '
        '"$MODE" == "portal_admin_domain" ]]' in package_body
    )
    assert "required+=(certbot python3-certbot-nginx)" in package_body


def test_env_file_is_parsed_as_data_and_never_executed(tmp_path: Path):
    library = _function_library(tmp_path)
    marker = tmp_path / "must-not-exist"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "API_PORT=10086",
                "CLIENT_PORTAL_PORT=10090",
                "SERVER_ENDPOINT=203.0.113.10:51820 # Automatically detected",
                "CERTBOT_EMAIL=from-env@example.com",
                f"MALICIOUS=$(touch {marker})",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; ENV_FILE="$2"; '
                'CERTBOT_EMAIL="cli@example.com"; load_env; '
                'printf "%s|%s|%s\\n" "$API_PORT" "$SERVER_ENDPOINT" '
                '"$CERTBOT_EMAIL"'
            ),
            "bash",
            str(library),
            str(env_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "10086|203.0.113.10:51820|cli@example.com\n"
    assert not marker.exists()


def test_blank_value_with_inline_comment_stays_blank(tmp_path: Path):
    library = _function_library(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "API_PORT=10086\n"
        "CLIENT_PORTAL_PORT=10090\n"
        "SERVER_ENDPOINT= # Automatically detected when needed\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; ENV_FILE="$2"; load_env; printf "<%s>\\n" "$SERVER_ENDPOINT"',
            "bash",
            str(library),
            str(env_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "<>\n"
