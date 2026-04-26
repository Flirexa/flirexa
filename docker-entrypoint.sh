#!/bin/bash
# VPN Manager — Docker Entrypoint
# Handles first-run setup, migrations, and startup

set -eo pipefail

echo "=== VPN Manager Docker Entrypoint ==="

# Generate .env from template if not exists
if [ ! -f /app/.env ]; then
    echo "Creating .env from template..."
    cp /app/.env.example /app/.env

    # Generate random secret key
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change-this-to-a-random-secret-key/$SECRET/" /app/.env

    # Generate JWT secret
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change-this-to-a-random-secret-key-for-jwt/$JWT_SECRET/" /app/.env

    # Inject LICENSE_KEY from environment if provided
    if [ -n "${LICENSE_KEY:-}" ]; then
        sed -i "s|^LICENSE_KEY=.*|LICENSE_KEY=$LICENSE_KEY|" /app/.env
        sed -i "s|^LICENSE_CHECK_ENABLED=.*|LICENSE_CHECK_ENABLED=true|" /app/.env
        echo "License key configured from environment"
    fi

    echo "Generated .env with random secrets"
fi

# Wait for database
echo "Waiting for database..."
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
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

# Run database migrations (create tables)
echo "Initializing database..."
python3 -c "
from src.database.connection import engine, Base
from src.database.models import *
Base.metadata.create_all(bind=engine)
print('Database tables created')
"

echo "Starting application..."
exec "$@"
