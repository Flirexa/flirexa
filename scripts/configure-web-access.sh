#!/bin/bash
# configure-web-access.sh — provision nginx + Let's Encrypt for Flirexa.
#
# Modes:
#   none                  → strip any web-access nginx config; expose raw ports.
#   portal_admin_ip       → client portal on a real domain (HTTPS),
#                           admin panel on the public IP (self-signed HTTPS).
#   portal_admin_domain   → both portal and admin on real domains, both with
#                           Let's Encrypt certs.
#   auto_selfsigned_ip    → no domain needed. Self-signed cert on this
#                           server's public IP for BOTH the portal (port 443)
#                           and the admin panel (port 10086). HTTP :80
#                           redirects to https. Useful for fresh installs run
#                           without a tty (curl | bash) — operator wires up a
#                           real domain via this same script later.
#
# Highlights:
#   • DNS pre-check vs server's public IP — fails fast with a clear message
#     instead of a cryptic Let's Encrypt timeout.
#   • Port 80/443 conflict pre-check — refuses to clobber a foreign listener.
#   • Email syntax validation before burning an LE rate-limit attempt.
#   • Optional --staging flag for unlimited test issuance.
#   • Modern TLS posture: TLS 1.2/1.3 only, Mozilla-intermediate cipher list,
#     OCSP stapling, session cache, HSTS, gzip, sane security headers.
#   • HTTP/2 enabled by default.
#   • proxy_read_timeout raised to 300s so long admin operations don't 504.
#   • certbot.timer explicitly enabled — auto-renew survives an opinionated
#     systemd-aware operator who might have masked the timer.
#   • Idempotent: a re-run with the same arguments is a no-op past the cert
#     check; an aborted run leaves nginx in a valid bootstrap state.
set -euo pipefail

APP_DIR="/opt/vpnmanager"
MODE="none"
PORTAL_DOMAIN=""
ADMIN_DOMAIN=""
CERTBOT_EMAIL=""
ENV_FILE=""
USE_STAGING=0
API_PORT="10086"
CLIENT_PORTAL_PORT="10090"
NGINX_CONF="/etc/nginx/conf.d/vpnmanager-web.conf"
NGINX_TLS_PARAMS="/etc/nginx/conf.d/vpnmanager-tls-params.conf"
ACME_ROOT="/var/www/vpnmanager-acme"
SELF_CERT="/etc/ssl/certs/vpnmanager-admin-selfsigned.crt"
SELF_KEY="/etc/ssl/private/vpnmanager-admin-selfsigned.key"
DHPARAM="/etc/ssl/certs/vpnmanager-dhparam.pem"

log()  { echo "[WEB] $1"; }
warn() { echo "[WEB][WARN] $1"; }
die()  { echo "[WEB][ERROR] $1" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: bash scripts/configure-web-access.sh \\
  --mode none|portal_admin_ip|portal_admin_domain|auto_selfsigned_ip \\
  [--portal-domain portal.example.com] \\
  [--admin-domain admin.example.com] \\
  [--email admin@example.com] \\
  [--install-dir /opt/vpnmanager] \\
  [--env-file PATH] \\
  [--staging]
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --mode) MODE="$2"; shift ;;
            --portal-domain) PORTAL_DOMAIN="$2"; shift ;;
            --admin-domain) ADMIN_DOMAIN="$2"; shift ;;
            --email) CERTBOT_EMAIL="$2"; shift ;;
            --install-dir) APP_DIR="$2"; shift ;;
            --env-file) ENV_FILE="$2"; shift ;;
            --staging) USE_STAGING=1 ;;
            --help|-h) usage; exit 0 ;;
            *) die "Unknown option: $1" ;;
        esac
        shift
    done
}

# ── Validators ───────────────────────────────────────────────────────────────

validate_domain() {
    local d="$1"
    # 1-63 chars per label, total ≤ 253, TLD ≥ 2 alphas.
    [[ ${#d} -le 253 ]] || return 1
    [[ "$d" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]
}

validate_email() {
    local e="$1"
    # Pragmatic regex — good enough to catch typos and missing @, not RFC-perfect.
    [[ "$e" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$ ]]
}

require_root() {
    [[ $EUID -eq 0 ]] || die "Run as root"
}

load_env() {
    if [[ -z "$ENV_FILE" ]]; then
        ENV_FILE="$APP_DIR/.env"
    fi
    [[ -f "$ENV_FILE" ]] || die ".env not found: $ENV_FILE"

    # Save CLI-supplied values BEFORE sourcing — `set -a; . file` would
    # otherwise overwrite them with .env's (often empty) values, silently
    # discarding what the operator just typed on the command line.
    local cli_email="$CERTBOT_EMAIL"
    local cli_portal="$PORTAL_DOMAIN"
    local cli_admin="$ADMIN_DOMAIN"

    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a

    # CLI args take precedence over .env. Only fall back to .env when the
    # CLI didn't supply a value.
    [[ -n "$cli_email"  ]] && CERTBOT_EMAIL="$cli_email"
    [[ -n "$cli_portal" ]] && PORTAL_DOMAIN="$cli_portal"
    [[ -n "$cli_admin"  ]] && ADMIN_DOMAIN="$cli_admin"

    API_PORT="${API_PORT:-10086}"
    CLIENT_PORTAL_PORT="${CLIENT_PORTAL_PORT:-10090}"
}

# ── Network discovery ────────────────────────────────────────────────────────

detect_public_ip() {
    if [[ -n "${SERVER_ENDPOINT:-}" ]]; then
        echo "$SERVER_ENDPOINT" | cut -d: -f1
        return
    fi
    curl -s --max-time 3 https://ifconfig.me 2>/dev/null \
        || curl -s --max-time 3 https://api.ipify.org 2>/dev/null \
        || hostname -I | awk '{print $1}'
}

# Resolve a domain via the system resolver and emit each A record on its own
# line. Tries `getent` first (respects /etc/hosts overrides), falls back to
# `dig` for environments where getent times out on slow DNS.
resolve_domain() {
    local d="$1"
    if command -v getent >/dev/null 2>&1; then
        getent ahostsv4 "$d" 2>/dev/null | awk '{print $1}' | sort -u | head -10
        return
    fi
    if command -v dig >/dev/null 2>&1; then
        dig +short +time=2 +tries=2 A "$d" 2>/dev/null | sort -u | head -10
        return
    fi
    echo ""
}

dns_precheck() {
    local domain="$1"
    local server_ip="$2"
    local resolved
    resolved="$(resolve_domain "$domain")"
    if [[ -z "$resolved" ]]; then
        die "DNS lookup for $domain returned nothing — set an A record pointing to ${server_ip} and retry."
    fi
    # If ANY resolved IP matches our public IP, we're good (round-robin etc.).
    if echo "$resolved" | grep -qx "$server_ip"; then
        return 0
    fi
    local first
    first="$(echo "$resolved" | head -1)"
    die "$domain resolves to ${first} but this server is ${server_ip}. \
Fix DNS (A record → ${server_ip}) and retry. DNS can take up to 30 minutes to propagate."
}

# Refuse to clobber a foreign listener on port 80/443. nginx (already part of
# this script) is fine — anything else (Caddy, Apache, a docker container
# bound to the host) is not.
port_conflict_check() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        local owner
        owner="$(ss -tlnpH "sport = :${port}" 2>/dev/null | awk 'NR==1{print $NF}')"
        if [[ -n "$owner" && "$owner" != *nginx* ]]; then
            die "Port ${port} is already in use by: ${owner}. Stop that service or pick another setup."
        fi
    fi
}

# ── .env writer with file lock (avoids concurrent corruption) ────────────────

update_env_file() {
    local key="$1"
    local value="$2"
    local lockfile="${ENV_FILE}.lock"
    (
        # Wait up to 5s for an exclusive lock on the .env file. The Python
        # /api side uses fcntl.flock on the same path, so this gives mutual
        # exclusion between shell and Python writers.
        exec 9>"$lockfile"
        flock -x -w 5 9 || die "Could not acquire .env lock"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
        else
            echo "${key}=${value}" >> "$ENV_FILE"
        fi
    )
}

# ── Package install ──────────────────────────────────────────────────────────

install_packages() {
    log "Installing nginx/certbot dependencies..."
    apt-get update -qq >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        nginx certbot python3-certbot-nginx openssl >/dev/null 2>&1 \
        || die "Failed to install nginx/certbot packages"
    systemctl enable nginx >/dev/null 2>&1 || true
}

# Generate a valid 2048-bit DH group once. Write through a temporary file so a
# killed/failed openssl process cannot leave a partial file that later runs
# mistake for a completed setup.
ensure_dhparam() {
    if [[ -s "$DHPARAM" ]] && \
       openssl dhparam -in "$DHPARAM" -check -noout >/dev/null 2>&1; then
        chmod 644 "$DHPARAM"
        return
    fi

    local dhparam_dir dhparam_tmp
    dhparam_dir="$(dirname "$DHPARAM")"
    mkdir -p "$dhparam_dir"
    dhparam_tmp="$(mktemp "${DHPARAM}.tmp.XXXXXX")" \
        || die "Failed to create temporary DH parameter file"

    log "Generating DH parameters (2048-bit, one-time, ~30s)..."
    if ! openssl dhparam -out "$dhparam_tmp" 2048 >/dev/null 2>&1 || \
       ! openssl dhparam -in "$dhparam_tmp" -check -noout >/dev/null 2>&1; then
        rm -f -- "$dhparam_tmp"
        die "Failed to generate valid DH parameters"
    fi
    chmod 644 "$dhparam_tmp"
    if ! mv -f -- "$dhparam_tmp" "$DHPARAM"; then
        rm -f -- "$dhparam_tmp"
        die "Failed to install DH parameters"
    fi
}

configure_firewall() {
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
        ufw allow 80/tcp comment "Flirexa HTTP" >/dev/null 2>&1 || true
        ufw allow 443/tcp comment "Flirexa HTTPS" >/dev/null 2>&1 || true
    fi
}

# ── nginx config fragments ───────────────────────────────────────────────────

# Inserted inside each `location /` proxy block — short-circuits to the static
# maintenance page when update_apply.sh has touched the flag, so users see a
# friendly "Updating, back in a moment" page instead of nginx 502.
maintenance_check_block() {
    cat <<EOF
        if (-f ${APP_DIR}/data/maintenance.flag) {
            return 503;
        }
EOF
}

maintenance_error_pages() {
    cat <<EOF
    error_page 502 503 504 = @maintenance;
    location @maintenance {
        root ${APP_DIR}/deploy/nginx;
        try_files /maintenance.html =503;
        internal;
        add_header Retry-After 30 always;
    }
EOF
}

proxy_headers_block() {
    # Shared block injected into every proxy `location` so the upstream sees
    # the real client. proxy_read_timeout is bumped to 300s so long admin
    # operations (full database backup, mass user import) don't 504.
    cat <<EOF
        proxy_pass http://127.0.0.1:${1};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_connect_timeout 30s;
        proxy_buffering off;
EOF
}

security_headers_block() {
    # Modern security headers. HSTS only inside HTTPS server blocks (sending
    # it over HTTP is a no-op and risky for accidental http-only setups).
    cat <<EOF
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
EOF
}

write_tls_params() {
    # Ubuntu's default /etc/nginx/nginx.conf already sets `gzip on`,
    # `ssl_protocols`, `ssl_prefer_server_ciphers`, and `server_tokens`
    # at the http scope. Re-declaring any of those here trips
    # "duplicate directive" errors. We keep our overrides inside each
    # `server { }` block via tls_directives_block() and
    # gzip_overrides_block() — that way they're idempotent regardless
    # of what the distro nginx.conf has set.
    cat > "$NGINX_TLS_PARAMS" <<EOF
# Managed by configure-web-access.sh — intentionally minimal.
# TLS/gzip overrides live inside each server block.
EOF
    log "Wrote TLS params at $NGINX_TLS_PARAMS"
}

tls_directives_block() {
    # Per-server-block TLS settings. Safe to repeat across multiple server
    # blocks — nginx scopes them per-block when declared here. Mozilla
    # Intermediate snapshot, 2026 baseline.
    cat <<EOF
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_dhparam ${DHPARAM};

    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 1.1.1.1 8.8.8.8 valid=300s;
    resolver_timeout 5s;
EOF
}

gzip_overrides_block() {
    # Per-server-block gzip tweaks. Doesn't redeclare `gzip on` (Ubuntu's
    # default nginx.conf already turns it on at http scope, which would
    # trip a duplicate-directive error if we set it here too). We only
    # tune the parameters that improve the panel's payload.
    cat <<EOF
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 256;
    gzip_types
        application/atom+xml application/geo+json application/javascript
        application/x-javascript application/json application/ld+json
        application/manifest+json application/rdf+xml application/rss+xml
        application/xhtml+xml application/xml font/eot font/otf font/ttf
        image/svg+xml text/css text/javascript text/plain text/xml;
EOF
}

write_http_bootstrap_config() {
    mkdir -p "$ACME_ROOT"
    chown www-data:www-data "$ACME_ROOT" 2>/dev/null || true

    {
        cat <<EOF
# HTTP bootstrap — listens on :80 just long enough for certbot to complete the
# webroot challenge. write_final_config() replaces this with a HTTPS-fronted
# version once Let's Encrypt has issued a cert.
server {
    listen 80;
    listen [::]:80;
    server_name ${PORTAL_DOMAIN};

$(maintenance_error_pages)

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${CLIENT_PORTAL_PORT}")
    }
}
EOF
        if [[ "$MODE" == "portal_admin_domain" ]]; then
            cat <<EOF

server {
    listen 80;
    listen [::]:80;
    server_name ${ADMIN_DOMAIN};

$(maintenance_error_pages)

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${API_PORT}")
    }
}
EOF
        fi
    } > "$NGINX_CONF"

    nginx -t >/dev/null 2>&1 || die "nginx bootstrap config test failed"
    systemctl restart nginx
}

obtain_letsencrypt() {
    [[ -n "$CERTBOT_EMAIL" ]] || die "Certbot email is required for domain setup"

    local args=(certonly --webroot -w "$ACME_ROOT"
                --agree-tos --non-interactive --keep-until-expiring
                -m "$CERTBOT_EMAIL"
                --rsa-key-size 2048
                -d "$PORTAL_DOMAIN")
    if [[ "$MODE" == "portal_admin_domain" ]]; then
        args+=( -d "$ADMIN_DOMAIN" )
    fi
    if [[ "$USE_STAGING" -eq 1 ]]; then
        args+=( --staging )
        log "Using Let's Encrypt staging endpoint (test certs, not browser-trusted)"
    fi

    log "Requesting certificate from Let's Encrypt..."
    if ! certbot "${args[@]}" >/tmp/vpnmanager-certbot.log 2>&1; then
        warn "certbot failed — last 40 lines of /tmp/vpnmanager-certbot.log:"
        tail -n 40 /tmp/vpnmanager-certbot.log >&2 || true
        die "certbot failed — see /tmp/vpnmanager-certbot.log for the full trace"
    fi
    log "Certificate issued."
}

# Make sure certbot's auto-renew systemd timer is active. Debian/Ubuntu ship
# the timer in the certbot package and enable it by default, but an operator
# might have masked or disabled it — defensive `enable --now` makes sure
# auto-renew survives until the cert's 90-day expiry.
ensure_renewal_timer() {
    if systemctl list-unit-files 2>/dev/null | grep -q '^certbot.timer'; then
        systemctl unmask certbot.timer >/dev/null 2>&1 || true
        systemctl enable --now certbot.timer >/dev/null 2>&1 \
            || warn "Could not enable certbot.timer — auto-renew may be disabled"
        log "Auto-renew: certbot.timer is active"
    else
        warn "certbot.timer not present — auto-renew may need manual setup"
    fi
}

generate_self_signed_admin() {
    local cn
    cn="$(detect_public_ip)"
    [[ -n "$cn" ]] || die "Could not detect public IP for self-signed cert"
    mkdir -p /etc/ssl/private /etc/ssl/certs
    # SAN=IP:<addr> is required by Chrome/Edge — they reject certs that
    # only put the IP in the CN. 1825 days because the 825-day cap is a
    # Safari rule for PUBLICLY trusted certs; self-signed is already
    # warning-on-every-load, no point making operators regenerate yearly.
    openssl req -x509 -nodes -newkey rsa:2048 -days 1825 \
        -subj "/CN=${cn}" \
        -addext "subjectAltName=IP:${cn}" \
        -keyout "$SELF_KEY" \
        -out "$SELF_CERT" >/dev/null 2>&1 || die "Failed to generate self-signed cert"
    chmod 600 "$SELF_KEY"
}


apply_selfsigned_ip_mode() {
    # No domain, no Let's Encrypt — self-signed cert bound to this server's
    # public IP, used for BOTH the portal (port 443) and the admin panel
    # (port 10086). Lets a fresh `curl | bash` install end with the panel
    # immediately reachable over HTTPS so the operator can log in and
    # configure their real domain via this same script later.
    local ip
    install_packages
    port_conflict_check 80
    port_conflict_check 443
    ip="$(detect_public_ip)"
    [[ -n "$ip" ]] || die "Could not determine this server's public IP"
    log "Self-signed mode — binding both panels to ${ip}"

    configure_firewall
    generate_self_signed_admin

    # Make sure backends are loopback-only. nginx in front of them is the
    # only public listener; if the python services still answered on the
    # public interface the panel would have both an :10086 nginx HTTPS and
    # a :10087 plain-HTTP backdoor, which is exactly what operators don't
    # want when they're operating customer data.
    update_env_value() {
        local key="$1" value="$2"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
        else
            echo "${key}=${value}" >> "$ENV_FILE"
        fi
    }
    update_env_value "API_HOST"           "127.0.0.1"
    # Move api to 10087 so nginx can take 10086. The api-port value also
    # propagates to ADMIN_API_URL below.
    update_env_value "API_PORT"           "10087"
    update_env_value "CLIENT_PORTAL_HOST" "127.0.0.1"
    update_env_value "CLIENT_PORTAL_PORT" "10090"

    # Refresh local vars so the nginx config below renders the new port.
    API_PORT="10087"
    CLIENT_PORTAL_PORT="10090"

    # Drop the stock /etc/nginx/sites-enabled/default — it owns :80 with
    # default_server and conflicts with the :80 redirect server we write
    # below. Idempotent.
    rm -f /etc/nginx/sites-enabled/default

    # Generate the DH params the TLS server blocks reference via ssl_dhparam.
    # Without this the nginx config written below fails `nginx -t` and :443
    # never binds — the panel is then reachable on :80 only (or not at all),
    # which looks like "HTTPS down while services are up". Only apply_domain_mode
    # used to call this; the self-signed path (the default for non-interactive
    # installs) skipped it. See the dhparam install-bug fix.
    ensure_dhparam

    write_tls_params

    cat > "$NGINX_CONF" <<EOF
# Managed by configure-web-access.sh (auto_selfsigned_ip mode). Do not edit
# by hand — re-run the script to refresh. Self-signed cert at:
#   ${SELF_CERT}
#   ${SELF_KEY}

# ── HTTP → HTTPS redirect (catches operators who paste the IP without https) ──
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://\$host\$request_uri;
}

# ── Client portal: HTTPS on the public IP ─────────────────────────────────────
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name _;

    ssl_certificate     ${SELF_CERT};
    ssl_certificate_key ${SELF_KEY};

$(tls_directives_block)
$(gzip_overrides_block)

    client_max_body_size 20m;

$(security_headers_block)
$(maintenance_error_pages)

    access_log /var/log/nginx/portal-access.log;
    error_log  /var/log/nginx/portal-error.log;

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${CLIENT_PORTAL_PORT}")
    }
}

# ── Admin panel: HTTPS on the public IP (port 10086) ──────────────────────────
server {
    listen 10086 ssl http2;
    listen [::]:10086 ssl http2;
    server_name _;

    ssl_certificate     ${SELF_CERT};
    ssl_certificate_key ${SELF_KEY};

$(tls_directives_block)
$(gzip_overrides_block)

    client_max_body_size 20m;

$(security_headers_block)
$(maintenance_error_pages)

    access_log /var/log/nginx/admin-access.log;
    error_log  /var/log/nginx/admin-error.log;

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${API_PORT}")
    }
}
EOF

    nginx -t >/dev/null 2>&1 || die "nginx config test failed (auto_selfsigned_ip)"
    systemctl enable nginx >/dev/null 2>&1 || true
    systemctl reload nginx 2>/dev/null || systemctl restart nginx

    # The python services were bound to 0.0.0.0:10086 / 0.0.0.0:10090 by
    # whatever ran before us. Bounce them so they pick up the new env.
    if systemctl is-enabled vpnmanager-api >/dev/null 2>&1; then
        systemctl restart vpnmanager-api          2>/dev/null || true
    fi
    if systemctl is-enabled vpnmanager-client-portal >/dev/null 2>&1; then
        systemctl restart vpnmanager-client-portal 2>/dev/null || true
    fi

    update_env_value "WEB_SETUP_MODE"      "auto_selfsigned_ip"
    update_env_value "CLIENT_PORTAL_DOMAIN" ""
    update_env_value "ADMIN_PANEL_DOMAIN"   ""
    update_env_value "CERTBOT_EMAIL"        ""
    update_env_value "CLIENT_PORTAL_URL"   "https://${ip}"
    update_env_value "ADMIN_PANEL_URL"     "https://${ip}:10086"
    # Internal URL the portal process uses to call the admin process.
    # Loopback HTTP — never https://, never the public IP, because TLS
    # to ourselves through nginx adds latency and the self-signed cert
    # would fail verification inside python httpx without verify=False.
    update_env_value "ADMIN_API_URL"       "http://127.0.0.1:${API_PORT}"
    update_env_value "ADMIN_ACCESS_MODE"   "selfsigned_ip"
    log "Web access configured (self-signed cert on ${ip})"
}

write_final_config() {
    {
        cat <<EOF
# Managed by configure-web-access.sh — do not edit by hand.

# ── Client portal: HTTP → HTTPS redirect ─────────────────────────
server {
    listen 80;
    listen [::]:80;
    server_name ${PORTAL_DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# ── Client portal: HTTPS ─────────────────────────────────────────
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${PORTAL_DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${PORTAL_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${PORTAL_DOMAIN}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/${PORTAL_DOMAIN}/chain.pem;

$(tls_directives_block)
$(gzip_overrides_block)

    client_max_body_size 20m;

$(security_headers_block)
$(maintenance_error_pages)

    access_log /var/log/nginx/portal-access.log;
    error_log  /var/log/nginx/portal-error.log;

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${CLIENT_PORTAL_PORT}")
    }
}
EOF

        if [[ "$MODE" == "portal_admin_domain" ]]; then
            cat <<EOF

# ── Admin panel: HTTP → HTTPS redirect ───────────────────────────
server {
    listen 80;
    listen [::]:80;
    server_name ${ADMIN_DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
        default_type "text/plain";
        try_files \$uri =404;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

# ── Admin panel: HTTPS ───────────────────────────────────────────
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${ADMIN_DOMAIN};

    ssl_certificate     /etc/letsencrypt/live/${ADMIN_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${ADMIN_DOMAIN}/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/${ADMIN_DOMAIN}/chain.pem;

$(tls_directives_block)
$(gzip_overrides_block)

    client_max_body_size 20m;

$(security_headers_block)
$(maintenance_error_pages)

    access_log /var/log/nginx/admin-access.log;
    error_log  /var/log/nginx/admin-error.log;

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${API_PORT}")
    }
}
EOF
        elif [[ "$MODE" == "portal_admin_ip" ]]; then
            cat <<EOF

# ── Admin panel: HTTPS via self-signed cert on the public IP ─────
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name _;

    ssl_certificate     ${SELF_CERT};
    ssl_certificate_key ${SELF_KEY};

$(tls_directives_block)
$(gzip_overrides_block)

    client_max_body_size 20m;

$(security_headers_block)
$(maintenance_error_pages)

    access_log /var/log/nginx/admin-access.log;
    error_log  /var/log/nginx/admin-error.log;

    location / {
$(maintenance_check_block)
$(proxy_headers_block "${API_PORT}")
    }
}
EOF
        fi
    } > "$NGINX_CONF"

    nginx -t >/dev/null 2>&1 || die "nginx final config test failed"
    systemctl reload nginx
}

cleanup_web_proxy() {
    rm -f "$NGINX_CONF" "$NGINX_TLS_PARAMS"
    # Best-effort reload: if nginx isn't installed or the test fails, swallow
    # the error — `none` mode shouldn't fail just because there's no nginx.
    if nginx -t >/dev/null 2>&1; then
        systemctl reload nginx >/dev/null 2>&1 || true
    fi
}

# ── Mode dispatchers ─────────────────────────────────────────────────────────

apply_mode_none() {
    local ip
    ip="$(detect_public_ip)"
    cleanup_web_proxy
    update_env_file "WEB_SETUP_MODE" "none"
    update_env_file "CLIENT_PORTAL_DOMAIN" ""
    update_env_file "ADMIN_PANEL_DOMAIN" ""
    update_env_file "CERTBOT_EMAIL" ""
    update_env_file "CLIENT_PORTAL_URL" "http://${ip}:${CLIENT_PORTAL_PORT}"
    update_env_file "ADMIN_PANEL_URL" "http://${ip}:${API_PORT}"
    # Internal URL the portal process uses to call the admin process —
    # MUST stay on the plain-HTTP API port (never nginx HTTPS), otherwise
    # GET /clients/by-ids 400s with "plain HTTP request sent to HTTPS port"
    # and the portal silently shows zero devices.
    update_env_file "ADMIN_API_URL" "http://localhost:${API_PORT}"
    update_env_file "ADMIN_ACCESS_MODE" "raw_ports"
    log "Web access left on raw ports"
}

apply_domain_mode() {
    # ── Validation ───────────────────────────────────────────────
    validate_domain "$PORTAL_DOMAIN" || die "Invalid client portal domain: ${PORTAL_DOMAIN}"
    if [[ "$MODE" == "portal_admin_domain" ]]; then
        validate_domain "$ADMIN_DOMAIN" || die "Invalid admin panel domain: ${ADMIN_DOMAIN}"
        [[ "$PORTAL_DOMAIN" != "$ADMIN_DOMAIN" ]] \
            || die "Portal and admin domains must differ"
    fi
    validate_email "$CERTBOT_EMAIL" || die "Invalid email: ${CERTBOT_EMAIL}"

    # ── Install (idempotent) ─────────────────────────────────────
    install_packages

    # ── Port conflict check (after install, before bind) ─────────
    port_conflict_check 80
    port_conflict_check 443

    # ── DNS preflight ────────────────────────────────────────────
    local server_ip
    server_ip="$(detect_public_ip)"
    [[ -n "$server_ip" ]] || die "Could not determine this server's public IP"
    log "This server's public IP: ${server_ip}"

    dns_precheck "$PORTAL_DOMAIN" "$server_ip"
    log "DNS OK: ${PORTAL_DOMAIN} → ${server_ip}"
    if [[ "$MODE" == "portal_admin_domain" ]]; then
        dns_precheck "$ADMIN_DOMAIN" "$server_ip"
        log "DNS OK: ${ADMIN_DOMAIN} → ${server_ip}"
    fi

    # ── nginx + TLS plumbing ─────────────────────────────────────
    configure_firewall
    ensure_dhparam
    write_tls_params
    write_http_bootstrap_config

    # ── Certificate ──────────────────────────────────────────────
    obtain_letsencrypt

    if [[ "$MODE" == "portal_admin_ip" ]]; then
        generate_self_signed_admin
    fi

    write_final_config
    ensure_renewal_timer

    # ── Update .env ──────────────────────────────────────────────
    update_env_file "WEB_SETUP_MODE" "$MODE"
    update_env_file "CLIENT_PORTAL_DOMAIN" "$PORTAL_DOMAIN"
    update_env_file "CERTBOT_EMAIL" "$CERTBOT_EMAIL"
    update_env_file "CLIENT_PORTAL_URL" "https://${PORTAL_DOMAIN}"

    if [[ "$MODE" == "portal_admin_domain" ]]; then
        update_env_file "ADMIN_PANEL_DOMAIN" "$ADMIN_DOMAIN"
        update_env_file "ADMIN_PANEL_URL" "https://${ADMIN_DOMAIN}"
        update_env_file "ADMIN_ACCESS_MODE" "domain_tls"
    else
        update_env_file "ADMIN_PANEL_DOMAIN" ""
        update_env_file "ADMIN_PANEL_URL" "https://${server_ip}"
        update_env_file "ADMIN_ACCESS_MODE" "ip_self_signed"
    fi

    # Internal URL for portal→admin RPC. Always plain HTTP at the API port —
    # see apply_mode_none for the rationale (nginx HTTPS on the public port
    # rejects plain HTTP and the portal then silently shows zero devices).
    update_env_file "ADMIN_API_URL" "http://localhost:${API_PORT}"

    log "Web access configured"
}

main() {
    parse_args "$@"
    require_root
    load_env

    case "$MODE" in
        none) apply_mode_none ;;
        portal_admin_ip|portal_admin_domain) apply_domain_mode ;;
        auto_selfsigned_ip) apply_selfsigned_ip_mode ;;
        *) die "Unsupported mode: $MODE" ;;
    esac

    log "Client portal URL: $(grep '^CLIENT_PORTAL_URL=' "$ENV_FILE" | cut -d= -f2-)"
    log "Admin panel URL:   $(grep '^ADMIN_PANEL_URL=' "$ENV_FILE" | cut -d= -f2-)"
}

main "$@"
