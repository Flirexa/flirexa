FROM python:3.12-slim AS base

LABEL maintainer="VPN Manager"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wireguard-tools \
    iproute2 \
    iptables \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy and set entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create directories for runtime data
RUN mkdir -p /app/data /app/logs /app/backups

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# NOTE: This container runs as root because WireGuard management requires
# privileged operations: wg (set/show), ip link, iptables, tc (traffic control),
# modprobe (kernel modules). Running as a non-root user would break all
# WireGuard and bandwidth-limiting functionality.
# If you only run the API/portal without WireGuard, consider overriding USER.

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:10090/health || curl -f http://localhost:10086/health || exit 1

# Default: API server
EXPOSE 10086
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "main.py", "api", "--host", "0.0.0.0", "--port", "10086"]
