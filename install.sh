#!/bin/bash
#===============================================================================
# Flirexa — Smart Installer
# Fully automated installation for Debian/Ubuntu servers
#
# Features:
#   - Admin panel with JWT authentication (first-run setup wizard)
#   - Client portal with subscription plans & crypto payments
#   - Telegram bots (admin + client) — configure via web UI
#   - Agent mode for remote WireGuard management
#   - Backup/restore, traffic rules, bandwidth limits
#
# Usage:
#   bash install.sh                          — interactive install
#   bash install.sh --non-interactive        — auto install (uses env vars)
#   bash install.sh --install-dir /custom    — custom install path
#
# Non-interactive env vars:
#   SB_ADMIN_TOKEN      — Telegram admin bot token (optional, configure later)
#   SB_ADMIN_USERS      — Comma-separated admin Telegram user IDs
#   SB_CLIENT_TOKEN     — Telegram client bot token (optional)
#   SB_ENDPOINT         — WireGuard server endpoint ip:port (auto-detected)
#   SB_DB_PASSWORD      — PostgreSQL password (generated if empty)
#   SB_SUPPORT_EMAIL    — Opt in to one help email if installation fails
#===============================================================================

set -euo pipefail

# ─── Per-phase telemetry to the license server ────────────────────────────────
#
# The outer landing/install.sh exports INSTALL_ID / UPDATE_SERVER /
# UPDATE_SERVER_PRIMARY / CHANNEL / INSTALL_LOG / INSTALL_TELEMETRY so we
# can fire our own beacons from each major install step. Without these a
# failed attempt can end at "inner_start" with no indication of the phase
# that failed.
# Best-effort: any failure to beacon is silently dropped, never blocks
# the install. `INSTALL_TELEMETRY=off` skips entirely (privacy opt-out).
INSTALL_ID="${INSTALL_ID:-no-id}"
INSTALL_TELEMETRY="${INSTALL_TELEMETRY:-on}"
# Outer landing/install.sh selects UPDATE_SERVER (primary or backup
# fallback) BEFORE invoking us, then exports it. We just inherit
# whatever it picked — don't hardcode the backup host as a default
# here, that would leak operator infra into the open-core mirror.
UPDATE_SERVER="${UPDATE_SERVER:-https://flirexa.biz}"
CHANNEL="${CHANNEL:-stable}"
INSTALL_LOG="${INSTALL_LOG:-/tmp/vpnmanager-install-${INSTALL_ID}.log}"
INSTALL_SUPPORT_EMAIL="${INSTALL_SUPPORT_EMAIL:-}"
INSTALL_SUPPORT_OPT_IN="${INSTALL_SUPPORT_OPT_IN:-0}"
INSTALL_SUPPORT_PROMPTED="${INSTALL_SUPPORT_PROMPTED:-0}"

# Track which phase we're in so the EXIT trap can label an unexpected death.
CURRENT_PHASE="boot"
_PHASE_REPORTED=0

_inner_beacon() {
    [[ "$INSTALL_TELEMETRY" == "off" ]] && return 0
    local step="$1" status="$2" exit_code="${3:-}" tail_file="${4:-}"
    local server="${UPDATE_SERVER:-$UPDATE_SERVER_PRIMARY}"
    command -v python3 >/dev/null 2>&1 || return 0
    local payload
    payload="$(
        STEP="$step" STATUS="$status" EXIT_CODE="$exit_code" \
        LOG_TAIL_FILE="$tail_file" INSTALL_ID="$INSTALL_ID" \
        CHANNEL="$CHANNEL" PHASE="$CURRENT_PHASE" \
        VERSION="${VERSION:-${APP_VERSION:-}}" \
        SUPPORT_EMAIL="$INSTALL_SUPPORT_EMAIL" \
        SUPPORT_OPT_IN="$INSTALL_SUPPORT_OPT_IN" \
        python3 - <<'PY' 2>/dev/null
import json, os, pathlib
tail = ""
tf = os.environ.get("LOG_TAIL_FILE") or ""
if tf and pathlib.Path(tf).exists():
    try:
        with open(tf, "rb") as f:
            f.seek(0, 2); size = f.tell()
            f.seek(max(0, size - 32_000))
            chunk = f.read().decode("utf-8", errors="replace")
        tail = "\n".join(chunk.splitlines()[-100:])
        if len(tail) > 16_000: tail = tail[-16_000:]
    except Exception:
        tail = ""
out = {
    "install_id": os.environ.get("INSTALL_ID", ""),
    "step":       os.environ.get("STEP", ""),
    "status":     os.environ.get("STATUS", ""),
    "channel":    os.environ.get("CHANNEL", ""),
    "version":    os.environ.get("VERSION", ""),
}
if os.environ.get("SUPPORT_OPT_IN") == "1" and os.environ.get("SUPPORT_EMAIL"):
    out["support_opt_in"] = True
    out["support_email"] = os.environ["SUPPORT_EMAIL"]
ec = os.environ.get("EXIT_CODE", "")
if ec:
    try: out["exit_code"] = int(ec)
    except ValueError: pass
if tail:
    out["log_tail"] = tail
print(json.dumps(out))
PY
    )"
    [[ -n "$payload" ]] || return 0
    curl -fsS --max-time 5 -X POST "${server}/api/install-event" \
        -H "Content-Type: application/json" -d "$payload" >/dev/null 2>&1 || true
}

# Wrap a phase: beacon begin → run → beacon ok/fail (with log tail on fail).
# Sets CURRENT_PHASE so the EXIT trap can attribute a hung / killed install
# to whatever was running at the time.
_phase() {
    local name="$1"; shift
    local rc=0
    CURRENT_PHASE="$name"
    _PHASE_REPORTED=0
    _inner_beacon "$name" "begin"
    "$@" || rc=$?
    if (( rc == 0 )); then
        _PHASE_REPORTED=1
        _inner_beacon "$name" "ok"
        return 0
    fi
    _PHASE_REPORTED=1
    _inner_beacon "$name" "fail" "$rc" "$INSTALL_LOG"
    return "$rc"
}

# Safety net: if the script dies in the middle of a phase (signal, OOM,
# user closed terminal mid-`curl | bash`, `set -e` triggered) and we
# haven't already beaconed for the current phase, fire `inner_died` with
# whatever phase we were in. Best-effort; this trap MUST never raise.
_inner_exit_trap() {
    local rc=$?
    if (( rc != 0 )) && (( _PHASE_REPORTED == 0 )); then
        _inner_beacon "${CURRENT_PHASE}_died" "fail" "$rc" "$INSTALL_LOG" || true
    fi
}
trap _inner_exit_trap EXIT

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
if [ -z "$PYTHON_VERSION" ]; then
    echo "ERROR: Python 3 is required but not found"
    exit 1
fi
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "ERROR: Python 3.10+ is required (found $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION detected"

# ============================================================================
# CONFIGURATION
# ============================================================================
APP_NAME="Flirexa"
INSTALL_DIR="/opt/vpnmanager"
LICENSE_SERVER_URL="${SB_LICENSE_SERVER_URL:-https://flirexa.biz}"
UPDATE_SERVER_URL="${SB_UPDATE_SERVER_URL:-https://flirexa.biz}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_VERSION="$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo 1.3.0)"
INSTALLER_VERSION="$APP_VERSION"
# The public wrapper already knows the manifest version. Direct executions do
# not, so use the package VERSION file as the authoritative fallback and make
# the value available to every inner telemetry beacon.
VERSION="${VERSION:-$APP_VERSION}"
export VERSION

# Official customer archives contain manylinux x86-64 native extensions. The
# source-based open core has no such file and remains architecture-neutral.
if [[ -f "$SCRIPT_DIR/src/api/main.abi3.so" ]]; then
    MACHINE_ARCH="$(uname -m 2>/dev/null || true)"
    if [[ "$MACHINE_ARCH" != "x86_64" && "$MACHINE_ARCH" != "amd64" ]]; then
        echo "ERROR: This Flirexa customer build requires Linux x86_64 (found ${MACHINE_ARCH:-unknown})"
        exit 1
    fi
fi
NON_INTERACTIVE=false
EXISTING_INSTALL=false
DB_USER="vpnmanager"
DB_NAME="vpnmanager_db"
DB_PASS="${SB_DB_PASSWORD:-}"
WEB_SETUP_MODE="${SB_WEB_SETUP_MODE:-none}"
WEB_PORTAL_DOMAIN="${SB_CLIENT_PORTAL_DOMAIN:-}"
WEB_ADMIN_DOMAIN="${SB_ADMIN_PANEL_DOMAIN:-}"
WEB_CERTBOT_EMAIL="${SB_CERTBOT_EMAIL:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

die() { log_error "$1"; exit 1; }


_valid_support_email() {
    local value="$1"
    [[ ${#value} -le 254 ]] || return 1
    [[ "$value" != *".."* ]] || return 1
    [[ "$value" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$ ]]
}


_collect_support_contact() {
    [[ "$INSTALL_SUPPORT_PROMPTED" == "1" ]] && return 0
    INSTALL_SUPPORT_PROMPTED=1
    export INSTALL_SUPPORT_PROMPTED

    [[ "$INSTALL_TELEMETRY" == "off" ]] && return 0

    local candidate="${SB_SUPPORT_EMAIL:-}"
    if [[ -n "$candidate" ]]; then
        if _valid_support_email "$candidate"; then
            INSTALL_SUPPORT_EMAIL="$candidate"
            INSTALL_SUPPORT_OPT_IN=1
            export INSTALL_SUPPORT_EMAIL INSTALL_SUPPORT_OPT_IN
            log_success "Installation help enabled for the provided email."
        else
            log_warn "SB_SUPPORT_EMAIL is invalid; automatic help email disabled."
        fi
        return 0
    fi

    [[ "$NON_INTERACTIVE" == "true" ]] && return 0
    if ! exec 9</dev/tty 2>/dev/null; then
        return 0
    fi

    echo -e "${BOLD}Optional installation help${NC}"
    echo "  Enter your email if you want us to contact you once if this install fails."
    echo "  No marketing messages. Press Enter to skip."
    while true; do
        read -r -p "  Support email (optional): " candidate <&9 || candidate=""
        if [[ -z "$candidate" ]]; then
            break
        fi
        if _valid_support_email "$candidate"; then
            INSTALL_SUPPORT_EMAIL="$candidate"
            INSTALL_SUPPORT_OPT_IN=1
            log_success "We will send one help email only if this installation fails."
            break
        fi
        log_warn "Please enter a valid email address or press Enter to skip."
    done
    exec 9<&- || true
    export INSTALL_SUPPORT_EMAIL INSTALL_SUPPORT_OPT_IN
    echo ""
}

# ────────────────────────────────────────────────────────────────────────────
# Progress / ETA helpers
#
# Each of the 8 steps has a hardcoded cold-install estimate. log_step starts
# a step and prints the ETA banner; log_step_done closes it and renders a
# progress bar with elapsed/remaining time. Hot-cache reinstalls finish
# faster than the estimates — the numbers are an upper-ish bound, not a
# promise. Keeps the UX honest under "this is taking forever" panic.
# ────────────────────────────────────────────────────────────────────────────
INSTALL_START_TS=$(date +%s)
CURRENT_STEP=0
CURRENT_STEP_START_TS=0
STEP_ESTIMATES_S=(120 60 30 120 10 30 10 30)   # 8 steps, seconds each
TOTAL_ESTIMATE_S=0
for _e in "${STEP_ESTIMATES_S[@]}"; do TOTAL_ESTIMATE_S=$((TOTAL_ESTIMATE_S + _e)); done

_fmt_duration() {
    # 137 → "2m 17s" ; 45 → "45s" ; 0 → "<1s"
    local s=$1
    [ "$s" -le 0 ] && { echo "<1s"; return; }
    local m=$((s / 60)) sec=$((s % 60))
    if [ "$m" -gt 0 ]; then
        if [ "$sec" -gt 0 ]; then echo "${m}m ${sec}s"; else echo "${m}m"; fi
    else
        echo "${sec}s"
    fi
}

_progress_bar() {
    local pct=$1 width=24 filled
    [ "$pct" -gt 100 ] && pct=100
    [ "$pct" -lt 0 ]   && pct=0
    filled=$(( pct * width / 100 ))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=filled; i<width; i++)); do bar+="░"; done
    echo -e "${BLUE}[${bar}]${NC} ${pct}%"
}

log_step() {
    # log_step N "Title"
    local n="$1" title="$2"
    CURRENT_STEP="$n"
    CURRENT_STEP_START_TS=$(date +%s)
    local est=${STEP_ESTIMATES_S[$((n - 1))]}
    log_info "[${n}/8] ${title}  (≈$(_fmt_duration "$est") cold)"
}

log_step_done() {
    # Call at end of each step. Renders bar + elapsed/remaining.
    local now=$(date +%s)
    local step_elapsed=$((now - CURRENT_STEP_START_TS))
    local total_elapsed=$((now - INSTALL_START_TS))
    local steps_done="$CURRENT_STEP"
    local pct=$(( steps_done * 100 / 8 ))

    # Sum of estimates for remaining steps
    local remaining_est=0
    for ((i=steps_done; i<8; i++)); do
        remaining_est=$((remaining_est + STEP_ESTIMATES_S[i]))
    done

    local bar
    bar=$(_progress_bar "$pct")
    printf '%b · %d/8 done · elapsed %s · ~%s remaining\n' \
        "$bar" "$steps_done" "$(_fmt_duration "$total_elapsed")" "$(_fmt_duration "$remaining_est")"
    echo ""
}

# ============================================================================
# PARSE ARGUMENTS
# ============================================================================
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --non-interactive) NON_INTERACTIVE=true ;;
            --install-dir)     INSTALL_DIR="$2"; shift ;;
            --help|-h)
                echo "Usage: bash install.sh [--non-interactive] [--install-dir /path]"
                echo ""
                echo "Options:"
                echo "  --non-interactive   Use env vars instead of prompts"
                echo "  --install-dir PATH  Install to custom directory (default: /opt/vpnmanager)"
                echo ""
                echo "Non-interactive env vars:"
                echo "  SB_ADMIN_TOKEN      Admin bot token (optional, configure via web UI later)"
                echo "  SB_ADMIN_USERS      Admin user IDs, comma-separated"
                echo "  SB_CLIENT_TOKEN     Client bot token (optional)"
                echo "  SB_ENDPOINT         WireGuard endpoint ip:port (auto-detected if empty)"
                echo "  SB_DB_PASSWORD      PostgreSQL password (auto-generated if empty)"
                echo "  SB_WEB_SETUP_MODE   none|portal_admin_ip|portal_admin_domain|auto_selfsigned_ip"
                echo "  SB_CLIENT_PORTAL_DOMAIN  portal.example.com"
                echo "  SB_ADMIN_PANEL_DOMAIN    admin.example.com (when using portal_admin_domain)"
                echo "  SB_CERTBOT_EMAIL    Email for Let's Encrypt notices"
                exit 0
                ;;
            *) log_warn "Unknown option: $1" ;;
        esac
        shift
    done
}

# ============================================================================
# HELPER: Generate secure random string
# ============================================================================
generate_secret() {
    python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null \
        || openssl rand -hex 32 2>/dev/null \
        || head -c 32 /dev/urandom | xxd -p | tr -d '\n'
}

generate_password() {
    python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20)))" 2>/dev/null \
        || openssl rand -base64 15 2>/dev/null \
        || head -c 15 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 20
}

sed_escape_replacement() {
    printf '%s' "$1" | sed -e 's/[\&|]/\\&/g'
}

# ============================================================================
# 1. PRE-FLIGHT CHECKS
# ============================================================================
preflight() {
    log_info "Cold-install estimate: ~$(_fmt_duration "$TOTAL_ESTIMATE_S") on a fresh Ubuntu/Debian. Reinstalls / hot-cache hosts finish faster."
    echo ""
    log_info "Pre-flight checks..."

    # Root check
    [[ $EUID -eq 0 ]] || die "This script requires root. Run: sudo bash install.sh"

    # OS check
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        case "$ID" in
            debian|ubuntu|linuxmint|pop) ;;
            *) log_warn "Untested OS: $ID. Proceeding anyway (Debian/Ubuntu recommended)." ;;
        esac
        log_info "  OS: $PRETTY_NAME"
    else
        log_warn "Cannot detect OS. Proceeding..."
    fi

    # Disk space (need 500MB+)
    local avail_mb
    avail_mb=$(df -m / | awk 'NR==2{print $4}')
    if [[ "$avail_mb" -lt 500 ]]; then
        die "Not enough disk space: ${avail_mb}MB available, need 500MB+"
    fi
    log_info "  Disk: ${avail_mb}MB free"

    # RAM — pip install of the panel's wheels easily eats 500-700 MB peak,
    # and apt-get + alembic on top of that pushes a 1 GB box into OOM
    # territory. We've seen this kill installs silently (the OOM killer
    # nukes bash before the failure beacon can fire). Catch it here with
    # a clear error + dedicated beacon so we know who bounced and why.
    # Counts swap toward the total because the outer landing/install.sh
    # already adds a swapfile on low-RAM boxes. Set
    # SB_SKIP_RAM_CHECK=1 to bypass (power-users on weird memcg setups).
    local ram_mb total_mb swap_mb effective_mb
    if [[ -r /proc/meminfo ]]; then
        ram_mb=$(awk '/^MemAvailable:/{printf "%d", $2/1024; exit}' /proc/meminfo)
        total_mb=$(awk '/^MemTotal:/{printf "%d", $2/1024; exit}' /proc/meminfo)
        swap_mb=$(awk '/^SwapTotal:/{printf "%d", $2/1024; exit}' /proc/meminfo)
        effective_mb=$(( total_mb + swap_mb ))
        log_info "  RAM:  ${ram_mb}MB available (${total_mb}MB physical + ${swap_mb}MB swap = ${effective_mb}MB effective)"
        if [[ "${SB_SKIP_RAM_CHECK:-0}" == "1" ]]; then
            log_warn "  SB_SKIP_RAM_CHECK=1 — skipping RAM gate (you'd better know what you're doing)"
        elif [[ "${effective_mb:-0}" -lt 1500 ]]; then
            _inner_beacon "low_ram" "fail" "1" || true
            _PHASE_REPORTED=1
            die "Not enough RAM: ${total_mb}MB physical + ${swap_mb}MB swap = ${effective_mb}MB effective, need 1500MB+ (2GB recommended). pip install will OOM otherwise. Resize the VPS to at least 2GB OR add swap, then re-run."
        fi
    fi

    # Check source files
    if [[ ! -f "$SCRIPT_DIR/main.py" ]]; then
        die "Source files not found in $SCRIPT_DIR. Run from the project directory."
    fi
    if [[ ! -f "$SCRIPT_DIR/requirements.txt" ]]; then
        die "requirements.txt not found in $SCRIPT_DIR"
    fi

    log_success "Pre-flight OK"
}

# ============================================================================
# 2. DETECT EXISTING INSTALLATION
# ============================================================================
detect_existing() {
    log_info "Checking for existing installation..."

    local found=false

    # Check target directory
    if [[ -f "$INSTALL_DIR/main.py" ]] && [[ -f "$INSTALL_DIR/.env" ]]; then
        found=true
        log_warn "Existing installation found at $INSTALL_DIR"

        if [[ -z "$DB_PASS" ]]; then
            local parsed_db
            parsed_db=$(python3 - "$INSTALL_DIR/.env" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import sys
env_path = Path(sys.argv[1])
for line in env_path.read_text().splitlines():
    if line.startswith("DATABASE_URL="):
        parsed = urlparse(line.split("=", 1)[1])
        print(parsed.password or "")
        break
PY
)
            if [[ -n "$parsed_db" ]]; then
                DB_PASS="$parsed_db"
                log_info "  Reusing existing database password from .env"
            fi
        fi
    fi

    # Check systemd services
    if systemctl list-unit-files 2>/dev/null | grep -q "vpnmanager-api.service"; then
        found=true
        log_warn "Systemd services already installed"
    fi

    if [[ "$found" == "true" ]]; then
        EXISTING_INSTALL=true
        log_info "Creating backup before upgrade..."

        local backup_dir="/root/vpnmanager_backups/pre-install-$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"

        # Backup .env
        [[ -f "$INSTALL_DIR/.env" ]] && cp "$INSTALL_DIR/.env" "$backup_dir/.env.backup"

        # Backup database
        if command -v pg_dump >/dev/null 2>&1; then
            sudo -u postgres pg_dump "$DB_NAME" > "$backup_dir/db_backup.sql" 2>/dev/null || true
        fi

        log_success "Backup saved to $backup_dir"

        # Stop running services
        log_info "Stopping existing services..."
        systemctl stop vpnmanager-api 2>/dev/null || true
        systemctl stop vpnmanager-admin-bot 2>/dev/null || true
        systemctl stop vpnmanager-client-bot 2>/dev/null || true
        systemctl stop vpnmanager-client-portal 2>/dev/null || true
        # The worker imports application modules once at process startup.  It
        # must be stopped before files are replaced or an upgraded install can
        # keep executing the previous scheduler/payment code from memory.
        systemctl stop vpnmanager-worker 2>/dev/null || true

        # Kill any manual processes
        pkill -f "main.py api" 2>/dev/null || true
        pkill -f "main.py admin-bot" 2>/dev/null || true
        pkill -f "main.py client-bot" 2>/dev/null || true
        pkill -f "client_portal_main.py" 2>/dev/null || true
        pkill -f "worker_main.py" 2>/dev/null || true
        sleep 2
    fi
}

# ============================================================================
# 3. INSTALL SYSTEM DEPENDENCIES
# ============================================================================
install_system_deps() {
    log_step 1 "Installing system dependencies..."

    wait_for_apt_locks() {
        local locks=(
            /var/lib/dpkg/lock-frontend
            /var/lib/dpkg/lock
            /var/cache/apt/archives/lock
        )
        local waited=0
        while true; do
            local lock_found=false
            for lock in "${locks[@]}"; do
                if fuser "$lock" >/dev/null 2>&1; then
                    lock_found=true
                    break
                fi
            done
            if [[ "$lock_found" == "false" ]]; then
                return 0
            fi
            sleep 2
            waited=$((waited+2))
            if (( waited % 30 == 0 )); then
                log_warn "  Waiting for apt/dpkg lock to clear (${waited}s)..."
            fi
            if [[ "$waited" -ge 300 ]]; then
                return 1
            fi
        done
    }

    apt_update_retry() {
        for i in $(seq 1 10); do
            wait_for_apt_locks || true
            if apt-get update -qq 2>/tmp/vpnmanager-apt-update.err; then
                return 0
            fi
            if grep -qi "Could not get lock\\|Unable to acquire the dpkg frontend lock" /tmp/vpnmanager-apt-update.err 2>/dev/null; then
                log_warn "  apt-get update waiting for package manager lock (attempt $i)..."
            else
                log_warn "  apt-get update failed (attempt $i), retrying..."
            fi
            rm -rf /var/lib/apt/lists/* 2>/dev/null || true
            sleep 3
        done
        return 1
    }

    apt_install_retry() {
        local stderr_file=/tmp/vpnmanager-apt-install.err
        local attempts=${1:-8}
        shift
        for i in $(seq 1 "$attempts"); do
            wait_for_apt_locks || true
            if DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" 2>"$stderr_file"; then
                return 0
            fi
            if grep -qi "Could not get lock\\|Unable to acquire the dpkg frontend lock" "$stderr_file" 2>/dev/null; then
                log_warn "  apt-get install waiting for package manager lock (attempt $i)..."
            else
                tail -5 "$stderr_file" 2>/dev/null || true
            fi
            sleep 3
        done
        return 1
    }

    can_create_virtualenv() {
        local probe_dir
        probe_dir=$(mktemp -d /tmp/vpnmanager-venv-probe.XXXXXX)
        if python3 -m venv "$probe_dir/env" >/dev/null 2>&1; then
            rm -rf "$probe_dir"
            return 0
        fi
        rm -rf "$probe_dir"
        return 1
    }

    # Stop background apt services to avoid lock contention
    systemctl stop unattended-upgrades apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
    pkill -f packagekit >/dev/null 2>&1 || true
    wait_for_apt_locks

    # Update package lists
    if ! apt_update_retry; then
        die "apt-get update failed. Check DNS/network connectivity and try again."
    fi

    # Ensure apt can work (minimal packages that may be missing on bare systems)
    apt_install_retry 5 apt-transport-https ca-certificates gnupg lsb-release sudo >/dev/null 2>&1 || true

    # Core packages
    local packages=(
        python3
        python3-venv
        python3-dev
        python3-pip
        postgresql
        postgresql-contrib
        wireguard-tools
        curl
        wget
        rsync
        iproute2
        iptables
        net-tools
        libpq-dev
        gcc
        openssl
    )

    apt_install_retry 8 "${packages[@]}" || {
        log_error "Failed to install system packages"
        log_info "Attempting packages one by one..."
        for pkg in "${packages[@]}"; do
            apt_install_retry 3 "$pkg" >/dev/null 2>&1 || log_warn "  Failed: $pkg"
        done
    }

    # AmneziaWG (DPI-resistant) — FREE-tier feature, install best-effort.
    # The DKMS build needs kernel headers, which may be missing on stripped
    # VPS images; if any of these fail the panel still works, just without
    # the AmneziaWG protocol. The user can add the PPA + install manually
    # later if needed.
    log_info "Installing AmneziaWG (FREE-tier DPI-resistant protocol)..."
    apt_install_retry 3 software-properties-common >/dev/null 2>&1 || true
    if add-apt-repository -y ppa:amnezia/ppa >/dev/null 2>&1 && apt_update_retry >/dev/null 2>&1; then
        # Linux headers are needed by the DKMS module; without them awg-tools
        # still installs but the kernel module won't compile, and `awg` calls
        # at runtime will fail. Try to grab the running-kernel headers first.
        apt_install_retry 3 "linux-headers-$(uname -r)" >/dev/null 2>&1 || \
            apt_install_retry 3 linux-headers-generic >/dev/null 2>&1 || \
            log_warn "  Linux headers not available — DKMS compile will likely fail"
        if apt_install_retry 3 amneziawg amneziawg-tools amneziawg-dkms >/dev/null 2>&1; then
            log_success "  AmneziaWG installed"
        else
            log_warn "  AmneziaWG install failed — WireGuard-only on this host"
            log_warn "  To enable later: apt install amneziawg amneziawg-tools amneziawg-dkms"
        fi
    else
        log_warn "  Could not add amnezia PPA — WireGuard-only on this host"
    fi

    # Ensure we can actually create a virtual environment. Some bare Ubuntu
    # images temporarily expose mismatched python3/python3-venv meta-packages,
    # so capability matters more than the exact package name being installed.
    if ! can_create_virtualenv; then
        log_warn "python3 -m venv not ready, attempting apt repair..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y -f -qq 2>/dev/null || true
        apt_install_retry 5 python3-venv python3.12-venv >/dev/null 2>&1 || true
    fi
    if ! can_create_virtualenv; then
        log_warn "python3 -m venv still unavailable, installing virtualenv fallback..."
        apt_install_retry 5 virtualenv >/dev/null 2>&1 || true
        python3 -m pip install -q virtualenv 2>/dev/null || true
    fi
    if ! can_create_virtualenv && ! python3 -m virtualenv --version >/dev/null 2>&1; then
        die "Cannot create a Python virtual environment. Run: apt-get update && apt-get install -y python3-venv or python3 -m pip install virtualenv"
    fi
    if ! dpkg -s python3-pip >/dev/null 2>&1; then
        log_warn "python3-pip not installed, retrying..."
        apt_install_retry 5 python3-pip >/dev/null 2>&1 || true
    fi
    if ! dpkg -s python3-pip >/dev/null 2>&1; then
        die "python3-pip missing. Run: apt-get update && apt-get install -y python3-pip"
    fi

    # Enable IP forwarding (required for WireGuard routing)
    if ! sysctl -n net.ipv4.ip_forward 2>/dev/null | grep -q 1; then
        sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
        if ! grep -q "^net.ipv4.ip_forward" /etc/sysctl.conf 2>/dev/null; then
            echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
        else
            sed -i 's/^net.ipv4.ip_forward.*/net.ipv4.ip_forward=1/' /etc/sysctl.conf
        fi
        log_info "  IP forwarding enabled"
    fi

    # Enable IPv6 forwarding
    if ! sysctl -n net.ipv6.conf.all.forwarding 2>/dev/null | grep -q 1; then
        sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null 2>&1 || true
        if ! grep -q "^net.ipv6.conf.all.forwarding" /etc/sysctl.conf 2>/dev/null; then
            echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
        fi
        log_info "  IPv6 forwarding enabled"
    fi

    # Verify critical packages
    command -v python3 >/dev/null || die "python3 not installed"
    command -v psql >/dev/null || die "postgresql not installed"

    local python_version
    python_version=$(python3 --version 2>&1 | awk '{print $2}')
    log_success "System deps installed (Python $python_version)"
}

# ============================================================================
# 4. SETUP POSTGRESQL
# ============================================================================
setup_postgresql() {
    log_step_done
    log_step 2 "Setting up PostgreSQL..."

    # Generate DB password if not provided
    if [[ -z "$DB_PASS" ]]; then
        DB_PASS=$(generate_password)
        log_info "  Generated database password"
    fi

    # Ensure PostgreSQL is running
    systemctl enable postgresql >/dev/null 2>&1 || true
    systemctl start postgresql 2>/dev/null || {
        local pg_service
        pg_service=$(systemctl list-unit-files | grep "^postgresql" | head -1 | awk '{print $1}')
        if [[ -n "$pg_service" ]]; then
            systemctl start "$pg_service" || die "Cannot start PostgreSQL"
        else
            die "PostgreSQL service not found"
        fi
    }

    # Wait for PostgreSQL to be ready
    local retries=10
    while ! sudo -u postgres pg_isready -q 2>/dev/null; do
        retries=$((retries - 1))
        [[ $retries -le 0 ]] && die "PostgreSQL not ready after waiting"
        sleep 1
    done

    # Create user (use environment variable to avoid SQL injection via password)
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
        sudo -u postgres psql -v ON_ERROR_STOP=1 -v db_user="$DB_USER" -v db_pass="$DB_PASS" >/dev/null 2>&1 <<'SQL'
SELECT format('CREATE USER %I WITH PASSWORD %L', :'db_user', :'db_pass') \gexec
SQL
        log_info "  Created PostgreSQL user: $DB_USER"
    else
        sudo -u postgres psql -v ON_ERROR_STOP=1 -v db_user="$DB_USER" -v db_pass="$DB_PASS" >/dev/null 2>&1 <<'SQL'
SELECT format('ALTER USER %I WITH PASSWORD %L', :'db_user', :'db_pass') \gexec
SQL
        log_info "  PostgreSQL user exists: $DB_USER (password updated)"
    fi

    # Create database
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
        sudo -u postgres createdb "$DB_NAME" -O "$DB_USER" 2>/dev/null
        log_info "  Created database: $DB_NAME"
    else
        log_info "  Database exists: $DB_NAME"
    fi

    # Fix pg_hba.conf for password auth
    local pg_hba
    pg_hba=$(find /etc/postgresql -name pg_hba.conf 2>/dev/null | head -1)

    if [[ -n "$pg_hba" ]]; then
        if ! grep -q "$DB_USER" "$pg_hba" 2>/dev/null; then
            # Append entries instead of rewriting the entire file
            {
                echo ""
                echo "# Flirexa database access"
                echo "local   $DB_NAME    $DB_USER                                md5"
                echo "host    $DB_NAME    $DB_USER    127.0.0.1/32            md5"
                echo "host    $DB_NAME    $DB_USER    ::1/128                 md5"
            } >> "$pg_hba"

            systemctl reload postgresql 2>/dev/null || systemctl restart postgresql
            log_info "  Updated pg_hba.conf for password auth"
        fi
    fi

    # Verify connection
    if PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
        log_success "PostgreSQL ready (user=$DB_USER, db=$DB_NAME)"
    else
        log_warn "Cannot verify DB connection via password. Trying peer auth..."
        if sudo -u postgres psql -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
            log_success "PostgreSQL ready via peer auth"
        else
            die "Cannot connect to PostgreSQL"
        fi
    fi
}

# ============================================================================
# 5. COPY APPLICATION FILES
# ============================================================================
copy_files() {
    log_step_done
    log_step 3 "Installing application files..."

    mkdir -p "$INSTALL_DIR"

    # If source and target are same, skip copy
    if [[ "$(realpath "$SCRIPT_DIR")" == "$(realpath "$INSTALL_DIR")" ]]; then
        log_info "  Source and target are the same directory, skipping copy"
        return
    fi

    # Vite gives changed bundles new hashed filenames. A merge-only in-place
    # copy leaves the previous JavaScript reachable on disk indefinitely even
    # though index.html no longer references it. Prune only these two
    # package-owned build outputs (never runtime data) before copying the
    # verified replacements from the release archive.
    local frontend_output
    for frontend_output in src/web/static/dist src/web/client-portal-dist; do
        if [[ -d "$SCRIPT_DIR/$frontend_output" ]]; then
            rm -rf "$INSTALL_DIR/$frontend_output"
        fi
    done

    rsync -a \
        --exclude='.git' \
        --exclude='.env' \
        --exclude='venv/' \
        --exclude='node_modules/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache/' \
        --exclude='*.egg-info/' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/" 2>/dev/null || {
        log_info "  rsync not available, using cp..."
        cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
        cp "$SCRIPT_DIR"/.env.example "$INSTALL_DIR/" 2>/dev/null || true
        rm -rf "$INSTALL_DIR/.git" "$INSTALL_DIR/venv" "$INSTALL_DIR/node_modules" 2>/dev/null || true
    }

    log_success "Files installed to $INSTALL_DIR"
}

# ============================================================================
# 5.5 PREPARE RUNTIME LAYOUT
# ============================================================================
prepare_runtime_layout() {
    log_info "Preparing runtime layout..."

    mkdir -p "$INSTALL_DIR/releases"
    mkdir -p "$INSTALL_DIR/shared"
    mkdir -p "$INSTALL_DIR/staging"
    mkdir -p "$INSTALL_DIR/update-lock"

    # Compatibility mode for existing installs:
    # keep running directly from INSTALL_DIR until release/current rollout is enabled.
    local current_link="$INSTALL_DIR/current"
    if [[ -L "$current_link" ]]; then
        log_info "  current symlink already exists"
    elif [[ -e "$current_link" ]]; then
        log_warn "  $current_link exists and is not a symlink — leaving as-is"
    else
        ln -s "$INSTALL_DIR" "$current_link"
        log_info "  Created compatibility current -> $INSTALL_DIR"
    fi

    log_success "Runtime layout ready"
}

reset_runtime_state_for_fresh_install() {
    if [[ "$EXISTING_INSTALL" == "true" ]]; then
        return 0
    fi

    # Defense in depth for a package assembled from a dirty working tree.
    # These files describe one prior installation.  In particular,
    # migration_initiated.json can deliberately decommission its original
    # server, so it must never affect a newly installed customer panel.
    local runtime_state_file
    for runtime_state_file in \
        first_startup_at.txt \
        license_cache.json \
        license_suspend_state.json \
        migration_initiated.json \
        license_migration_nonces.json \
        applied_migration.json \
        pending_migration.json \
        hb_servers.json \
        restart_pending; do
        rm -f "$INSTALL_DIR/data/$runtime_state_file"
    done
    log_info "  Cleared packaged runtime license state for fresh install"
}

# ============================================================================
# 6. PYTHON VIRTUAL ENVIRONMENT
# ============================================================================
setup_python() {
    log_step_done
    log_step 4 "Setting up Python environment..."

    if [[ ! -d "$INSTALL_DIR/venv" ]]; then
        if python3 -m venv "$INSTALL_DIR/venv" >/dev/null 2>&1; then
            :
        elif python3 -m virtualenv "$INSTALL_DIR/venv" >/dev/null 2>&1; then
            log_warn "  Created virtual environment via virtualenv fallback"
        else
            die "Failed to create virtual environment"
        fi
        log_info "  Created virtual environment"
    fi

    # Install requirements. Stream the full output to a log file — the
    # previous `2>&1 | tail -5` swallowed the root cause (a wheel build
    # error usually has its real `Error: …` line ~30 above the tail).
    log_info "  Installing Python packages (this may take a minute)..."
    local pip_log=/tmp/vpnmanager-pip-install.log
    local pip_bin="$INSTALL_DIR/venv/bin/pip"
    local runtime_bootstrap_lock="$INSTALL_DIR/requirements-runtime-bootstrap.lock"
    local requirements_file="$INSTALL_DIR/requirements.lock"
    : > "$pip_log"

    pip_install_retry() {
        local description="$1"
        shift
        local attempt
        for attempt in 1 2; do
            if "$pip_bin" --disable-pip-version-check --timeout 60 --retries 5 \
                install "$@" >> "$pip_log" 2>&1; then
                return 0
            fi
            log_warn "  ${description} failed (attempt ${attempt}/2)."
            (( attempt < 2 )) && sleep 3
        done
        return 1
    }

    # Python 3.12 venvs no longer reliably contain setuptools. Seed a small,
    # hash-locked build backend before the main transaction so the
    # --no-build-isolation recovery path can actually build an sdist after a
    # transient network or PEP 517 failure.
    if [[ ! -f "$runtime_bootstrap_lock" ]]; then
        die "Runtime Python bootstrap lock is missing: $runtime_bootstrap_lock"
    fi
    if ! pip_install_retry "Runtime build-tool bootstrap" \
        -r "$runtime_bootstrap_lock"; then
        log_error "Runtime Python bootstrap failed. Last 40 lines:"
        tail -40 "$pip_log" 2>&1 | sed 's/^/  /' || true
        log_info "Full log preserved at: $pip_log"
        die "Failed to install locked Python build tools"
    fi

    if [[ ! -f "$requirements_file" ]]; then
        requirements_file="$INSTALL_DIR/requirements.txt"
        log_warn "  Dependency lock not found; using compatibility requirements"
    fi
    if ! pip_install_retry "Locked Python dependency installation" \
        -r "$requirements_file"; then
        log_warn "  First pip pass failed, retrying with --no-build-isolation..."
        if ! pip_install_retry "Non-isolated Python dependency installation" \
            -r "$requirements_file" --no-build-isolation; then
            log_error "Pip install failed. Last 40 lines:"
            tail -40 "$pip_log" 2>&1 | sed 's/^/  /' || true
            log_info "Full log preserved at: $pip_log"
            die "Failed to install Python requirements"
        fi
    fi

    # Verify critical imports
    local missing=()
    "$INSTALL_DIR/venv/bin/python" -c "import fastapi" 2>/dev/null || missing+=("fastapi")
    "$INSTALL_DIR/venv/bin/python" -c "import sqlalchemy" 2>/dev/null || missing+=("sqlalchemy")
    "$INSTALL_DIR/venv/bin/python" -c "import telegram" 2>/dev/null || missing+=("python-telegram-bot")
    "$INSTALL_DIR/venv/bin/python" -c "import uvicorn" 2>/dev/null || missing+=("uvicorn")
    "$INSTALL_DIR/venv/bin/python" -c "import psycopg2" 2>/dev/null || missing+=("psycopg2-binary")
    "$INSTALL_DIR/venv/bin/python" -c "import dotenv" 2>/dev/null || missing+=("python-dotenv")
    "$INSTALL_DIR/venv/bin/python" -c "import psutil" 2>/dev/null || missing+=("psutil")
    "$INSTALL_DIR/venv/bin/python" -c "import bcrypt" 2>/dev/null || missing+=("bcrypt")
    "$INSTALL_DIR/venv/bin/python" -c "import jwt" 2>/dev/null || missing+=("PyJWT")

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing critical packages: ${missing[*]}"
        log_info "Attempting individual install..."
        for pkg in "${missing[@]}"; do
            "$INSTALL_DIR/venv/bin/pip" install "$pkg" 2>&1 | tail -1
        done
    fi

    local py_ver
    py_ver=$("$INSTALL_DIR/venv/bin/python" --version 2>&1)
    log_success "Python environment ready ($py_ver)"
}

# ============================================================================
# 7. CONFIGURE .env
# ============================================================================

# Validate a Telegram bot token against the API
validate_telegram_token() {
    local token="$1"
    local label="$2"
    local response
    response=$(curl -s --max-time 10 "https://api.telegram.org/bot${token}/getMe" 2>/dev/null)

    if echo "$response" | grep -q '"ok":true'; then
        local bot_name
        bot_name=$(echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result'].get('username',''))" 2>/dev/null || echo "")
        log_success "  $label token valid: @$bot_name"
        return 0
    else
        log_warn "  $label token rejected by Telegram API"
        return 1
    fi
}

# Contacts license server with activation_code, prints license_key to stdout on success.
configure_license_activation() {
    # NOTE: all log_* output goes to stderr so that callers can capture
    # the license key from stdout without mixing in log messages.
    local activation_code="$1"
    log_info "  Computing machine fingerprint…" >&2
    local hw_id
    hw_id=$(python3 -c "
import platform, hashlib, uuid
components = [platform.node(), platform.machine(), str(uuid.getnode())]
try:
    with open('/etc/machine-id') as f:
        components.append(f.read().strip())
except Exception:
    pass
print(hashlib.sha256('|'.join(components).encode()).hexdigest()[:32])
" 2>/dev/null) || hw_id=""

    if [[ -z "$hw_id" ]]; then
        log_warn "  Could not compute machine fingerprint. Skipping activation." >&2
        return 1
    fi

    log_info "  Contacting license server…" >&2
    local activate_resp
    activate_resp=$(curl -sf --max-time 30 \
        -X POST "${LICENSE_SERVER_URL}/api/activate" \
        -H "Content-Type: application/json" \
        -d "{\"activation_code\":\"${activation_code}\",\"hardware_id\":\"${hw_id}\",\"client_version\":\"${APP_VERSION}\"}" \
        2>/dev/null) || activate_resp=""

    if [[ -z "$activate_resp" ]]; then
        log_warn "  Could not reach license server. Activate later via the admin panel." >&2
        return 1
    fi

    local license_key
    license_key=$(python3 -c "
import sys, json
try:
    d = json.loads(sys.argv[1])
    print(d.get('license_key',''))
except Exception:
    pass
" "$activate_resp" 2>/dev/null) || license_key=""

    if [[ -n "$license_key" ]]; then
        log_success "  Product activated successfully!" >&2
        echo "$license_key"   # ← only the key goes to stdout
        return 0
    else
        local err_detail
        err_detail=$(python3 -c "
import sys, json
try:
    d = json.loads(sys.argv[1])
    print(d.get('detail', 'Unknown error'))
except Exception:
    print('Could not parse server response')
" "$activate_resp" 2>/dev/null) || err_detail="Unknown error"
        log_warn "  Activation failed: ${err_detail}" >&2
        log_info "  You can activate later via the admin panel." >&2
        return 1
    fi
}

configure_env() {
    log_step_done
    log_step 5 "Configuring environment..."

    # If .env already exists (upgrade), preserve it completely
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        log_info "  .env already exists, preserving existing configuration"

        # Ensure SECRET_KEY is set (might be missing from older installs)
        if ! grep -q "^SECRET_KEY=" "$INSTALL_DIR/.env" || grep -q "change-this" "$INSTALL_DIR/.env"; then
            local secret_key
            secret_key=$(generate_secret)
            if grep -q "^SECRET_KEY=" "$INSTALL_DIR/.env"; then
                sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(sed_escape_replacement "$secret_key")|" "$INSTALL_DIR/.env"
            else
                echo "SECRET_KEY=$secret_key" >> "$INSTALL_DIR/.env"
            fi
            log_info "  Generated new SECRET_KEY"
        fi

        # Ensure JWT_SECRET is set
        if ! grep -q "^JWT_SECRET=" "$INSTALL_DIR/.env" || grep -q "change-this" "$INSTALL_DIR/.env"; then
            local jwt_secret
            jwt_secret=$(generate_secret)
            if grep -q "^JWT_SECRET=" "$INSTALL_DIR/.env"; then
                sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(sed_escape_replacement "$jwt_secret")|" "$INSTALL_DIR/.env"
            else
                echo "JWT_SECRET=$jwt_secret" >> "$INSTALL_DIR/.env"
            fi
            log_info "  Generated new JWT_SECRET"
        fi

        # Pin LICENSE_SERVER_URL and UPDATE_SERVER_URL in .env so the runtime
        # never falls through to the placeholder default. Both default to
        # https://flirexa.biz; self-hosters set SB_LICENSE_SERVER_URL /
        # SB_UPDATE_SERVER_URL before running install.sh to override.
        for _kv in "LICENSE_SERVER_URL=$LICENSE_SERVER_URL" "UPDATE_SERVER_URL=$UPDATE_SERVER_URL"; do
            local _k="${_kv%%=*}"
            if grep -q "^${_k}=" "$INSTALL_DIR/.env" 2>/dev/null; then
                sed -i "s|^${_k}=.*|${_kv}|" "$INSTALL_DIR/.env"
            else
                echo "$_kv" >> "$INSTALL_DIR/.env"
            fi
        done

        # Ensure VMS_ENCRYPTION_KEY is set (critical for backup/restore — must not change between servers)
        local _cur_enc_key
        _cur_enc_key=$(grep "^VMS_ENCRYPTION_KEY=" "$INSTALL_DIR/.env" | cut -d= -f2- | tr -d '[:space:]') || _cur_enc_key=""
        if [[ -z "$_cur_enc_key" ]]; then
            local enc_key
            enc_key=$(generate_secret)
            if grep -q "^VMS_ENCRYPTION_KEY=" "$INSTALL_DIR/.env"; then
                sed -i "s|^VMS_ENCRYPTION_KEY=.*|VMS_ENCRYPTION_KEY=$(sed_escape_replacement "$enc_key")|" "$INSTALL_DIR/.env"
            else
                echo "VMS_ENCRYPTION_KEY=$enc_key" >> "$INSTALL_DIR/.env"
            fi
            log_info "  Generated new VMS_ENCRYPTION_KEY (back up this key — required to decrypt WireGuard keys after server migration)"
        fi

        # If activation code provided and license key is missing — activate now
        local _ac="${SB_ACTIVATION_CODE:-}"
        local _lk
        _lk=$(grep "^LICENSE_KEY=" "$INSTALL_DIR/.env" | cut -d= -f2-)
        if [[ -n "$_ac" && -z "$_lk" ]]; then
            local _new_key
            _new_key=$(configure_license_activation "$_ac") || _new_key=""
            if [[ -n "$_new_key" ]]; then
                python3 - "$INSTALL_DIR/.env" "$_new_key" <<'PYEOF'
import sys, re
env_file, key_val = sys.argv[1], sys.argv[2]
with open(env_file) as f:
    content = f.read()
content = re.sub(r'^LICENSE_KEY=.*$', 'LICENSE_KEY=' + key_val, content, flags=re.MULTILINE)
with open(env_file, 'w') as f:
    f.write(content)
PYEOF
                sed -i "s|^LICENSE_CHECK_ENABLED=.*|LICENSE_CHECK_ENABLED=true|" "$INSTALL_DIR/.env"
                # Save activation code for display in admin panel (masked)
                python3 - "$INSTALL_DIR/.env" "$_ac" <<'PYEOF'
import sys
env_file, ac = sys.argv[1], sys.argv[2]
with open(env_file) as f:
    content = f.read()
if 'ACTIVATION_CODE=' not in content:
    content += f'\nACTIVATION_CODE={ac}\n'
with open(env_file, 'w') as f:
    f.write(content)
PYEOF
            fi
        fi

        return
    fi

    # --- Fresh install ---
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"

    # Generate unique secrets
    local secret_key jwt_secret service_token agent_key enc_key
    secret_key=$(generate_secret)
    jwt_secret=$(generate_secret)
    service_token=$(generate_secret)
    agent_key=$(generate_secret)
    enc_key=$(generate_secret)
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(sed_escape_replacement "$secret_key")|" "$INSTALL_DIR/.env"
    sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(sed_escape_replacement "$jwt_secret")|" "$INSTALL_DIR/.env"
    sed -i "s|^SERVICE_API_TOKEN=.*|SERVICE_API_TOKEN=$(sed_escape_replacement "$service_token")|" "$INSTALL_DIR/.env"
    sed -i "s|^AGENT_API_KEY=.*|AGENT_API_KEY=$(sed_escape_replacement "$agent_key")|" "$INSTALL_DIR/.env"
    sed -i "s|^VMS_ENCRYPTION_KEY=.*|VMS_ENCRYPTION_KEY=$(sed_escape_replacement "$enc_key")|" "$INSTALL_DIR/.env"

    # Set database URL
    local db_url
    db_url="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$(sed_escape_replacement "$db_url")|" "$INSTALL_DIR/.env"

    # Pin LICENSE_SERVER_URL + UPDATE_SERVER_URL (default flirexa.biz; override
    # via SB_LICENSE_SERVER_URL / SB_UPDATE_SERVER_URL env on the install
    # invocation if running a private license server).
    for _kv in "LICENSE_SERVER_URL=$LICENSE_SERVER_URL" "UPDATE_SERVER_URL=$UPDATE_SERVER_URL"; do
        local _k="${_kv%%=*}"
        if grep -q "^${_k}=" "$INSTALL_DIR/.env" 2>/dev/null; then
            sed -i "s|^${_k}=.*|${_kv}|" "$INSTALL_DIR/.env"
        else
            echo "$_kv" >> "$INSTALL_DIR/.env"
        fi
    done

    # Detect server IP for endpoint
    local server_ip="" _raw
    # Try each source and take the first that returns a valid IPv4 address.
    for _raw in \
        "$(curl -s --max-time 5 https://ifconfig.me/ip 2>/dev/null)" \
        "$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null)" \
        "$(curl -s --max-time 5 https://checkip.amazonaws.com 2>/dev/null)" \
        "$(hostname -I 2>/dev/null | awk '{print $1}')"; do
        server_ip=$(echo "$_raw" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -1) || true
        [[ -n "$server_ip" ]] && break
    done
    [[ -n "$server_ip" ]] || server_ip="YOUR_SERVER_IP"
    sed -i "s|^SERVER_ENDPOINT=.*|SERVER_ENDPOINT=$(sed_escape_replacement "$server_ip:51820")|" "$INSTALL_DIR/.env"

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        # ── Non-interactive mode ──
        local admin_token="${SB_ADMIN_TOKEN:-}"
        local admin_users="${SB_ADMIN_USERS:-}"
        local client_token="${SB_CLIENT_TOKEN:-}"
        local endpoint="${SB_ENDPOINT:-$server_ip:51820}"

        if [[ -n "$admin_token" ]]; then
            if validate_telegram_token "$admin_token" "Admin bot"; then
                sed -i "s|^ADMIN_BOT_TOKEN=.*|ADMIN_BOT_TOKEN=$(sed_escape_replacement "$admin_token")|" "$INSTALL_DIR/.env"
            else
                log_warn "  Admin bot token invalid. Configure later via web panel."
            fi
        fi

        [[ -n "$admin_users" ]] && sed -i "s|^ADMIN_BOT_ALLOWED_USERS=.*|ADMIN_BOT_ALLOWED_USERS=$(sed_escape_replacement "$admin_users")|" "$INSTALL_DIR/.env"

        if [[ -n "$client_token" ]]; then
            if validate_telegram_token "$client_token" "Client bot"; then
                sed -i "s|^CLIENT_BOT_TOKEN=.*|CLIENT_BOT_TOKEN=$(sed_escape_replacement "$client_token")|" "$INSTALL_DIR/.env"
                sed -i "s|^CLIENT_BOT_ENABLED=.*|CLIENT_BOT_ENABLED=true|" "$INSTALL_DIR/.env"
            else
                log_warn "  Client bot token invalid. Leaving disabled."
            fi
        fi

        sed -i "s|^SERVER_ENDPOINT=.*|SERVER_ENDPOINT=$(sed_escape_replacement "$endpoint")|" "$INSTALL_DIR/.env"

    else
        # ── Interactive mode ──
        echo ""
        echo -e "${BOLD}Telegram Bot Configuration${NC}"
        echo ""
        echo "  Create your bots via @BotFather in Telegram."
        echo "  Get your user ID via @userinfobot."
        echo "  You can skip now and configure later via the web panel (/bots page)."
        echo ""

        # Admin bot token (optional)
        local admin_token=""
        read -r -p "  Admin Bot Token (Enter to skip): " admin_token || admin_token=""

        if [[ -n "$admin_token" ]]; then
            if [[ ! "$admin_token" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
                log_warn "  Invalid format. Skipping."
                admin_token=""
            else
                if ! validate_telegram_token "$admin_token" "Admin bot"; then
                    read -r -p "  Token rejected. Save anyway? (y/n): " reply || reply=""
                    if [[ ! "$reply" =~ ^[Yy]$ ]]; then
                        admin_token=""
                    fi
                fi
            fi
        fi

        # Admin user IDs
        local admin_users=""
        if [[ -n "$admin_token" ]]; then
            while true; do
                read -r -p "  Admin User ID(s) (comma-separated): " admin_users || admin_users=""
                if [[ -z "$admin_users" ]]; then
                    log_warn "  No admin IDs. Bot won't accept commands. Configure later via /bots."
                    break
                elif [[ "$admin_users" =~ ^[0-9,\ ]+$ ]]; then
                    admin_users=$(echo "$admin_users" | tr -d ' ')
                    break
                else
                    log_warn "  Numbers only, comma-separated: 123456789,987654321"
                fi
            done
        fi

        # Client bot token (optional)
        local client_token=""
        local client_enabled="false"
        echo ""
        read -r -p "  Client Bot Token (Enter to skip): " client_token || client_token=""

        if [[ -n "$client_token" ]]; then
            if [[ ! "$client_token" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
                log_warn "  Invalid format. Skipping."
                client_token=""
            else
                if validate_telegram_token "$client_token" "Client bot"; then
                    client_enabled="true"
                else
                    read -r -p "  Token rejected. Save anyway? (y/n): " reply || reply=""
                    if [[ "$reply" =~ ^[Yy]$ ]]; then
                        client_enabled="true"
                    else
                        client_token=""
                    fi
                fi
            fi
        fi

        # Server endpoint
        echo ""
        read -r -p "  WireGuard endpoint [$server_ip:51820]: " endpoint || endpoint=""
        endpoint="${endpoint:-$server_ip:51820}"

        # Write values to .env
        [[ -n "$admin_token" ]] && sed -i "s|^ADMIN_BOT_TOKEN=.*|ADMIN_BOT_TOKEN=$(sed_escape_replacement "$admin_token")|" "$INSTALL_DIR/.env"
        [[ -n "$admin_users" ]] && sed -i "s|^ADMIN_BOT_ALLOWED_USERS=.*|ADMIN_BOT_ALLOWED_USERS=$(sed_escape_replacement "$admin_users")|" "$INSTALL_DIR/.env"
        [[ -n "$client_token" ]] && sed -i "s|^CLIENT_BOT_TOKEN=.*|CLIENT_BOT_TOKEN=$(sed_escape_replacement "$client_token")|" "$INSTALL_DIR/.env"
        sed -i "s|^CLIENT_BOT_ENABLED=.*|CLIENT_BOT_ENABLED=$client_enabled|" "$INSTALL_DIR/.env"
        sed -i "s|^SERVER_ENDPOINT=.*|SERVER_ENDPOINT=$(sed_escape_replacement "$endpoint")|" "$INSTALL_DIR/.env"

        if [[ -z "$admin_token" ]]; then
            echo ""
            log_info "  No bot tokens configured. Set them later:"
            log_info "    - Web panel: http://$server_ip:10086 -> Bots page"
            log_info "    - Or edit $INSTALL_DIR/.env manually"
        fi
    fi

    # ── License Activation ────────────────────────────────────────────────────
    # Always prompt for an activation code when interactive (incl. via curl|bash,
    # by reading from /dev/tty). Empty / N / no / skip → FREE tier. Non-interactive
    # mode stays unprompted; SB_ACTIVATION_CODE / SB_LICENSE_KEY env vars short-
    # circuit the prompt so CI/automation can pass a paid code without a TTY.
    local activation_code="${SB_ACTIVATION_CODE:-}"
    local license_key="${SB_LICENSE_KEY:-}"

    if [[ "$NON_INTERACTIVE" != "true" && -z "$activation_code" && -z "$license_key" ]]; then
        echo ""
        echo -e "${BOLD}License Activation${NC}"
        echo ""
        echo "  Have a paid Activation Code (XXXX-XXXX-XXXX-XXXX)? Paste it below."
        echo "  Press Enter (or type N) to install in FREE tier."
        echo ""
        # Read from /dev/tty so the prompt works even under `curl … | bash`,
        # where stdin is the script pipe and a plain `read` fails immediately.
        #
        # `-r /dev/tty` is true on every box (the devnode exists 666), but
        # actually open(2)'ing it fails with ENXIO when the process has no
        # controlling terminal — which is exactly the case under
        # `curl … | sudo bash` over SSH without a pty. Bash prints
        # "install.sh: line NNNN: /dev/tty: No such device or address" to
        # stderr in that case, which guests reasonably mistake for a fatal
        # error and abort the install (4 retry pattern we saw in the logs).
        # Probe with `exec 9<` so the failure is silent, and only prompt
        # if the fd actually opened.
        if exec 9</dev/tty 2>/dev/null; then
            read -r -p "  Activation Code (or N for FREE): " activation_code <&9 || activation_code=""
            exec 9<&- || true
        else
            log_info "  No TTY available — installing in FREE tier"
            activation_code=""
        fi
        # Treat explicit "no" inputs as FREE.
        case "${activation_code,,}" in
            ""|"n"|"no"|"free"|"skip") activation_code="" ;;
        esac
    fi

    if [[ -n "$activation_code" ]]; then
        license_key=$(configure_license_activation "$activation_code") || license_key=""
    fi

    if [[ -n "$license_key" ]]; then
        # Use Python to write LICENSE_KEY safely — the key may contain characters
        # (e.g. newlines, backslashes) that would break sed substitution.
        python3 - "$INSTALL_DIR/.env" "$license_key" <<'PYEOF'
import sys, re
env_file, key_val = sys.argv[1], sys.argv[2]
with open(env_file) as f:
    content = f.read()
content = re.sub(r'^LICENSE_KEY=.*$', 'LICENSE_KEY=' + key_val, content, flags=re.MULTILINE)
with open(env_file, 'w') as f:
    f.write(content)
PYEOF
        sed -i "s|^LICENSE_CHECK_ENABLED=.*|LICENSE_CHECK_ENABLED=true|" "$INSTALL_DIR/.env"
        # Save activation code for display in admin panel (if activated via code)
        if [[ -n "$activation_code" ]]; then
            python3 - "$INSTALL_DIR/.env" "$activation_code" <<'PYEOF'
import sys
env_file, ac = sys.argv[1], sys.argv[2]
with open(env_file) as f:
    content = f.read()
if 'ACTIVATION_CODE=' not in content:
    content += f'\nACTIVATION_CODE={ac}\n'
with open(env_file, 'w') as f:
    f.write(content)
PYEOF
        fi
        log_info "  License key saved"
    else
        sed -i "s|^LICENSE_CHECK_ENABLED=.*|LICENSE_CHECK_ENABLED=true|" "$INSTALL_DIR/.env"
        log_info "  Running on FREE tier (no activation needed)"
    fi

    update_env_value() {
        local key="$1"
        local value="$2"
        if grep -q "^${key}=" "$INSTALL_DIR/.env" 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=$(sed_escape_replacement "$value")|" "$INSTALL_DIR/.env"
        else
            echo "${key}=${value}" >> "$INSTALL_DIR/.env"
        fi
    }

    update_env_value "WEB_SETUP_MODE" "$WEB_SETUP_MODE"
    update_env_value "CLIENT_PORTAL_DOMAIN" "$WEB_PORTAL_DOMAIN"
    update_env_value "ADMIN_PANEL_DOMAIN" "$WEB_ADMIN_DOMAIN"
    update_env_value "ADMIN_ACCESS_MODE" "raw_ports"
    update_env_value "CERTBOT_EMAIL" "$WEB_CERTBOT_EMAIL"

    chmod 600 "$INSTALL_DIR/.env"
    log_success "Environment configured"
}

configure_web_access_preferences() {
    log_info "Configuring web access mode..."

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        if [[ "$WEB_SETUP_MODE" == "portal_admin_domain" ]] && [[ -z "$WEB_PORTAL_DOMAIN" || -z "$WEB_ADMIN_DOMAIN" || -z "$WEB_CERTBOT_EMAIL" ]]; then
            die "SB_WEB_SETUP_MODE=portal_admin_domain requires SB_CLIENT_PORTAL_DOMAIN, SB_ADMIN_PANEL_DOMAIN, SB_CERTBOT_EMAIL"
        fi
        if [[ "$WEB_SETUP_MODE" == "portal_admin_ip" ]] && [[ -z "$WEB_PORTAL_DOMAIN" || -z "$WEB_CERTBOT_EMAIL" ]]; then
            die "SB_WEB_SETUP_MODE=portal_admin_ip requires SB_CLIENT_PORTAL_DOMAIN and SB_CERTBOT_EMAIL"
        fi
        # `auto_selfsigned_ip` needs nothing — falls through.
    elif [[ ! -t 0 ]]; then
        # Piped installer (curl … | bash) has no controlling tty, so the
        # read prompts below would silently default to "n" and the operator
        # would end up with services running but no nginx in front, making
        # the panel appear unavailable on its expected HTTPS URL. Default
        # to `auto_selfsigned_ip`:
        # nginx + self-signed cert bound to the public IP, so the panel
        # works the moment the install finishes. Operators with a real
        # domain can re-run scripts/configure-web-access.sh later.
        log_info "Non-interactive install detected (no tty) — defaulting web access to auto_selfsigned_ip"
        WEB_SETUP_MODE="auto_selfsigned_ip"
        WEB_PORTAL_DOMAIN=""
        WEB_ADMIN_DOMAIN=""
        WEB_CERTBOT_EMAIL=""
    else
        echo ""
        echo -e "${BOLD}Web Access / HTTPS${NC}"
        echo ""
        echo "  Recommended production setup:"
        echo "    - Client portal on its own domain with Let's Encrypt"
        echo "    - Admin panel either on a separate domain or via server IP + self-signed TLS"
        echo "    - Or: no domain yet — quick self-signed TLS on this server's IP"
        echo ""
        read -r -p "  Configure nginx + HTTPS now? (y/n) [n]: " web_reply || web_reply=""
        if [[ "$web_reply" =~ ^[Yy]$ ]]; then
            while true; do
                echo ""
                echo "  1) Client portal domain + admin by server IP (self-signed TLS for admin)"
                echo "  2) Client portal domain + admin domain (Let's Encrypt for both)"
                echo "  3) No domain yet — self-signed TLS on this server's IP for both"
                read -r -p "  Choose web mode [1-3]: " web_mode_choice || web_mode_choice=""
                case "$web_mode_choice" in
                    1) WEB_SETUP_MODE="portal_admin_ip"; break ;;
                    2) WEB_SETUP_MODE="portal_admin_domain"; break ;;
                    3) WEB_SETUP_MODE="auto_selfsigned_ip"; break ;;
                    *) log_warn "  Choose 1, 2 or 3" ;;
                esac
            done

            if [[ "$WEB_SETUP_MODE" != "auto_selfsigned_ip" ]]; then
                while [[ -z "$WEB_PORTAL_DOMAIN" ]]; do
                    read -r -p "  Client portal domain: " WEB_PORTAL_DOMAIN || WEB_PORTAL_DOMAIN=""
                    [[ -n "$WEB_PORTAL_DOMAIN" ]] || log_warn "  Client portal domain is required"
                done

                if [[ "$WEB_SETUP_MODE" == "portal_admin_domain" ]]; then
                    while [[ -z "$WEB_ADMIN_DOMAIN" ]]; do
                        read -r -p "  Admin panel domain: " WEB_ADMIN_DOMAIN || WEB_ADMIN_DOMAIN=""
                        [[ -n "$WEB_ADMIN_DOMAIN" ]] || log_warn "  Admin panel domain is required"
                    done
                else
                    WEB_ADMIN_DOMAIN=""
                fi

                while [[ -z "$WEB_CERTBOT_EMAIL" ]]; do
                    read -r -p "  Email for Let's Encrypt notices: " WEB_CERTBOT_EMAIL || WEB_CERTBOT_EMAIL=""
                    [[ -n "$WEB_CERTBOT_EMAIL" ]] || log_warn "  Email is required for certificate issuance"
                done
            else
                # auto_selfsigned_ip needs no extra input — IP is discovered
                # at apply time, cert is generated then.
                WEB_PORTAL_DOMAIN=""
                WEB_ADMIN_DOMAIN=""
                WEB_CERTBOT_EMAIL=""
            fi
        else
            WEB_SETUP_MODE="none"
            WEB_PORTAL_DOMAIN=""
            WEB_ADMIN_DOMAIN=""
            WEB_CERTBOT_EMAIL=""
        fi
    fi

    if [[ -f "$INSTALL_DIR/.env" ]]; then
        sed -i "s|^WEB_SETUP_MODE=.*|WEB_SETUP_MODE=$(sed_escape_replacement "$WEB_SETUP_MODE")|" "$INSTALL_DIR/.env" 2>/dev/null || true
        sed -i "s|^CLIENT_PORTAL_DOMAIN=.*|CLIENT_PORTAL_DOMAIN=$(sed_escape_replacement "$WEB_PORTAL_DOMAIN")|" "$INSTALL_DIR/.env" 2>/dev/null || true
        sed -i "s|^ADMIN_PANEL_DOMAIN=.*|ADMIN_PANEL_DOMAIN=$(sed_escape_replacement "$WEB_ADMIN_DOMAIN")|" "$INSTALL_DIR/.env" 2>/dev/null || true
        sed -i "s|^CERTBOT_EMAIL=.*|CERTBOT_EMAIL=$(sed_escape_replacement "$WEB_CERTBOT_EMAIL")|" "$INSTALL_DIR/.env" 2>/dev/null || true
    fi
}

# ============================================================================
# 8. INITIALIZE DATABASE
# ============================================================================
init_database() {
    log_step_done
    log_step 6 "Initializing database..."

    cd "$INSTALL_DIR"
    "$INSTALL_DIR/venv/bin/python" main.py init-db 2>&1 | tail -3 || {
        log_error "Database initialization failed"
        log_info "Checking PostgreSQL connection..."
        systemctl reload postgresql 2>/dev/null || true
        sleep 1
        "$INSTALL_DIR/venv/bin/python" main.py init-db 2>&1 | tail -3 || die "Database init failed after retry"
    }

    log_success "Database initialized"
}

# ============================================================================
# 9. INSTALL SYSTEMD SERVICES
# ============================================================================
install_cli_entrypoint() {
    local cli_source=""
    if [[ -L "$INSTALL_DIR/current" && -f "$INSTALL_DIR/current/vpnmanager" ]]; then
        cli_source="$INSTALL_DIR/current/vpnmanager"
    elif [[ -f "$INSTALL_DIR/vpnmanager" ]]; then
        cli_source="$INSTALL_DIR/vpnmanager"
    fi

    if [[ -n "$cli_source" ]]; then
        ln -sf "$cli_source" /usr/local/bin/vpnmanager
        chmod 755 "$cli_source" 2>/dev/null || true
        log_info "  Installed CLI: /usr/local/bin/vpnmanager -> $cli_source"
    else
        log_warn "  vpnmanager CLI source not found under $INSTALL_DIR"
    fi
}

install_systemd() {
    log_step_done
    log_step 7 "Installing systemd services..."

    # Core services from deploy/systemd/
    local services=("vpnmanager-api" "vpnmanager-admin-bot" "vpnmanager-client-bot" "vpnmanager-worker")

    for svc in "${services[@]}"; do
        local src="$INSTALL_DIR/deploy/systemd/${svc}.service"
        local dst="/etc/systemd/system/${svc}.service"

        if [[ -f "$src" ]]; then
            cp "$src" "$dst"
            sed -i "s|/opt/vpnmanager|$INSTALL_DIR|g" "$dst"
            log_info "  Installed: ${svc}.service"
        else
            log_warn "  Service file not found: $src"
        fi
    done

    # Client portal service (separate file location)
    local cp_src="$INSTALL_DIR/deploy/vpnmanager-client-portal.service"
    local cp_dst="/etc/systemd/system/vpnmanager-client-portal.service"
    if [[ -f "$cp_src" ]]; then
        cp "$cp_src" "$cp_dst"
        sed -i \
            -e "s|/opt/vpnmanager|$INSTALL_DIR|g" \
            "$cp_dst"
        log_info "  Installed: vpnmanager-client-portal.service"
    else
        log_warn "  Client portal service file not found: $cp_src"
    fi

    # Log directory
    mkdir -p /var/log/vpnmanager
    chmod 755 /var/log/vpnmanager
    log_info "  Log directory: /var/log/vpnmanager"

    # Logrotate config
    local lr_src="$INSTALL_DIR/deploy/logrotate/vpnmanager"
    if [[ -f "$lr_src" ]]; then
        cp "$lr_src" /etc/logrotate.d/vpnmanager
        log_info "  Logrotate config installed"
    fi

    systemctl daemon-reload

    # Enable services
    systemctl enable vpnmanager-api >/dev/null 2>&1 || true
    systemctl enable vpnmanager-client-portal >/dev/null 2>&1 || true
    systemctl enable vpnmanager-worker >/dev/null 2>&1 || true

    # Admin bot: only enable if configured
    if grep -q "^ADMIN_BOT_TOKEN=.\\+" "$INSTALL_DIR/.env" 2>/dev/null; then
        systemctl enable vpnmanager-admin-bot >/dev/null 2>&1 || true
    fi

    # Client bot: only enable if configured
    if grep -q "CLIENT_BOT_ENABLED=true" "$INSTALL_DIR/.env" 2>/dev/null; then
        systemctl enable vpnmanager-client-bot >/dev/null 2>&1 || true
    fi

    install_cli_entrypoint

    log_success "Systemd services installed"
}

# ============================================================================
# 10. FIREWALL
# ============================================================================
configure_firewall() {
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
        log_info "Configuring UFW firewall..."
        ufw allow 10086/tcp comment "Flirexa Admin Panel" >/dev/null 2>&1 || true
        ufw allow 10090/tcp comment "Flirexa Client Portal" >/dev/null 2>&1 || true
        ufw allow 51820/udp comment "WireGuard" >/dev/null 2>&1 || true
        log_success "Firewall rules added (10086/tcp, 10090/tcp, 51820/udp)"
    fi
}

# ============================================================================
# 11. START SERVICES
# ============================================================================
start_services() {
    log_step_done
    log_step 8 "Starting services..."

    # Start API. set -e at the top of this script means a silent failure here
    # aborts the whole install without any context — surface the real reason
    # (journalctl tail + systemctl status) so the operator can fix it on the
    # FIRST attempt instead of running the installer 3-4 times.
    if ! systemctl start vpnmanager-api 2>/tmp/vpnmanager-api-start.err; then
        log_error "Failed to start vpnmanager-api:"
        cat /tmp/vpnmanager-api-start.err 2>/dev/null || true
        log_error "── systemctl status (last 15 lines) ─────────────────"
        systemctl status vpnmanager-api --no-pager -n 15 2>&1 | sed 's/^/  /' || true
        log_error "── journalctl -u vpnmanager-api -n 30 ───────────────"
        journalctl -u vpnmanager-api --no-pager -n 30 2>&1 | sed 's/^/  /' || true
        log_error "─────────────────────────────────────────────────────"
        log_info "Common causes: port 10086 already in use, alembic migration"
        log_info "from a previous attempt left the DB in a mixed state, or one"
        log_info "of the pip-installed packages didn't import cleanly."
        die "vpnmanager-api failed to start (see diagnostics above)"
    fi
    sleep 3

    # Check API health
    local retries=5
    while ! curl -s -o /dev/null -w "%{http_code}" http://localhost:10086/health 2>/dev/null | grep -q "200"; do
        retries=$((retries - 1))
        if [[ $retries -le 0 ]]; then
            log_warn "API not responding yet (may need more time)"
            break
        fi
        sleep 2
    done

    # Start client portal
    systemctl start vpnmanager-client-portal 2>/dev/null || true
    log_info "  Client portal started"

    # Start worker when enabled
    if grep -q "WORKER_ENABLED=true" "$INSTALL_DIR/.env" 2>/dev/null; then
        systemctl start vpnmanager-worker 2>/dev/null || true
        log_info "  Worker started"
    else
        log_info "  Worker skipped (disabled in .env)"
    fi

    # Start admin bot only if token is configured
    local admin_token
    admin_token=$(grep "^ADMIN_BOT_TOKEN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    if [[ -n "$admin_token" ]]; then
        systemctl start vpnmanager-admin-bot 2>/dev/null || true
        log_info "  Admin bot started"
    else
        log_info "  Admin bot skipped (no token configured)"
    fi

    # Start client bot only if enabled AND token is configured
    local client_token
    client_token=$(grep "^CLIENT_BOT_TOKEN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    if grep -q "CLIENT_BOT_ENABLED=true" "$INSTALL_DIR/.env" 2>/dev/null && [[ -n "$client_token" ]]; then
        systemctl start vpnmanager-client-bot 2>/dev/null || true
        log_info "  Client bot started"
    else
        log_info "  Client bot skipped (not configured)"
    fi

    sleep 2
    log_success "Services started"
}

# ============================================================================
# 11.5. SETUP WIREGUARD INTERFACE
# ============================================================================
setup_wireguard() {
    log_info "Setting up WireGuard..."

    if ! command -v wg >/dev/null 2>&1; then
        log_warn "  WireGuard tools not installed, skipping"
        return
    fi

    local iface="wg0"
    local wg_conf="/etc/wireguard/${iface}.conf"

    # Skip if WireGuard already configured
    if [[ -f "$wg_conf" ]]; then
        log_info "  $wg_conf already exists, skipping generation"
        # Make sure interface is up
        if ! wg show "$iface" >/dev/null 2>&1; then
            wg-quick up "$iface" 2>/dev/null || log_warn "  Failed to bring up $iface"
        fi
        systemctl enable "wg-quick@${iface}" 2>/dev/null || true
        return
    fi

    # Generate WireGuard keys
    local priv_key pub_key
    priv_key=$(wg genkey)
    pub_key=$(echo "$priv_key" | wg pubkey)

    # Detect listen port from .env or use default
    local listen_port
    listen_port=$(grep "^SERVER_ENDPOINT=" "$INSTALL_DIR/.env" 2>/dev/null | grep -oP ':\K[0-9]+$' || echo "")
    listen_port="${listen_port:-51820}"

    # Detect default network interface for NAT (multiple fallback methods)
    local net_iface
    net_iface=$(ip -4 route show default 2>/dev/null | awk '{print $5}' | head -1)
    if [[ -z "$net_iface" ]]; then
        net_iface=$(ip link show up 2>/dev/null | awk -F: '/^[0-9]+:/{if($2!~"lo|docker|br-|veth|wg|awg|tun") print $2}' | tr -d ' ' | head -1)
    fi
    net_iface="${net_iface:-eth0}"

    # Choose address pool
    local addr_v4="10.66.66.1/24"
    local addr_v6="fd42:42:42::1/64"

    mkdir -p /etc/wireguard
    chmod 700 /etc/wireguard

    # Pre-create the AmneziaWG config dir too so the panel can drop awg0.conf
    # there on first server-create without hitting "no such directory". The
    # apt package from ppa:amnezia/ppa expects /etc/amnezia/amneziawg/.
    mkdir -p /etc/amnezia/amneziawg
    chmod 700 /etc/amnezia/amneziawg

    cat > "$wg_conf" << WGEOF
[Interface]
Address = ${addr_v4}
Address = ${addr_v6}
PostUp = iptables -I INPUT -p udp --dport ${listen_port} -j ACCEPT
PostUp = iptables -I FORWARD -i ${net_iface} -o ${iface} -j ACCEPT
PostUp = iptables -I FORWARD -i ${iface} -o ${iface} -j ACCEPT
PostUp = iptables -I FORWARD -i ${iface} -j ACCEPT
PostUp = iptables -t nat -A POSTROUTING -o ${net_iface} -j MASQUERADE
PostUp = ip6tables -I FORWARD -i ${iface} -j ACCEPT
PostUp = ip6tables -t nat -A POSTROUTING -o ${net_iface} -j MASQUERADE
PostDown = iptables -D INPUT -p udp --dport ${listen_port} -j ACCEPT
PostDown = iptables -D FORWARD -i ${net_iface} -o ${iface} -j ACCEPT
PostDown = iptables -D FORWARD -i ${iface} -o ${iface} -j ACCEPT
PostDown = iptables -D FORWARD -i ${iface} -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o ${net_iface} -j MASQUERADE
PostDown = ip6tables -D FORWARD -i ${iface} -j ACCEPT
PostDown = ip6tables -t nat -D POSTROUTING -o ${net_iface} -j MASQUERADE
ListenPort = ${listen_port}
PrivateKey = ${priv_key}
WGEOF

    chmod 600 "$wg_conf"

    # Enable IPv6 forwarding too
    sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null 2>&1 || true
    if ! grep -q "^net.ipv6.conf.all.forwarding" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
    fi

    # Start interface
    wg-quick up "$iface" 2>/dev/null
    if wg show "$iface" >/dev/null 2>&1; then
        log_success "WireGuard interface $iface is UP (port: $listen_port)"
    else
        log_warn "  Failed to bring up $iface. Check: journalctl -u wg-quick@${iface}"
        return
    fi

    # Enable on boot
    systemctl enable "wg-quick@${iface}" 2>/dev/null || true

    # Update .env with actual values
    sed -i "s|^WG_INTERFACE=.*|WG_INTERFACE=${iface}|" "$INSTALL_DIR/.env" 2>/dev/null || true
    sed -i "s|^WG_CONFIG_PATH=.*|WG_CONFIG_PATH=${wg_conf}|" "$INSTALL_DIR/.env" 2>/dev/null || true

    log_info "  Keys generated, config: $wg_conf"
}

# ============================================================================
# 12. AUTO-REGISTER WIREGUARD SERVER
# ============================================================================
register_wireguard_server() {
    log_info "Registering WireGuard server..."

    if ! command -v wg >/dev/null 2>&1; then
        log_warn "  WireGuard tools not found, skipping registration"
        return
    fi

    local iface
    iface=$(grep "^WG_INTERFACE=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    iface="${iface:-wg0}"

    if ! wg show "$iface" >/dev/null 2>&1; then
        log_info "  WireGuard interface $iface not active, skipping registration"
        return
    fi

    # Get auth token — only if admin already exists (e.g. re-run install)
    # On fresh install admin does NOT exist: user creates it on first web visit
    local setup_status
    setup_status=$(curl -s http://localhost:10086/api/v1/auth/setup-status 2>/dev/null)

    local needs_setup
    needs_setup=$(echo "$setup_status" | python3 -c "import sys,json; print(json.load(sys.stdin).get('needs_setup', False))" 2>/dev/null || echo "")

    local auth_token=""

    if [[ "$needs_setup" == "True" ]]; then
        # No admin yet — user will create one on first web visit (setup wizard)
        log_info "  No admin account yet — create one at the web panel on first visit."
        log_info "  WireGuard server will auto-register after admin setup."
        return
    fi

    # Admin exists — obtain token to register server
    local creds_file="$INSTALL_DIR/.admin_tmp_creds"
    if [[ -f "$creds_file" ]]; then
        local saved_user saved_pass
        saved_user=$(grep "^username=" "$creds_file" 2>/dev/null | cut -d= -f2-)
        saved_pass=$(grep "^password=" "$creds_file" 2>/dev/null | cut -d= -f2-)
        if [[ -n "$saved_user" && -n "$saved_pass" ]]; then
            local login_result
            login_result=$(curl -s -X POST http://localhost:10086/api/v1/auth/login \
                -H "Content-Type: application/json" \
                -d "{\"username\":\"$saved_user\",\"password\":\"$saved_pass\"}" 2>/dev/null)
            auth_token=$(echo "$login_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
        fi
    fi

    if [[ -z "$auth_token" ]]; then
        log_info "  Admin account already exists. Register WireGuard servers via the web panel."
        return
    fi

    # Check if server already registered
    local existing
    existing=$(curl -s -H "Authorization: Bearer $auth_token" http://localhost:10086/api/v1/servers 2>/dev/null)
    if echo "$existing" | python3 -c "import sys,json; data=json.load(sys.stdin); items=data.get('items',data) if isinstance(data,dict) else data; exit(0 if len(items)>0 else 1)" 2>/dev/null; then
        log_info "  Server(s) already registered, skipping"
        return
    fi

    # Get WireGuard info
    local pub_key listen_port priv_key
    pub_key=$(wg show "$iface" public-key 2>/dev/null || echo "")
    listen_port=$(wg show "$iface" listen-port 2>/dev/null || echo "51820")

    local wg_config
    wg_config=$(grep "^WG_CONFIG_PATH=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    wg_config="${wg_config:-/etc/wireguard/${iface}.conf}"

    if [[ -f "$wg_config" ]]; then
        priv_key=$(grep -i "^PrivateKey" "$wg_config" | head -1 | cut -d= -f2- | xargs)
    fi

    if [[ -z "$pub_key" ]] || [[ -z "$priv_key" ]]; then
        log_warn "  Cannot read WireGuard keys, skipping registration"
        return
    fi

    local endpoint
    endpoint=$(grep "^SERVER_ENDPOINT=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    endpoint="${endpoint:-$(curl -s --max-time 3 https://ifconfig.me 2>/dev/null):${listen_port}}"

    # Get address pool from config
    local address_pool="10.66.66.0/24"
    local address_v6=""
    if [[ -f "$wg_config" ]]; then
        local addr_line
        addr_line=$(grep -i "^Address" "$wg_config" | head -1 | awk -F'=' '{print $2}' | xargs)
        if [[ -n "$addr_line" ]]; then
            local ipv4_addr
            ipv4_addr=$(echo "$addr_line" | tr ',' '\n' | grep -v ':' | head -1 | xargs)
            if [[ -n "$ipv4_addr" ]]; then
                local subnet
                subnet=$(echo "$ipv4_addr" | grep -oP '/\d+')
                local base_ip
                base_ip=$(echo "$ipv4_addr" | cut -d/ -f1 | awk -F. '{printf "%s.%s.%s.0", $1,$2,$3}')
                address_pool="${base_ip}${subnet}"
            fi
            address_v6=$(echo "$addr_line" | tr ',' '\n' | grep ':' | head -1 | xargs)
        fi
    fi

    local dns
    dns=$(grep "^DNS_SERVERS=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    dns="${dns:-1.1.1.1,1.0.0.1}"

    local max_clients=253

    # Register via API
    local json_payload
    json_payload=$(python3 -c "
import json
data = {
    'name': 'Main Server',
    'endpoint': '$endpoint',
    'public_key': '$pub_key',
    'private_key': '$priv_key',
    'interface': '$iface',
    'listen_port': int('$listen_port'),
    'address_pool_ipv4': '$address_pool',
    'dns': '$dns',
    'max_clients': $max_clients,
}
if '$address_v6':
    data['address_pool_ipv6'] = '$address_v6'
print(json.dumps(data))
" 2>/dev/null)

    if [[ -z "$json_payload" ]]; then
        log_warn "  Failed to build registration payload"
        return
    fi

    local result
    result=$(curl -s -X POST http://localhost:10086/api/v1/servers \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $auth_token" \
        -d "$json_payload" 2>/dev/null)

    if echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null | grep -q "[0-9]"; then
        log_success "WireGuard server registered (interface: $iface, port: $listen_port)"
    else
        local detail
        detail=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail','unknown error'))" 2>/dev/null || echo "$result")
        log_warn "  Server registration failed: $detail"
    fi
}

apply_web_access_setup() {
    local script_path="$INSTALL_DIR/scripts/configure-web-access.sh"
    local cmd=()

    if [[ ! -x "$script_path" ]]; then
        log_warn "Web access script not found: $script_path"
        return
    fi

    if [[ "$WEB_SETUP_MODE" == "none" ]]; then
        log_info "  Web proxy/TLS skipped for now. You can configure it later via Settings -> Web Access or scripts/configure-web-access.sh"
        return
    fi

    cmd=(bash "$script_path" --install-dir "$INSTALL_DIR" --mode "$WEB_SETUP_MODE" --portal-domain "$WEB_PORTAL_DOMAIN" --email "$WEB_CERTBOT_EMAIL")
    if [[ -n "$WEB_ADMIN_DOMAIN" ]]; then
        cmd+=(--admin-domain "$WEB_ADMIN_DOMAIN")
    fi

    log_info "Applying nginx / HTTPS configuration..."
    if "${cmd[@]}"; then
        log_success "Web access configured"
    else
        log_error "Web access setup failed. Review the package/nginx output above."
        return 1
    fi
}

# ============================================================================
# 13. VERIFICATION
# ============================================================================
verify() {
    echo ""
    log_info "Verification..."

    local errors=0

    # curl prints "000" through --write-out even when the request itself
    # fails. Appending another fallback with `|| echo 000` therefore produced
    # the misleading "HTTP 000000" seen during a normal API restart. Keep a
    # single normalized code and allow freshly restarted services a bounded
    # startup window before reporting a customer-visible warning.
    _verification_http_code() {
        local url="$1" code
        if code=$(curl -s -o /dev/null -w "%{http_code}" \
            --connect-timeout 3 --max-time 5 "$url" 2>/dev/null); then
            printf '%s' "$code"
        else
            printf '000'
        fi
    }

    _verification_wait_http_code() {
        local url="$1" expected="$2" attempts="${3:-5}" delay="${4:-2}"
        local attempt code="000"
        for ((attempt=1; attempt<=attempts; attempt++)); do
            code=$(_verification_http_code "$url")
            if [[ "$code" =~ $expected ]]; then
                break
            fi
            if (( attempt < attempts )); then
                sleep "$delay"
            fi
        done
        printf '%s' "$code"
    }

    # Resolve where api actually lives. apply_web_access_setup may have
    # moved it off :10086 (the public TLS port nginx is now on) onto
    # 127.0.0.1:10087. Read API_PORT from .env if it's there so verify
    # checks the right backend even after the migration.
    local API_PORT_LIVE=10086
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        local env_port
        env_port=$(grep '^API_PORT=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2-)
        [[ -n "$env_port" ]] && API_PORT_LIVE="$env_port"
    fi

    # API health (always hit the backend over plain HTTP on localhost — the
    # api process is loopback-bound when nginx is in front of it, so this
    # works for all WEB_SETUP_MODE values).
    local http_code
    http_code=$(_verification_wait_http_code \
        "http://127.0.0.1:${API_PORT_LIVE}/health" '^200$' 10 2)
    if [[ "$http_code" == "200" ]]; then
        log_success "  API: healthy (HTTP 200)"
    else
        log_warn "  API: not responding (HTTP $http_code on port ${API_PORT_LIVE})"
        errors=$((errors + 1))
    fi

    # Admin panel
    http_code=$(_verification_wait_http_code \
        "http://127.0.0.1:${API_PORT_LIVE}/" '^200$' 3 2)
    if [[ "$http_code" == "200" ]]; then
        log_success "  Admin panel: OK"
    else
        log_warn "  Admin panel: not available (HTTP $http_code)"
        errors=$((errors + 1))
    fi

    # Client portal health endpoint
    local portal_http_code
    portal_http_code=$(_verification_wait_http_code \
        "http://127.0.0.1:10090/health" '^200$' 5 2)
    if [[ "$portal_http_code" == "200" ]]; then
        log_success "  Client portal: OK"
    elif systemctl is-active --quiet vpnmanager-client-portal 2>/dev/null; then
        log_warn "  Client portal: startup lag detected (HTTP $portal_http_code); service is running, re-check with: sudo vpnmanager health"
    else
        log_warn "  Client portal: not available (HTTP $portal_http_code)"
        errors=$((errors + 1))
    fi

    # API authentication (401 = no token, 403 = activation mode / no license yet — both are correct)
    http_code=$(_verification_wait_http_code \
        "http://127.0.0.1:${API_PORT_LIVE}/api/v1/clients" '^(401|403)$' 3 2)
    if [[ "$http_code" == "401" ]]; then
        log_success "  API auth: protected (401 without token)"
    elif [[ "$http_code" == "403" ]]; then
        log_success "  API auth: activation mode (403 — enter license key to unlock)"
    else
        log_warn "  API auth: unexpected response ($http_code)"
        errors=$((errors + 1))
    fi

    # Systemd services
    if systemctl is-active --quiet vpnmanager-api 2>/dev/null; then
        log_success "  vpnmanager-api: running"
    else
        log_warn "  vpnmanager-api: not running"
        errors=$((errors + 1))
    fi

    if systemctl is-active --quiet vpnmanager-client-portal 2>/dev/null; then
        log_success "  vpnmanager-client-portal: running"
    else
        log_warn "  vpnmanager-client-portal: not running"
        errors=$((errors + 1))
    fi

    if grep -q "WORKER_ENABLED=true" "$INSTALL_DIR/.env" 2>/dev/null; then
        if systemctl is-active --quiet vpnmanager-worker 2>/dev/null; then
            log_success "  vpnmanager-worker: running"
        else
            log_warn "  vpnmanager-worker: not running"
            errors=$((errors + 1))
        fi
    else
        log_info "  vpnmanager-worker: skipped (disabled)"
    fi

    # Admin bot
    local admin_token
    admin_token=$(grep "^ADMIN_BOT_TOKEN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    if [[ -n "$admin_token" ]]; then
        if systemctl is-active --quiet vpnmanager-admin-bot 2>/dev/null; then
            log_success "  vpnmanager-admin-bot: running"
        else
            log_warn "  vpnmanager-admin-bot: not running"
            errors=$((errors + 1))
        fi
    else
        log_info "  vpnmanager-admin-bot: skipped (no token)"
    fi

    # Client bot
    local client_token
    client_token=$(grep "^CLIENT_BOT_TOKEN=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2)
    if grep -q "CLIENT_BOT_ENABLED=true" "$INSTALL_DIR/.env" 2>/dev/null && [[ -n "$client_token" ]]; then
        if systemctl is-active --quiet vpnmanager-client-bot 2>/dev/null; then
            log_success "  vpnmanager-client-bot: running"
        else
            log_warn "  vpnmanager-client-bot: not running"
            errors=$((errors + 1))
        fi
    else
        log_info "  vpnmanager-client-bot: skipped (not configured)"
    fi

    if grep -qE "^WEB_SETUP_MODE=(portal_|auto_selfsigned_ip)" "$INSTALL_DIR/.env" 2>/dev/null; then
        if systemctl is-active --quiet nginx 2>/dev/null; then
            log_success "  nginx: running"
        else
            log_warn "  nginx: not running"
            errors=$((errors + 1))
        fi
    fi

    # Database
    if "$INSTALL_DIR/venv/bin/python" -c "
from dotenv import load_dotenv; load_dotenv('$INSTALL_DIR/.env')
from sqlalchemy import create_engine, text
import os
e = create_engine(os.getenv('DATABASE_URL'))
with e.connect() as c: c.execute(text('SELECT 1'))
print('ok')
" 2>/dev/null | grep -q "ok"; then
        log_success "  Database: connected"
    else
        log_warn "  Database: connection failed"
        errors=$((errors + 1))
    fi

    return $errors
}

# ============================================================================
# 14. SUMMARY
# ============================================================================
print_summary() {
    log_step_done

    local server_ip
    server_ip=$(curl -s --max-time 3 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

    echo ""
    echo "==============================================================="
    echo -e "  ${GREEN}${BOLD}Flirexa v${APP_VERSION} — Installation Complete${NC}"
    echo "==============================================================="
    echo ""
    local admin_url portal_url
    portal_url=$(grep '^CLIENT_PORTAL_URL=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2-)
    admin_url=$(grep '^ADMIN_PANEL_URL=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2-)
    portal_url="${portal_url:-http://$server_ip:10090}"
    admin_url="${admin_url:-http://$server_ip:10086}"

    echo "  Admin Panel:     $admin_url"
    echo "  Client Portal:   $portal_url"
    echo "  API Docs:        ${admin_url%/}/api/docs"
    echo ""

    echo -e "  ${BOLD}First visit:${NC} open the admin panel and create your admin account."
    echo "  The setup wizard will appear automatically."
    echo ""

    local license_key
    license_key=$(grep "^LICENSE_KEY=" "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2-)
    if [[ -z "$license_key" ]]; then
        echo -e "  ${BOLD}Tier:${NC} FREE (WireGuard + AmneziaWG, up to 80 clients,"
        echo "         1 server per protocol)."
        echo "    Want paid features (multi-server, Hysteria2/TUIC,"
        echo "    auto-backup, white-label)? Get an Activation Code at"
        echo "    https://flirexa.biz and paste it in the admin panel"
        echo "    under Settings → License."
        echo ""
    fi

    echo "  Features:"
    echo "    - JWT-authenticated admin panel with brute-force protection"
    echo "    - Client self-service portal with subscription plans"
    echo "    - Agent mode for remote WireGuard management"
    echo "    - Telegram bots (admin + client)"
    echo "    - Backup/restore, traffic rules, bandwidth limits"
    echo ""
    echo "  Management Commands:"
    echo "    systemctl status vpnmanager-api"
    echo "    systemctl status vpnmanager-client-portal"
    echo "    systemctl status vpnmanager-admin-bot"
    echo "    systemctl restart vpnmanager-api"
    echo "    journalctl -u vpnmanager-api -f"
    echo ""
    echo "  Files:"
    echo "    Install:   $INSTALL_DIR"
    echo "    Config:    $INSTALL_DIR/.env"
    echo "    Logs:      journalctl -u vpnmanager-*"
    echo ""
    echo "==============================================================="
}

# ============================================================================
# MAIN
# ============================================================================

# Stores initial admin password if created during install
INITIAL_ADMIN_PASSWORD=""  # unused, kept for compat

main() {
    echo ""
    echo "==============================================================="
    echo "  Flirexa v${APP_VERSION} Installer (v${INSTALLER_VERSION})"
    echo "  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==============================================================="
    echo ""

    parse_args "$@"
    _collect_support_contact

    # Each phase is wrapped in _phase so the license server sees a per-step
    # ok / fail beacon and, on a mid-phase death (OOM, SIGHUP, network drop
    # mid-pip), the EXIT trap labels which step we were in. The funnel
    # then shows exactly where install attempts are failing instead
    # of "inner_start → silence".
    _phase preflight                          preflight
    _phase detect_existing                    detect_existing
    _phase install_system_deps                install_system_deps
    _phase setup_postgresql                   setup_postgresql
    _phase copy_files                         copy_files
    _phase prepare_runtime_layout             prepare_runtime_layout
    _phase setup_python                       setup_python
    _phase configure_env                      configure_env
    _phase reset_runtime_state                reset_runtime_state_for_fresh_install
    _phase configure_web_access_preferences   configure_web_access_preferences
    _phase init_database                      init_database
    _phase install_systemd                    install_systemd
    _phase configure_firewall                 configure_firewall
    _phase setup_wireguard                    setup_wireguard
    _phase start_services                     start_services
    _phase register_wireguard_server          register_wireguard_server

    _phase apply_web_access_setup             apply_web_access_setup

    local exit_code=0
    _phase verify                             verify || exit_code=$?

    # Verified ok — final success beacon so the funnel's final_status flips
    # from in_progress → ok for this install_id.
    if [[ $exit_code -eq 0 ]]; then
        _PHASE_REPORTED=1
        _inner_beacon "inner_complete" "ok"
    fi

    print_summary

    if [[ $exit_code -ne 0 ]]; then
        echo ""
        log_warn "Some checks failed. Review warnings above."
        log_info "Troubleshooting: journalctl -u vpnmanager-api -n 50"
    fi

    exit "$exit_code"
}

main "$@"
