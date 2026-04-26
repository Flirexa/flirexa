#!/bin/bash
# ============================================================================
# VPN Manager Update Script
# Обновление системы с минимальным даунтаймом (~5-10 секунд)
#
# WireGuard НЕ затрагивается — VPN-трафик клиентов идёт непрерывно.
# Кратковременно недоступны: веб-панель + Telegram-бот (во время рестарта).
#
# Использование:
#   bash update.sh              — полное обновление (код + фронт + рестарт)
#   bash update.sh --no-build   — без пересборки фронтенда
#   bash update.sh --setup      — первичная установка systemd-сервисов
#   bash update.sh --dir /path  — указать директорию установки
# ============================================================================

set -euo pipefail

# Auto-detect install directory (check common locations)
detect_install_dir() {
    if [ -n "${INSTALL_DIR:-}" ]; then
        echo "$INSTALL_DIR"
    elif [ -L "./current" ] && [ -f "./current/main.py" ]; then
        echo "$(pwd)"
    elif [ -f "./main.py" ] && [ -d "./src" ]; then
        echo "$(pwd)"
    elif [ -d "/opt/spongebot" ] && [ -L "/opt/spongebot/current" ]; then
        echo "/opt/spongebot"
    elif [ -d "/opt/spongebot" ] && [ -f "/opt/spongebot/main.py" ]; then
        echo "/opt/spongebot"
    elif [ -d "/opt/vpnmanager" ] && [ -L "/opt/vpnmanager/current" ]; then
        echo "/opt/vpnmanager"
    elif [ -d "/opt/vpnmanager" ] && [ -f "/opt/vpnmanager/main.py" ]; then
        echo "/opt/vpnmanager"
    elif [ -d "/opt/vpnmanager" ] && [ -f "/opt/vpnmanager/main.py" ]; then
        echo "/opt/vpnmanager"
    else
        echo ""
    fi
}

detect_service_prefix() {
    if systemctl list-unit-files 2>/dev/null | grep -q '^vpnmanager-api\.service'; then
        echo "vpnmanager"
    elif systemctl list-unit-files 2>/dev/null | grep -q '^spongebot-api\.service'; then
        echo "spongebot"
    elif [ -d "/etc/systemd/system" ] && ls /etc/systemd/system/vpnmanager-*.service >/dev/null 2>&1; then
        echo "vpnmanager"
    else
        echo "spongebot"
    fi
}

SPONGEBOT_DIR="$(detect_install_dir)"
SERVICE_PREFIX="${SERVICE_PREFIX:-$(detect_service_prefix)}"
CLIENT_PORTAL_SERVICE="${SERVICE_PREFIX}-client-portal"
BACKUP_DIR="${BACKUP_DIR:-/root/${SERVICE_PREFIX}_backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[UPDATE]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

has_systemd_service() {
    [ -f "/etc/systemd/system/$1.service" ] || \
    [ -f "/lib/systemd/system/$1.service" ] || \
    [ -f "/usr/lib/systemd/system/$1.service" ] || \
    systemctl list-unit-files 2>/dev/null | grep -q "^$1\.service"
}

install_service_unit_from_template() {
    local source_name="$1"
    local target_name="$2"
    local src=""
    local dst="/etc/systemd/system/${target_name}.service"

    if [ -f "$SPONGEBOT_DIR/deploy/systemd/${source_name}.service" ]; then
        src="$SPONGEBOT_DIR/deploy/systemd/${source_name}.service"
    elif [ -f "$SPONGEBOT_DIR/deploy/${source_name}.service" ]; then
        src="$SPONGEBOT_DIR/deploy/${source_name}.service"
    else
        return 1
    fi

    cp "$src" "$dst"
    sed -i \
        -e "s|/opt/vpnmanager|$SPONGEBOT_DIR|g" \
        -e "s|/opt/spongebot|$SPONGEBOT_DIR|g" \
        -e "s|vpnmanager-|${SERVICE_PREFIX}-|g" \
        -e "s|spongebot-|${SERVICE_PREFIX}-|g" \
        "$dst"
    return 0
}

wait_for_http() {
    local url="$1"
    local expected="${2:-200}"
    local attempts="${3:-15}"
    local delay="${4:-1}"
    local http_code=""

    for _ in $(seq 1 "$attempts"); do
        http_code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true)
        if [ "$http_code" = "$expected" ]; then
            echo "$http_code"
            return 0
        fi
        sleep "$delay"
    done

    echo "${http_code:-000}"
    return 1
}

load_env() {
    [ -f "$SPONGEBOT_DIR/.env" ] || err ".env file not found in $SPONGEBOT_DIR"
    set -a
    # shellcheck disable=SC1090
    . "$SPONGEBOT_DIR/.env"
    set +a
}

# ============================================================================
# 1. PRE-FLIGHT CHECKS
# ============================================================================
preflight() {
    log "Pre-flight checks..."

    [ -n "$SPONGEBOT_DIR" ] || err "Cannot detect install directory. Use --dir /path or run from project root."
    [ -d "$SPONGEBOT_DIR" ] || err "Install directory not found: $SPONGEBOT_DIR"
    load_env

    VENV="$SPONGEBOT_DIR/venv"
    [ -d "$VENV" ] || err "Virtual environment not found: $VENV"

    # Check PostgreSQL
    if ! pg_isready -q 2>/dev/null; then
        err "PostgreSQL is not running"
    fi

    # Check disk space (need at least 500MB)
    AVAIL=$(df -m "$SPONGEBOT_DIR" | awk 'NR==2{print $4}')
    [ "$AVAIL" -gt 500 ] || err "Not enough disk space: ${AVAIL}MB available, need 500MB+"

    log "Pre-flight OK (dir: $SPONGEBOT_DIR, disk: ${AVAIL}MB free)"
}

# ============================================================================
# 2. BACKUP
# ============================================================================
backup() {
    log "Creating backup..."
    mkdir -p "$BACKUP_DIR"

    # Backup .env (critical — contains tokens)
    cp "$SPONGEBOT_DIR/.env" "$BACKUP_DIR/.env.backup.$TIMESTAMP"

    DB_USER="${DB_USER:-}"
    DB_NAME="${DB_NAME:-}"
    DB_PASS="${DB_PASS:-}"
    DB_HOST="${DB_HOST:-127.0.0.1}"
    DB_PORT="${DB_PORT:-5432}"

    if [ -n "${DATABASE_URL:-}" ]; then
        eval "$(python3 - <<'PY'
from urllib.parse import urlparse
import os
url = os.environ.get("DATABASE_URL", "")
if url:
    parsed = urlparse(url)
    print(f"DB_USER='{parsed.username or ''}'")
    print(f"DB_PASS='{parsed.password or ''}'")
    print(f"DB_HOST='{parsed.hostname or '127.0.0.1'}'")
    print(f"DB_PORT='{parsed.port or 5432}'")
    print(f"DB_NAME='{(parsed.path or '/').lstrip('/')}'")
PY
)"
    fi

    if [ -n "$DB_USER" ] && [ -n "$DB_NAME" ]; then
        PGPASSWORD="$DB_PASS" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql" 2>/dev/null \
            || warn "pg_dump failed (credentials/pg_hba mismatch). DB backup skipped."
    else
        warn "Database credentials not resolved from .env. DB backup skipped."
    fi

    log "Backup saved to $BACKUP_DIR/ (timestamp: $TIMESTAMP)"
}

# ============================================================================
# 3. INSTALL DEPENDENCIES (if requirements.txt changed)
# ============================================================================
install_deps() {
    log "Checking Python dependencies..."
    "$VENV/bin/pip" install -q -r "$SPONGEBOT_DIR/requirements.txt" 2>&1 | tail -1
    log "Dependencies OK"
}

# ============================================================================
# 4. RUN DATABASE MIGRATIONS
# ============================================================================
run_migrations() {
    log "Running database migrations..."

    if [ -d "$SPONGEBOT_DIR/alembic" ] && [ -f "$SPONGEBOT_DIR/alembic.ini" ]; then
        cd "$SPONGEBOT_DIR"
        "$VENV/bin/python" -m alembic upgrade head 2>&1 | tail -5
        log "Migrations applied"
    else
        warn "No Alembic directory (alembic/ + alembic.ini) found — skipping migrations"
    fi
}

# ============================================================================
# 5. BUILD FRONTEND
# ============================================================================
build_frontend() {
    if [ "${NO_BUILD:-0}" = "1" ]; then
        warn "Skipping frontend build (--no-build)"
        return
    fi

    # Admin frontend
    if [ -d "$SPONGEBOT_DIR/src/web/frontend" ]; then
        log "Building admin frontend..."
        cd "$SPONGEBOT_DIR/src/web/frontend"

        if [ ! -d "node_modules" ]; then
            npm install --silent 2>&1 | tail -1
        fi

        # Remove old dist to prevent stale chunk accumulation
        rm -rf "$SPONGEBOT_DIR/src/web/static/dist"
        npm run build 2>&1 | tail -3
        cd "$SPONGEBOT_DIR"
        log "Admin frontend built"
    fi

    # Client portal frontend
    if [ -d "$SPONGEBOT_DIR/src/web/client-portal" ]; then
        log "Building client portal frontend..."
        cd "$SPONGEBOT_DIR/src/web/client-portal"

        if [ ! -d "node_modules" ]; then
            npm install --silent 2>&1 | tail -1
        fi

        rm -rf "$SPONGEBOT_DIR/src/web/client-portal-dist"
        npm run build 2>&1 | tail -3
        cd "$SPONGEBOT_DIR"
        log "Client portal frontend built"
    fi
}

# ============================================================================
# 6. SETUP SYSTEMD (one-time, --setup flag)
# ============================================================================
setup_systemd() {
    log "Installing systemd services..."

    local source_prefix="$SERVICE_PREFIX"
    if [ "$SERVICE_PREFIX" = "spongebot" ]; then
        source_prefix="vpnmanager"
    fi

    for suffix in api admin-bot client-bot worker; do
        install_service_unit_from_template "${source_prefix}-${suffix}" "${SERVICE_PREFIX}-${suffix}" || true
    done

    install_service_unit_from_template "${source_prefix}-client-portal" "${CLIENT_PORTAL_SERVICE}" || true

    systemctl daemon-reload

    # Stop any manually running processes first
    log "Stopping manually started processes..."
    pkill -f "main.py api" 2>/dev/null && sleep 1 || true
    pkill -f "main.py admin-bot" 2>/dev/null && sleep 1 || true
    pkill -f "main.py client-bot" 2>/dev/null && sleep 1 || true
    pkill -f "client_portal_main.py" 2>/dev/null && sleep 1 || true
    pkill -f "worker_main.py" 2>/dev/null && sleep 1 || true

    # Enable and start services
    systemctl enable "${SERVICE_PREFIX}-api"
    systemctl start "${SERVICE_PREFIX}-api"
    sleep 2

    systemctl enable "${SERVICE_PREFIX}-admin-bot"
    systemctl start "${SERVICE_PREFIX}-admin-bot"

    # Client portal
    systemctl enable "${CLIENT_PORTAL_SERVICE}" 2>/dev/null && \
        systemctl start "${CLIENT_PORTAL_SERVICE}" || \
        warn "Client portal service not found"

    # Worker — if WORKER_ENABLED in .env
    if grep -q "WORKER_ENABLED=true" "$SPONGEBOT_DIR/.env" 2>/dev/null; then
        systemctl enable "${SERVICE_PREFIX}-worker" 2>/dev/null && \
            systemctl start "${SERVICE_PREFIX}-worker" && \
            log "Worker enabled and started" || \
            warn "Worker service file not found"
    else
        warn "Worker disabled in .env (WORKER_ENABLED!=true) — not starting"
    fi

    # Client bot — only if enabled in .env
    if grep -q "CLIENT_BOT_ENABLED=true" "$SPONGEBOT_DIR/.env" 2>/dev/null; then
        systemctl enable "${SERVICE_PREFIX}-client-bot"
        systemctl start "${SERVICE_PREFIX}-client-bot"
        log "Client bot enabled and started"
    else
        warn "Client bot disabled in .env — not starting"
    fi

    log "Systemd services installed and started"
    systemctl status "${SERVICE_PREFIX}-api" "${SERVICE_PREFIX}-admin-bot" --no-pager -l | head -20
}

# ============================================================================
# 7. RESTART SERVICES (the fast part — ~5 seconds downtime)
# ============================================================================
restart_services() {
    log "=== RESTARTING SERVICES (brief downtime starts) ==="

    # Check if running via systemd or manually
    if has_systemd_service "${SERVICE_PREFIX}-api"; then
        # Systemd mode
        systemctl daemon-reload
        systemctl restart "${SERVICE_PREFIX}-api"

        # Client portal
        if has_systemd_service "${CLIENT_PORTAL_SERVICE}"; then
            systemctl restart "${CLIENT_PORTAL_SERVICE}"
        fi

        # Admin bot
        if has_systemd_service "${SERVICE_PREFIX}-admin-bot"; then
            systemctl restart "${SERVICE_PREFIX}-admin-bot"
        fi

        # Worker
        if has_systemd_service "${SERVICE_PREFIX}-worker"; then
            systemctl restart "${SERVICE_PREFIX}-worker"
        fi

        # Client bot
        if has_systemd_service "${SERVICE_PREFIX}-client-bot" && \
           systemctl is-enabled "${SERVICE_PREFIX}-client-bot" >/dev/null 2>&1; then
            systemctl restart "${SERVICE_PREFIX}-client-bot"
        fi
    else
        # Manual mode — kill and restart
        warn "Services not in systemd. Restarting manually..."

        pkill -f "main.py api" 2>/dev/null || true
        pkill -f "main.py admin-bot" 2>/dev/null || true
        pkill -f "main.py client-bot" 2>/dev/null || true
        pkill -f "client_portal_main.py" 2>/dev/null || true
        pkill -f "worker_main.py" 2>/dev/null || true
        sleep 2

        cd "$SPONGEBOT_DIR"
        nohup "$VENV/bin/python" main.py api --port 10086 > "/tmp/${SERVICE_PREFIX}-api.log" 2>&1 &
        sleep 2
        nohup "$VENV/bin/python" main.py admin-bot > "/tmp/${SERVICE_PREFIX}-admin-bot.log" 2>&1 &
        nohup "$VENV/bin/python" client_portal_main.py > "/tmp/${SERVICE_PREFIX}-client-portal.log" 2>&1 &

        # Worker
        if grep -q "WORKER_ENABLED=true" "$SPONGEBOT_DIR/.env" 2>/dev/null; then
            nohup "$VENV/bin/python" worker_main.py > "/tmp/${SERVICE_PREFIX}-worker.log" 2>&1 &
        fi

        if grep -q "CLIENT_BOT_ENABLED=true" "$SPONGEBOT_DIR/.env" 2>/dev/null; then
            nohup "$VENV/bin/python" main.py client-bot > "/tmp/${SERVICE_PREFIX}-client-bot.log" 2>&1 &
        fi
    fi

    sleep 3
    log "=== SERVICES RESTARTED (downtime ended) ==="
}

# ============================================================================
# 8. POST-UPDATE VERIFICATION
# ============================================================================
verify() {
    log "Verifying..."
    ERRORS=0

    # Check API
    HTTP_CODE=$(wait_for_http http://localhost:10086/health 200 15 1)
    if [ "$HTTP_CODE" = "200" ]; then
        log "  API: OK (HTTP 200)"
    else
        warn "  API: FAILED (HTTP $HTTP_CODE)"
        ERRORS=$((ERRORS + 1))
    fi

    # Check Client Portal
    HTTP_CODE=$(wait_for_http http://localhost:10090/health 200 20 1)
    if [ "$HTTP_CODE" = "200" ]; then
        log "  Client Portal: OK (HTTP 200)"
    else
        warn "  Client Portal: FAILED (HTTP $HTTP_CODE)"
        ERRORS=$((ERRORS + 1))
    fi

    # Check processes
    if pgrep -f "main.py api" >/dev/null; then
        log "  API process: running"
    else
        warn "  API process: NOT RUNNING"
        ERRORS=$((ERRORS + 1))
    fi

    if [ -n "${ADMIN_BOT_TOKEN:-}" ]; then
        if pgrep -f "main.py admin-bot" >/dev/null; then
            log "  Admin bot: running"
        else
            warn "  Admin bot: NOT RUNNING"
            ERRORS=$((ERRORS + 1))
        fi
    else
        log "  Admin bot: skipped (no token)"
    fi

    if pgrep -f "client_portal_main.py" >/dev/null; then
        log "  Client portal process: running"
    else
        warn "  Client portal process: NOT RUNNING"
        ERRORS=$((ERRORS + 1))
    fi

    # Worker (systemd or process check)
    if grep -q "WORKER_ENABLED=true" "$SPONGEBOT_DIR/.env" 2>/dev/null; then
        if systemctl is-active "${SERVICE_PREFIX}-worker" >/dev/null 2>&1; then
            log "  Worker service: active"
        elif pgrep -f "worker_main.py" >/dev/null; then
            log "  Worker process: running"
        else
            warn "  Worker: NOT RUNNING (WORKER_ENABLED=true)"
            ERRORS=$((ERRORS + 1))
        fi
    else
        log "  Worker: disabled in .env (OK)"
    fi

    # Check WireGuard (should be untouched)
    WG_IFACE=$(ip -o link show type wireguard 2>/dev/null | head -1 | awk -F: '{print $2}' | tr -d ' ')
    if [ -n "$WG_IFACE" ]; then
        log "  WireGuard ($WG_IFACE): UP — clients unaffected"
    else
        warn "  WireGuard: no interface found"
    fi

    # Check web panel
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:10086/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        log "  Web panel: OK"
    else
        warn "  Web panel: FAILED (HTTP $HTTP_CODE)"
        ERRORS=$((ERRORS + 1))
    fi

    echo ""
    if [ "$ERRORS" -eq 0 ]; then
        log "=== UPDATE COMPLETE — ALL CHECKS PASSED ==="
    else
        warn "=== UPDATE COMPLETE — $ERRORS CHECK(S) FAILED ==="
        warn "Check logs: journalctl -u ${SERVICE_PREFIX}-api -n 50"
        warn "Rollback:   psql -U \$DB_USER \$DB_NAME < $BACKUP_DIR/db_backup_$TIMESTAMP.sql"
    fi
}

# ============================================================================
# ROLLBACK
# ============================================================================
rollback() {
    echo ""
    echo "============================================"
    echo "  VPN Manager Rollback — $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================"
    echo ""

    [ -n "$SPONGEBOT_DIR" ] || err "Cannot detect install directory. Use --dir /path or run from project root."
    [ -d "$SPONGEBOT_DIR" ] || err "Install directory not found: $SPONGEBOT_DIR"
    load_env

    # Find latest backup
    local latest_sql latest_env
    latest_sql=$(ls -t "$BACKUP_DIR"/db_backup_*.sql 2>/dev/null | head -1)
    latest_env=$(ls -t "$BACKUP_DIR"/.env.backup.* 2>/dev/null | head -1)

    if [ -z "$latest_sql" ] && [ -z "$latest_env" ]; then
        err "No backups found in $BACKUP_DIR/"
    fi

    log "Found backups:"
    [ -n "$latest_sql" ] && log "  DB:  $latest_sql"
    [ -n "$latest_env" ] && log "  ENV: $latest_env"

    # Restore .env
    if [ -n "$latest_env" ]; then
        cp "$latest_env" "$SPONGEBOT_DIR/.env"
        log "  .env restored"
    fi

    # Restore database
    if [ -n "$latest_sql" ]; then
        DB_USER="${DB_USER:-}"
        DB_NAME="${DB_NAME:-}"
        DB_PASS="${DB_PASS:-}"
        DB_HOST="${DB_HOST:-127.0.0.1}"
        DB_PORT="${DB_PORT:-5432}"

        if [ -n "${DATABASE_URL:-}" ]; then
            eval "$(python3 - <<'PY'
from urllib.parse import urlparse
import os
url = os.environ.get("DATABASE_URL", "")
if url:
    parsed = urlparse(url)
    print(f"DB_USER='{parsed.username or ''}'")
    print(f"DB_PASS='{parsed.password or ''}'")
    print(f"DB_HOST='{parsed.hostname or '127.0.0.1'}'")
    print(f"DB_PORT='{parsed.port or 5432}'")
    print(f"DB_NAME='{(parsed.path or '/').lstrip('/')}'")
PY
)"
        fi

        if [ -n "$DB_USER" ] && [ -n "$DB_NAME" ]; then
            log "  Restoring database $DB_NAME..."
            PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" < "$latest_sql" 2>/dev/null \
                && log "  Database restored" \
                || warn "  Database restore failed. Manual restore: psql -U $DB_USER $DB_NAME < $latest_sql"
        else
            warn "  Cannot resolve DB credentials. Manual restore:"
            warn "    psql -U \$DB_USER \$DB_NAME < $latest_sql"
        fi
    fi

    # Restart services
    log "Restarting services..."
    if has_systemd_service "${SERVICE_PREFIX}-api"; then
        systemctl restart "${SERVICE_PREFIX}-api"
        has_systemd_service "${CLIENT_PORTAL_SERVICE}" && systemctl restart "${CLIENT_PORTAL_SERVICE}"
        has_systemd_service "${SERVICE_PREFIX}-worker" && systemctl restart "${SERVICE_PREFIX}-worker"
        has_systemd_service "${SERVICE_PREFIX}-admin-bot" && systemctl restart "${SERVICE_PREFIX}-admin-bot"
    fi

    # Quick health check with retry
    HTTP_CODE=$(wait_for_http http://localhost:10086/health 200 15 1)
    if [ "$HTTP_CODE" = "200" ]; then
        log "=== ROLLBACK COMPLETE — API healthy ==="
    else
        warn "=== ROLLBACK COMPLETE — API returned $HTTP_CODE, check logs ==="
    fi
}

# ============================================================================
# MAIN
# ============================================================================
main() {
    echo ""
    echo "============================================"
    echo "  VPN Manager Update — $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================"
    echo ""

    # Parse flags
    NO_BUILD=0
    DO_SETUP=0
    DO_ROLLBACK=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --no-build)  NO_BUILD=1 ;;
            --setup)     DO_SETUP=1 ;;
            --rollback)  DO_ROLLBACK=1 ;;
            --dir)       shift; SPONGEBOT_DIR="$1" ;;
            --help|-h)
                echo "Usage: bash update.sh [--no-build] [--setup] [--rollback] [--dir /path]"
                echo ""
                echo "  --no-build   Skip frontend rebuild"
                echo "  --setup      First-time systemd service installation"
                echo "  --rollback   Restore from latest backup (DB + .env + restart)"
                echo "  --dir PATH   Specify install directory (auto-detected by default)"
                exit 0
                ;;
            *) warn "Unknown flag: $1" ;;
        esac
        shift
    done

    if [ "$DO_ROLLBACK" = "1" ]; then
        rollback
        exit 0
    fi

    preflight
    backup
    install_deps
    run_migrations

    if [ "$DO_SETUP" = "1" ]; then
        build_frontend
        setup_systemd
    else
        build_frontend
        restart_services
    fi

    verify

    echo ""
    log "Backup: $BACKUP_DIR/"
    log "Done."
}

main "$@"
