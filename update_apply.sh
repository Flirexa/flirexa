#!/bin/bash
# =============================================================================
# VPN Management Studio — Stage 1 Update Apply Script
#
# Called by UpdateManager (src/modules/updates/manager.py).
# Environment variables:
#   UPDATE_PACKAGE          — path to downloaded .tar.gz package
#   STAGING_DIR             — controlled staging directory for this update
#   BACKUP_DIR              — backup directory for this update
#   INSTALL_DIR             — installation root (e.g. /opt/vpnmanager)
#   UPDATE_ID               — numeric ID for logging
#   TARGET_VERSION          — target release version
#   EXPECTED_PACKAGE_SHA256 — expected package sha256
#   EXPECTED_PACKAGE_SIZE   — expected package size in bytes
#   REQUIRES_MIGRATION      — true/false
#   REQUIRES_RESTART        — true/false
#   ROLLBACK=1              — run manual rollback from BACKUP_DIR
#
# Exit codes:
#   0 — success
#   1 — failed (no auto-rollback performed)
#   2 — failed, auto-rollback attempted
# =============================================================================

set -euo pipefail

UPDATE_ID="${UPDATE_ID:-0}"
INSTALL_DIR="${INSTALL_DIR:-/opt/vpnmanager}"
STAGING_DIR="${STAGING_DIR:-}"
BACKUP_DIR="${BACKUP_DIR:-}"
UPDATE_PACKAGE="${UPDATE_PACKAGE:-}"
TARGET_VERSION="${TARGET_VERSION:-}"
EXPECTED_PACKAGE_SHA256="${EXPECTED_PACKAGE_SHA256:-}"
EXPECTED_PACKAGE_SIZE="${EXPECTED_PACKAGE_SIZE:-0}"
REQUIRES_MIGRATION="${REQUIRES_MIGRATION:-false}"
REQUIRES_RESTART="${REQUIRES_RESTART:-true}"
SYSTEMD_UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"

LOCK_DIR="$INSTALL_DIR/update-lock"
LOCK_FILE="$LOCK_DIR/update.lock"
STATE_DIR="${BACKUP_DIR:-${STAGING_DIR:-$INSTALL_DIR/data}}"
CURRENT_LINK="$INSTALL_DIR/current"
RELEASES_DIR="$INSTALL_DIR/releases"
MIN_UPDATE_FREE_MB="${MIN_UPDATE_FREE_MB:-500}"
MIN_STAGING_FREE_MB="${MIN_STAGING_FREE_MB:-200}"

log()     { echo "[UPDATE $UPDATE_ID] $(date '+%H:%M:%S') $*"; }
log_err() { echo "[UPDATE $UPDATE_ID] ERROR: $*" >&2; }
write_marker() {
    local name="$1"
    local value="${2:-}"
    mkdir -p "$STATE_DIR"
    printf '%s' "$value" > "$STATE_DIR/$name"
}
marker_exists() {
    [[ -f "$STATE_DIR/$1" ]]
}
active_runtime_root() {
    if [[ -L "$CURRENT_LINK" ]]; then
        readlink -f "$CURRENT_LINK"
    else
        printf '%s\n' "$INSTALL_DIR"
    fi
}
version_file_for_runtime() {
    local root
    root="$(active_runtime_root)"
    printf '%s\n' "$root/VERSION"
}
effective_runtime_root() {
    if [[ "${ROLLBACK:-}" == "1" ]]; then
        active_runtime_root
        return
    fi
    if [[ "${APPLY_MODE:-compat-inplace}" == "release-layout" && -n "${TARGET_RELEASE_DIR:-}" ]]; then
        printf '%s\n' "$TARGET_RELEASE_DIR"
    else
        printf '%s\n' "$INSTALL_DIR"
    fi
}

mkdir -p "$LOCK_DIR"
if ! { exec 200>"$LOCK_FILE"; } 2>/dev/null; then
    log_err "Cannot create lock file: $LOCK_FILE"
    exit 1
fi
if ! flock -n 200 2>/dev/null; then
    log_err "Another update/rollback is already running (lock held: $LOCK_FILE)"
    exit 1
fi

_write_exitcode() {
    local code=$?
    if [[ -n "$STATE_DIR" && -d "$STATE_DIR" ]]; then
        echo "$code" > "$STATE_DIR/apply.exitcode" 2>/dev/null || true
    fi
}
trap '_write_exitcode' EXIT

require_command() {
    command -v "$1" >/dev/null 2>&1 || { log_err "Required command not found: $1"; return 1; }
}

check_disk_space() {
    local dir="$1"
    local required_mb="$2"
    local label="$3"
    mkdir -p "$dir" 2>/dev/null || true
    local available_mb
    available_mb=$(df -m "$dir" 2>/dev/null | awk 'NR==2 {print $4}')
    if [[ -z "$available_mb" ]]; then
        log "WARNING: Could not check disk space at $label — proceeding"
        return 0
    fi
    if [[ "$available_mb" -lt "$required_mb" ]]; then
        log_err "Insufficient disk space at $label: ${available_mb}MB available, ${required_mb}MB required"
        return 1
    fi
    log "  Disk space OK ($label): ${available_mb}MB available"
    return 0
}

detect_service_prefix() {
    local env_file="${INSTALL_DIR}/.env"
    if [[ -f "$env_file" ]]; then
        local svc_name
        svc_name=$(grep -E '^(API_SERVICE|ADMIN_BOT_SERVICE)=' "$env_file" 2>/dev/null \
            | head -1 | cut -d= -f2 | tr -d "'\" " | sed 's/-api$//' | sed 's/-admin-bot$//')
        if [[ -n "$svc_name" ]]; then
            echo "$svc_name"
            return
        fi
    fi
    if systemctl list-unit-files 2>/dev/null | grep -q 'vpnmanager-api'; then
        echo "vpnmanager"
    elif systemctl list-unit-files 2>/dev/null | grep -q 'spongebot-api'; then
        echo "spongebot"
    elif systemctl list-units --state=active 2>/dev/null | grep -q 'vpnmanager-api'; then
        echo "vpnmanager"
    elif systemctl list-units --state=active 2>/dev/null | grep -q 'spongebot-api'; then
        echo "spongebot"
    else
        echo "vpnmanager"
    fi
}

SVC_PREFIX="$(detect_service_prefix)"
API_SVC="${SVC_PREFIX}-api"
WORKER_SVC="${SVC_PREFIX}-worker"
ADMIN_BOT_SVC="${SVC_PREFIX}-admin-bot"
CLIENT_BOT_SVC="${SVC_PREFIX}-client-bot"
PORTAL_SVC="${SVC_PREFIX}-client-portal"
ALL_SVCS=("$API_SVC" "$WORKER_SVC" "$ADMIN_BOT_SVC" "$CLIENT_BOT_SVC" "$PORTAL_SVC")
STARTUP_LOG_SINCE=""
LEGACY_PRODUCT_LABEL="$(printf 'Sponge%s' 'Bot')"

stop_services() {
    log "Stopping services …"
    for svc in "${ALL_SVCS[@]}"; do
        systemctl stop "$svc" 2>/dev/null && log "  stopped $svc" || true
    done
}

start_services() {
    log "Starting services …"
    STARTUP_LOG_SINCE="$(date --iso-8601=seconds)"
    for svc in "${ALL_SVCS[@]}"; do
        if systemctl cat "$svc" >/dev/null 2>&1; then
            systemctl start "$svc" 2>/dev/null && log "  started $svc" || log "  WARNING: could not start $svc"
        fi
    done
}
cli_entrypoint_source() {
    if [[ -L "$CURRENT_LINK" && -f "$CURRENT_LINK/vpnmanager" ]]; then
        printf '%s\n' "$CURRENT_LINK/vpnmanager"
        return 0
    fi
    if [[ -n "${TARGET_RELEASE_DIR:-}" && -f "$TARGET_RELEASE_DIR/vpnmanager" ]]; then
        printf '%s\n' "$TARGET_RELEASE_DIR/vpnmanager"
        return 0
    fi
    if [[ -f "$INSTALL_DIR/vpnmanager" ]]; then
        printf '%s\n' "$INSTALL_DIR/vpnmanager"
        return 0
    fi
    return 1
}
install_cli_entrypoint() {
    local source_file
    source_file="$(cli_entrypoint_source || true)"
    if [[ -z "$source_file" ]]; then
        log "  WARNING: vpnmanager CLI source not found; skipping /usr/local/bin/vpnmanager"
        return 0
    fi
    chmod 755 "$source_file" 2>/dev/null || true
    ln -sfn "$source_file" /usr/local/bin/vpnmanager
    log "  Installed CLI entrypoint: /usr/local/bin/vpnmanager -> $source_file"
}
install_service_units_from_release() {
    local release_root="$1"
    local svc src dst source_name
    mkdir -p "$SYSTEMD_UNIT_DIR"

    for svc in "$API_SVC" "$ADMIN_BOT_SVC" "$CLIENT_BOT_SVC" "$WORKER_SVC"; do
        source_name="$svc"
        if [[ "$SVC_PREFIX" == "spongebot" ]]; then
            source_name="${svc/spongebot/vpnmanager}"
        fi
        src="$release_root/deploy/systemd/${source_name}.service"
        dst="$SYSTEMD_UNIT_DIR/${svc}.service"
        if [[ -f "$src" ]]; then
            cp "$src" "$dst"
            sed -i \
                -e "s|/opt/vpnmanager|$INSTALL_DIR|g" \
                -e "s|vpnmanager-|${SVC_PREFIX}-|g" \
                -e "s|VPN Management Studio|${LEGACY_PRODUCT_LABEL}|g" \
                "$dst"
        fi
    done

    src="$release_root/deploy/${PORTAL_SVC}.service"
    if [[ ! -f "$src" && "$SVC_PREFIX" == "spongebot" ]]; then
        src="$release_root/deploy/vpnmanager-client-portal.service"
    fi
    dst="$SYSTEMD_UNIT_DIR/${PORTAL_SVC}.service"
    if [[ -f "$src" ]]; then
        cp "$src" "$dst"
        sed -i \
            -e "s|/opt/vpnmanager|$INSTALL_DIR|g" \
            -e "s|vpnmanager-|${SVC_PREFIX}-|g" \
            -e "s|VPN Management Studio|${LEGACY_PRODUCT_LABEL}|g" \
            "$dst"
    fi

    systemctl daemon-reload
}
is_versioned_runtime_supported() {
    local extract_root="$1"
    [[ -d "$RELEASES_DIR" ]] || return 1
    [[ -L "$CURRENT_LINK" || ! -e "$CURRENT_LINK" ]] || return 1
    if [[ "$SVC_PREFIX" == "vpnmanager" ]]; then
        [[ -f "$extract_root/deploy/systemd/${API_SVC}.service" ]] || return 1
        [[ -f "$extract_root/deploy/${PORTAL_SVC}.service" ]] || return 1
    elif [[ "$SVC_PREFIX" == "spongebot" ]]; then
        [[ -f "$extract_root/deploy/systemd/vpnmanager-api.service" ]] || return 1
        [[ -f "$extract_root/deploy/vpnmanager-client-portal.service" ]] || return 1
    else
        return 1
    fi
    return 0
}
sync_release_tree() {
    local src="$1"
    local dst="$2"
    mkdir -p "$dst"
    rsync -a --checksum --delete-after \
        --exclude='.env' \
        --exclude='data/' \
        --exclude='venv/' \
        --exclude='backups/' \
        --exclude='staging/' \
        --exclude='update-lock/' \
        --exclude='shared/' \
        --exclude='releases/' \
        --exclude='current' \
        --exclude='.git/' \
        --exclude='*.pyc' \
        --exclude='__pycache__/' \
        "$src/" "$dst/"
}
prepare_previous_release_path() {
    local runtime_root current_version snapshot_dir
    runtime_root="$(active_runtime_root)"
    if [[ "$runtime_root" == "$INSTALL_DIR" ]]; then
        current_version="$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo "unknown")"
        snapshot_dir="$RELEASES_DIR/$current_version"
        if [[ ! -d "$snapshot_dir" || -z "$(ls -A "$snapshot_dir" 2>/dev/null)" ]]; then
            log "  Creating compatibility snapshot for current runtime: $snapshot_dir" >&2
            sync_release_tree "$INSTALL_DIR" "$snapshot_dir"
        fi
        printf '%s\n' "$snapshot_dir"
        return 0
    fi
    printf '%s\n' "$runtime_root"
}

load_db_url() {
    local db_url="${DATABASE_URL:-}"
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        local env_url
        env_url=$(grep '^DATABASE_URL=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
        db_url="${env_url:-$db_url}"
    fi
    printf '%s' "$db_url"
}

sha256_file() {
    sha256sum "$1" | awk '{print $1}'
}

validate_pg_dump() {
    local dump_file="$1"
    if [[ ! -s "$dump_file" ]]; then
        return 1
    fi
    pg_restore --list "$dump_file" >/dev/null 2>&1
}

backup_database() {
    local db_url
    db_url="$(load_db_url)"
    if [[ -z "$db_url" ]]; then
        log "  WARNING: DATABASE_URL not set — database backup skipped"
        return 1
    fi

    if [[ "$db_url" == postgresql* ]]; then
        require_command pg_dump || return 1
        local dump_file="$BACKUP_DIR/db.dump"
        log "  Backing up PostgreSQL …"
        if pg_dump -Fc "$db_url" > "$dump_file" 2>/dev/null; then
            if validate_pg_dump "$dump_file"; then
                local size sha
                size=$(stat -c '%s' "$dump_file" 2>/dev/null || echo 0)
                sha=$(sha256_file "$dump_file")
                write_marker "db_backup_meta.json" "{\"path\":\"$dump_file\",\"size\":$size,\"sha256\":\"$sha\",\"valid\":true}"
                return 0
            fi
            log_err "PostgreSQL backup created but validation failed"
            return 1
        fi
        log_err "PostgreSQL backup failed"
        return 1
    elif [[ "$db_url" == sqlite* ]]; then
        local db_file
        db_file=$(echo "$db_url" | sed 's#sqlite:///##')
        if [[ -f "$db_file" ]]; then
            cp "$db_file" "$BACKUP_DIR/db.sqlite"
            local size sha
            size=$(stat -c '%s' "$BACKUP_DIR/db.sqlite" 2>/dev/null || echo 0)
            sha=$(sha256_file "$BACKUP_DIR/db.sqlite")
            write_marker "db_backup_meta.json" "{\"path\":\"$BACKUP_DIR/db.sqlite\",\"size\":$size,\"sha256\":\"$sha\",\"valid\":true}"
            return 0
        fi
    fi
    log_err "Database backup path unsupported or source file missing"
    return 1
}

restore_database() {
    local db_url
    db_url="$(load_db_url)"
    if [[ -f "$BACKUP_DIR/db.dump" ]] && command -v pg_restore >/dev/null 2>&1; then
        log "Restoring PostgreSQL database …"
        if [[ "$db_url" == postgresql* ]]; then
            pg_restore --clean --if-exists -d "$db_url" "$BACKUP_DIR/db.dump" >/dev/null 2>&1 || return 1
            log "PostgreSQL restore done"
            return 0
        fi
    elif [[ -f "$BACKUP_DIR/db.sqlite" ]]; then
        log "Restoring SQLite database …"
        local db_path="${DB_PATH:-$INSTALL_DIR/data/vpnmanager.db}"
        cp "$BACKUP_DIR/db.sqlite" "$db_path"
        log "SQLite restore done"
        return 0
    fi
    return 1
}

scan_startup_logs() {
    local svc
    local since_args=()
    if [[ -n "$STARTUP_LOG_SINCE" ]]; then
        since_args=(--since "$STARTUP_LOG_SINCE")
    fi
    for svc in "$API_SVC" "$WORKER_SVC"; do
        if systemctl cat "$svc" >/dev/null 2>&1; then
            if journalctl -u "$svc" "${since_args[@]}" -n 120 --no-pager 2>/dev/null \
                | grep -E 'CRASH |Traceback|Unhandled exception' >/dev/null; then
                log_err "Critical startup errors detected in journal for $svc"
                return 1
            fi
        fi
    done
    return 0
}

smoke_check() {
    local target_version="$1"
    local port="${API_PORT:-10086}"
    local portal_port="${CLIENT_PORTAL_PORT:-10090}"
    local api_ok=false
    local health_json=""

    log "Smoke check …"

    for i in $(seq 1 15); do
        sleep 2
        health_json=$(curl -sf --max-time 5 "http://localhost:${port}/health?detail=true" 2>/dev/null || true)
        if [[ -n "$health_json" ]]; then
            api_ok=true
            log "  API health endpoint OK (attempt $i)"
            break
        fi
        log "  waiting for API … ($i/15)"
    done
    $api_ok || { log_err "API health check failed after 30s"; return 1; }

    if ! echo "$health_json" | grep -q '"status":"healthy"'; then
        log_err "API health payload not healthy"
        return 1
    fi
    if ! echo "$health_json" | grep -q '"database":"ok"'; then
        log_err "Database health not OK"
        return 1
    fi

    if [[ -n "$target_version" ]]; then
        local current_version=""
        local runtime_root
        runtime_root="$(effective_runtime_root)"
        [[ -f "$runtime_root/VERSION" ]] && current_version=$(cat "$runtime_root/VERSION")
        if [[ "$current_version" != "$target_version" ]]; then
            log_err "VERSION mismatch after update: expected $target_version, got ${current_version:-missing}"
            return 1
        fi
    fi

    local runtime_root
    runtime_root="$(effective_runtime_root)"
    local alembic_bin="$INSTALL_DIR/venv/bin/alembic"
    if [[ -f "$alembic_bin" && -f "$runtime_root/alembic.ini" ]]; then
        cd "$runtime_root"
        local current_rev head_rev
        current_rev=$($alembic_bin current 2>/dev/null | awk '{print $1}' | tail -1 || true)
        head_rev=$($alembic_bin heads 2>/dev/null | awk '{print $1}' | tail -1 || true)
        if [[ -n "$current_rev" && -n "$head_rev" && "$current_rev" != "$head_rev" ]]; then
            log_err "Alembic revision mismatch after update: current=$current_rev head=$head_rev"
            return 1
        fi
    fi

    if systemctl is-enabled "$WORKER_SVC" >/dev/null 2>&1; then
        if ! systemctl is-active --quiet "$WORKER_SVC" 2>/dev/null; then
            log_err "Worker service not active: $WORKER_SVC"
            return 1
        fi
    fi

    if systemctl is-enabled "$PORTAL_SVC" >/dev/null 2>&1; then
        if systemctl is-active --quiet "$PORTAL_SVC" 2>/dev/null; then
            curl -sf --max-time 5 "http://localhost:${portal_port}/health" >/dev/null 2>&1 || log "  WARNING: Client portal /health failed"
        fi
    fi

    scan_startup_logs || return 1

    write_marker "health.json" "$health_json"
    log "Smoke check PASSED"
    return 0
}

rollback_from_backup() {
    write_marker "phase_rollback_started" "$(date --iso-8601=seconds)"
    write_marker "rollback.pid" "$$"

    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_err "Backup dir not found: $BACKUP_DIR"
        return 1
    fi
    if [[ ! -f "$BACKUP_DIR/code.tar.gz" ]]; then
        log_err "Backup archive missing: $BACKUP_DIR/code.tar.gz"
        return 1
    fi

    stop_services || true

    local previous_release_path=""
    if [[ -f "$BACKUP_DIR/previous_release_path" ]]; then
        previous_release_path="$(cat "$BACKUP_DIR/previous_release_path" 2>/dev/null || true)"
    fi
    if [[ -n "$previous_release_path" && -d "$previous_release_path" && -L "$CURRENT_LINK" ]]; then
        log "Restoring current symlink …"
        ln -sfn "$previous_release_path" "$CURRENT_LINK"
        log "Current symlink restored -> $previous_release_path"
    else
        log "Restoring code …"
        tar -xzf "$BACKUP_DIR/code.tar.gz" -C "$INSTALL_DIR" --overwrite
        log "Code restored"
    fi

    if [[ -f "$BACKUP_DIR/dotenv" ]]; then
        log "Restoring .env …"
        cp "$BACKUP_DIR/dotenv" "$INSTALL_DIR/.env"
    fi

    if [[ -f "$BACKUP_DIR/VERSION" ]]; then
        cp "$BACKUP_DIR/VERSION" "$INSTALL_DIR/VERSION"
        log "Restored VERSION: $(cat "$INSTALL_DIR/VERSION")"
    fi
    install_cli_entrypoint

    if [[ -f "$BACKUP_DIR/db.dump" || -f "$BACKUP_DIR/db.sqlite" ]]; then
        if ! restore_database; then
            log_err "Database restore failed"
            return 1
        fi
    fi

    start_services || true
    local rollback_target=""
    [[ -f "$BACKUP_DIR/VERSION" ]] && rollback_target=$(cat "$BACKUP_DIR/VERSION")
    smoke_check "$rollback_target" || return 1

    write_marker "phase_rollback_complete" "$(date --iso-8601=seconds)"
    log "Rollback complete"
    return 0
}

# =============================================================================
# ROLLBACK MODE
# =============================================================================

if [[ "${ROLLBACK:-}" == "1" ]]; then
    log "=== ROLLBACK MODE ==="
    rollback_from_backup || exit 1
    exit 0
fi

# =============================================================================
# UPDATE MODE
# =============================================================================

[[ -n "$UPDATE_PACKAGE" && -f "$UPDATE_PACKAGE" ]] || { log_err "UPDATE_PACKAGE not set or not found: $UPDATE_PACKAGE"; exit 1; }
[[ -n "$BACKUP_DIR" ]] || { log_err "BACKUP_DIR not set"; exit 1; }
[[ -n "$STAGING_DIR" && -d "$STAGING_DIR" ]] || { log_err "STAGING_DIR not set or not found: $STAGING_DIR"; exit 1; }

EXTRACT_DIR="$STAGING_DIR/extracted"
EXTRACT_ROOT="$EXTRACT_DIR"
if [[ -d "$EXTRACT_DIR" ]]; then
    subcount=$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 | wc -l)
    if [[ "$subcount" -eq 1 ]]; then
        first=$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 | head -1)
        if [[ -d "$first" ]]; then
            EXTRACT_ROOT="$first"
        fi
    fi
fi

log "=== UPDATE MODE ==="
log "Package:     $UPDATE_PACKAGE"
log "Install dir: $INSTALL_DIR"
log "Staging dir: $STAGING_DIR"
log "Backup dir:  $BACKUP_DIR"
log "Target ver:  ${TARGET_VERSION:-unknown}"

require_command systemctl
require_command rsync
require_command tar
require_command curl
require_command sha256sum

log "[S0] Preflight checks …"
check_disk_space "$INSTALL_DIR" "$MIN_UPDATE_FREE_MB" "install dir" || exit 1
check_disk_space "$STAGING_DIR" "$MIN_STAGING_FREE_MB" "staging dir" || exit 1
check_disk_space "$BACKUP_DIR" "$MIN_UPDATE_FREE_MB" "backup dir" || exit 1
[[ -d "$EXTRACT_ROOT" ]] || { log_err "Extracted release not found in staging: $EXTRACT_ROOT"; exit 1; }
[[ -f "$EXTRACT_ROOT/VERSION" ]] || { log_err "Extracted VERSION missing"; exit 1; }
[[ -f "$EXTRACT_ROOT/alembic.ini" ]] || { log_err "Extracted alembic.ini missing"; exit 1; }
[[ -d "$EXTRACT_ROOT/src" ]] || { log_err "Extracted src/ missing"; exit 1; }

if [[ -n "$TARGET_VERSION" ]]; then
    extracted_version=$(cat "$EXTRACT_ROOT/VERSION" 2>/dev/null || true)
    [[ "$extracted_version" == "$TARGET_VERSION" ]] || { log_err "Extracted VERSION mismatch: expected $TARGET_VERSION, got ${extracted_version:-missing}"; exit 1; }
fi

if [[ -n "$EXPECTED_PACKAGE_SHA256" ]]; then
    actual_sha=$(sha256_file "$UPDATE_PACKAGE")
    [[ "$actual_sha" == "$EXPECTED_PACKAGE_SHA256" ]] || { log_err "Package SHA256 mismatch in apply script"; exit 1; }
fi
if [[ "$EXPECTED_PACKAGE_SIZE" != "0" ]]; then
    actual_size=$(stat -c '%s' "$UPDATE_PACKAGE" 2>/dev/null || echo 0)
    [[ "$actual_size" == "$EXPECTED_PACKAGE_SIZE" ]] || { log_err "Package size mismatch in apply script: expected $EXPECTED_PACKAGE_SIZE, got $actual_size"; exit 1; }
fi

APPLY_MODE="compat-inplace"
TARGET_RELEASE_DIR="$INSTALL_DIR"
PREVIOUS_RELEASE_PATH=""
if is_versioned_runtime_supported "$EXTRACT_ROOT"; then
    APPLY_MODE="release-layout"
    TARGET_RELEASE_DIR="$RELEASES_DIR/$TARGET_VERSION"
fi

mkdir -p "$BACKUP_DIR"
write_marker "phase_preflight_ok" "$(date --iso-8601=seconds)"

log "[S1] Creating backup …"
[[ -f "$(version_file_for_runtime)" ]] && cp "$(version_file_for_runtime)" "$BACKUP_DIR/VERSION" || echo "0.0.0" > "$BACKUP_DIR/VERSION"
[[ -f "$INSTALL_DIR/.env" ]] && cp "$INSTALL_DIR/.env" "$BACKUP_DIR/dotenv" || true
if [[ "$APPLY_MODE" == "release-layout" ]]; then
    PREVIOUS_RELEASE_PATH="$(prepare_previous_release_path)"
    printf '%s\n' "$PREVIOUS_RELEASE_PATH" > "$BACKUP_DIR/previous_release_path"
    tar -czf "$BACKUP_DIR/code.tar.gz" -C "$PREVIOUS_RELEASE_PATH" .
else
    tar -czf "$BACKUP_DIR/code.tar.gz" \
        -C "$INSTALL_DIR" \
        --exclude='venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='node_modules' \
        --exclude='backups' \
        --exclude='staging' \
        --exclude='update-lock' \
        --exclude='releases' \
        --exclude='shared' \
        --exclude='data' \
        --exclude='.git' \
        .
fi

if [[ "$REQUIRES_MIGRATION" == "true" ]]; then
    log "[S1] Database backup required …"
    if ! backup_database; then
        log_err "Migration required but DB backup failed — aborting before migration"
        exit 1
    fi
else
    backup_database >/dev/null 2>&1 || true
fi
write_marker "phase_backup_complete" "$(date --iso-8601=seconds)"

log "[S2] Applying release files …"
if [[ "$APPLY_MODE" == "release-layout" ]]; then
    rm -rf "$TARGET_RELEASE_DIR"
    mkdir -p "$TARGET_RELEASE_DIR"
    sync_release_tree "$EXTRACT_ROOT" "$TARGET_RELEASE_DIR"
    install_service_units_from_release "$TARGET_RELEASE_DIR"
else
    sync_release_tree "$EXTRACT_ROOT" "$INSTALL_DIR"
fi

if [[ -f "$INSTALL_DIR/venv/bin/pip" && -f "$TARGET_RELEASE_DIR/requirements.txt" ]]; then
    log "[S3] Updating Python dependencies …"
    "$INSTALL_DIR/venv/bin/pip" install -q -r "$TARGET_RELEASE_DIR/requirements.txt" 2>&1 | tail -5 || {
        log_err "Dependency install failed"
        exit 1
    }
fi

if [[ "$REQUIRES_MIGRATION" == "true" ]]; then
    local_alembic="$INSTALL_DIR/venv/bin/alembic"
    if [[ ! -f "$local_alembic" || ! -f "$TARGET_RELEASE_DIR/alembic.ini" ]]; then
        log_err "Migration required but alembic not available"
        exit 1
    fi
    write_marker "phase_migration_started" "$(date --iso-8601=seconds)"
    log "[S4] Running DB migrations …"
    if ! (cd "$TARGET_RELEASE_DIR" && "$local_alembic" upgrade head 2>&1 | tee -a "$STATE_DIR/apply.log"); then
        log_err "Migration failed — starting auto rollback"
        if rollback_from_backup; then
            exit 2
        fi
        exit 1
    fi
    write_marker "phase_migration_complete" "$(date --iso-8601=seconds)"
fi

if [[ "$APPLY_MODE" == "release-layout" ]]; then
    ln -sfn "$TARGET_RELEASE_DIR" "$CURRENT_LINK"
    # Keep $INSTALL_DIR/VERSION in sync with the runtime so external scripts
    # / monitoring that read the install-root file see the truth.
    if [[ -n "$TARGET_VERSION" ]]; then
        printf '%s\n' "$TARGET_VERSION" > "$INSTALL_DIR/VERSION"
    fi
    write_marker "phase_symlink_switched" "release:$TARGET_RELEASE_DIR"
else
    write_marker "phase_symlink_switched" "compat-inplace"
fi
install_cli_entrypoint

if [[ "$REQUIRES_RESTART" == "true" ]]; then
    write_marker "phase_restart_started" "$(date --iso-8601=seconds)"
    stop_services || true
    start_services || true
fi

log "[S5] Post-update health checks …"
if ! smoke_check "$TARGET_VERSION"; then
    log_err "Health checks failed — starting auto rollback"
    if rollback_from_backup; then
        exit 2
    fi
    exit 1
fi
write_marker "phase_health_ok" "$(date --iso-8601=seconds)"
rm -f "$INSTALL_DIR/data/restart_pending" 2>/dev/null || true
log "=== UPDATE COMPLETE ==="
exit 0
