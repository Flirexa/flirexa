#!/bin/bash
set -euo pipefail

APP_DIR="/opt/vpnmanager"
MODE="none"
PORTAL_DOMAIN=""
ADMIN_DOMAIN=""
CERTBOT_EMAIL=""
ENV_FILE=""
API_PORT="10086"
CLIENT_PORTAL_PORT="10090"
NGINX_CONF="/etc/nginx/conf.d/vpnmanager-web.conf"
ACME_ROOT="/var/www/vpnmanager-acme"
SELF_CERT="/etc/ssl/certs/vpnmanager-admin-selfsigned.crt"
SELF_KEY="/etc/ssl/private/vpnmanager-admin-selfsigned.key"

log()  { echo "[WEB] $1"; }
warn() { echo "[WEB][WARN] $1"; }
die()  { echo "[WEB][ERROR] $1" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: bash scripts/configure-web-access.sh \
  --mode none|portal_admin_ip|portal_admin_domain \
  [--portal-domain portal.example.com] \
  [--admin-domain admin.example.com] \
  [--email admin@example.com] \
  [--install-dir /opt/vpnmanager]
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
            --help|-h) usage; exit 0 ;;
            *) die "Unknown option: $1" ;;
        esac
        shift
    done
}

validate_domain() {
    local d="$1"
    [[ "$d" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$ ]]
}

require_root() {
    [[ $EUID -eq 0 ]] || die "Run as root"
}

load_env() {
    if [[ -z "$ENV_FILE" ]]; then
        ENV_FILE="$APP_DIR/.env"
    fi
    [[ -f "$ENV_FILE" ]] || die ".env not found: $ENV_FILE"

    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a

    API_PORT="${API_PORT:-10086}"
    CLIENT_PORTAL_PORT="${CLIENT_PORTAL_PORT:-10090}"
}

detect_public_ip() {
    if [[ -n "${SERVER_ENDPOINT:-}" ]]; then
        echo "$SERVER_ENDPOINT" | cut -d: -f1
        return
    fi
    curl -s --max-time 3 https://ifconfig.me 2>/dev/null \
        || curl -s --max-time 3 https://api.ipify.org 2>/dev/null \
        || hostname -I | awk '{print $1}'
}

update_env_file() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

install_packages() {
    log "Installing nginx/certbot dependencies..."
    apt-get update -qq >/dev/null 2>&1 || true
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx certbot python3-certbot-nginx openssl >/dev/null 2>&1 \
        || die "Failed to install nginx/certbot packages"
    systemctl enable nginx >/dev/null 2>&1 || true
}

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

# Server-block fallback: any 502/503/504 from the upstream API hands off to
# the static page at $APP_DIR/deploy/nginx/maintenance.html. The flag check
# above triggers this same handler explicitly during updates; the error_page
# also catches unplanned upstream failures (API crashed, port not listening).
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

configure_firewall() {
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
        ufw allow 80/tcp comment "VPN Manager HTTP" >/dev/null 2>&1 || true
        ufw allow 443/tcp comment "VPN Manager HTTPS" >/dev/null 2>&1 || true
    fi
}

write_http_bootstrap_config() {
    mkdir -p "$ACME_ROOT"
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name ${PORTAL_DOMAIN};

$(maintenance_error_pages)

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
    }

    location / {
$(maintenance_check_block)
        proxy_pass http://127.0.0.1:${CLIENT_PORTAL_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    if [[ "$MODE" == "portal_admin_domain" ]]; then
        cat >> "$NGINX_CONF" <<EOF

server {
    listen 80;
    server_name ${ADMIN_DOMAIN};

$(maintenance_error_pages)

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
    }

    location / {
$(maintenance_check_block)
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    fi

    nginx -t >/dev/null 2>&1 || die "nginx bootstrap config test failed"
    systemctl restart nginx
}

obtain_letsencrypt() {
    [[ -n "$CERTBOT_EMAIL" ]] || die "Certbot email is required for domain setup"
    local args=(certonly --webroot -w "$ACME_ROOT" --agree-tos --non-interactive --keep-until-expiring -m "$CERTBOT_EMAIL" -d "$PORTAL_DOMAIN")
    if [[ "$MODE" == "portal_admin_domain" ]]; then
        args+=( -d "$ADMIN_DOMAIN" )
    fi
    certbot "${args[@]}" >/tmp/vpnmanager-certbot.log 2>&1 || {
        tail -n 40 /tmp/vpnmanager-certbot.log >&2 || true
        die "certbot failed"
    }
}

generate_self_signed_admin() {
    local cn
    cn="$(detect_public_ip)"
    mkdir -p /etc/ssl/private /etc/ssl/certs
    openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
        -subj "/CN=${cn}" \
        -keyout "$SELF_KEY" \
        -out "$SELF_CERT" >/dev/null 2>&1 || die "Failed to generate self-signed cert"
    chmod 600 "$SELF_KEY"
}

write_final_config() {
    cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name ${PORTAL_DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name ${PORTAL_DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${PORTAL_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${PORTAL_DOMAIN}/privkey.pem;

    client_max_body_size 20m;

$(maintenance_error_pages)

    location / {
$(maintenance_check_block)
        proxy_pass http://127.0.0.1:${CLIENT_PORTAL_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF

    if [[ "$MODE" == "portal_admin_domain" ]]; then
        cat >> "$NGINX_CONF" <<EOF

server {
    listen 80;
    server_name ${ADMIN_DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${ACME_ROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name ${ADMIN_DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${ADMIN_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${ADMIN_DOMAIN}/privkey.pem;

    client_max_body_size 20m;

$(maintenance_error_pages)

    location / {
$(maintenance_check_block)
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF
    elif [[ "$MODE" == "portal_admin_ip" ]]; then
        cat >> "$NGINX_CONF" <<EOF

server {
    listen 443 ssl default_server;
    server_name _;

    ssl_certificate ${SELF_CERT};
    ssl_certificate_key ${SELF_KEY};

    client_max_body_size 20m;

$(maintenance_error_pages)

    location / {
$(maintenance_check_block)
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF
    fi

    nginx -t >/dev/null 2>&1 || die "nginx final config test failed"
    systemctl reload nginx
}

cleanup_web_proxy() {
    rm -f "$NGINX_CONF"
    nginx -t >/dev/null 2>&1 && systemctl reload nginx || true
}

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
    update_env_file "ADMIN_ACCESS_MODE" "raw_ports"
    log "Web access left on raw ports"
}

apply_domain_mode() {
    validate_domain "$PORTAL_DOMAIN" || die "Invalid client portal domain"
    if [[ "$MODE" == "portal_admin_domain" ]]; then
        validate_domain "$ADMIN_DOMAIN" || die "Invalid admin panel domain"
    fi

    install_packages
    configure_firewall
    write_http_bootstrap_config
    obtain_letsencrypt

    if [[ "$MODE" == "portal_admin_ip" ]]; then
        generate_self_signed_admin
    fi

    write_final_config

    update_env_file "WEB_SETUP_MODE" "$MODE"
    update_env_file "CLIENT_PORTAL_DOMAIN" "$PORTAL_DOMAIN"
    update_env_file "CERTBOT_EMAIL" "$CERTBOT_EMAIL"
    update_env_file "CLIENT_PORTAL_URL" "https://${PORTAL_DOMAIN}"

    if [[ "$MODE" == "portal_admin_domain" ]]; then
        update_env_file "ADMIN_PANEL_DOMAIN" "$ADMIN_DOMAIN"
        update_env_file "ADMIN_PANEL_URL" "https://${ADMIN_DOMAIN}"
        update_env_file "ADMIN_ACCESS_MODE" "domain_tls"
    else
        local ip
        ip="$(detect_public_ip)"
        update_env_file "ADMIN_PANEL_DOMAIN" ""
        update_env_file "ADMIN_PANEL_URL" "https://${ip}"
        update_env_file "ADMIN_ACCESS_MODE" "ip_self_signed"
    fi

    log "Web access configured"
}

main() {
    parse_args "$@"
    require_root
    load_env

    case "$MODE" in
        none) apply_mode_none ;;
        portal_admin_ip|portal_admin_domain) apply_domain_mode ;;
        *) die "Unsupported mode: $MODE" ;;
    esac

    log "Client portal URL: $(grep '^CLIENT_PORTAL_URL=' "$ENV_FILE" | cut -d= -f2-)"
    log "Admin panel URL:   $(grep '^ADMIN_PANEL_URL=' "$ENV_FILE" | cut -d= -f2-)"
}

main "$@"
