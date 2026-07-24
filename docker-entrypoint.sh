#!/bin/bash
# Flirexa — Docker entrypoint
# Validates configuration, optionally runs migrations, and starts the service.

set -eo pipefail

echo "=== Flirexa Docker Entrypoint ==="

require_secret() {
    local name="$1"
    local value="${!name:-}"
    case "$value" in
        ""|CHANGE_ME|change-this-to-*)
            echo "ERROR: $name is unset or still uses the example value." >&2
            echo "Generate it in the host .env before starting Docker Compose." >&2
            exit 1
            ;;
    esac
}

require_secret SECRET_KEY
require_secret JWT_SECRET
require_secret SERVICE_API_TOKEN
require_secret VMS_ENCRYPTION_KEY

# Wait for database
echo "Waiting for database..."
database_ready=false
for i in $(seq 1 30); do
    if python3 -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
    conn.close()
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
        echo "Database ready"
        database_ready=true
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

if [ "$database_ready" != "true" ]; then
    echo "ERROR: database did not become ready within 60 seconds." >&2
    exit 1
fi

if [ "${MIGRATE_ON_STARTUP:-false}" = "true" ]; then
    echo "Applying database migrations..."
    alembic upgrade head
fi

echo "Starting application..."
exec "$@"
