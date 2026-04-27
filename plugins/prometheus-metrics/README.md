# prometheus-metrics

Community-tier plugin. Exposes Flirexa runtime stats at `/metrics` in Prometheus exposition format so you can scrape them with Prometheus, Grafana Agent, VictoriaMetrics, or anything else that speaks Prometheus.

## What you get

```
# HELP flirexa_uptime_seconds Seconds since the API process started.
# TYPE flirexa_uptime_seconds gauge
flirexa_uptime_seconds 86421.5

# HELP flirexa_clients_total Total VPN clients by status.
# TYPE flirexa_clients_total gauge
flirexa_clients_total{status="active"} 47
flirexa_clients_total{status="disabled"} 3
flirexa_clients_total{status="expired"} 1

# HELP flirexa_servers_total Total VPN servers configured.
# TYPE flirexa_servers_total gauge
flirexa_servers_total 1

# HELP flirexa_traffic_bytes_total Cumulative VPN traffic in bytes by direction.
# TYPE flirexa_traffic_bytes_total counter
flirexa_traffic_bytes_total{direction="up"} 12483922
flirexa_traffic_bytes_total{direction="down"} 89412380
```

Drop these straight into a Grafana dashboard.

## Install

The plugin ships with Flirexa core. It's loaded automatically because its `requires_license_feature` is `community` (always granted). No extra steps needed beyond the optional auth token.

## Configuration

```ini
# Optional. If set, /metrics requires `Authorization: Bearer <token>`.
# If unset, the endpoint is open — protect with a firewall or reverse proxy.
METRICS_AUTH_TOKEN=your-long-random-string
```

## Scraping

```yaml
# prometheus.yml
scrape_configs:
  - job_name: flirexa
    scrape_interval: 30s
    static_configs:
      - targets: ['your-server:10086']
    authorization:
      type: Bearer
      credentials: your-long-random-string  # only if METRICS_AUTH_TOKEN is set
```

## Disable

Just delete the directory (or rename it to start with an underscore — the plugin loader skips underscore-prefixed dirs):

```bash
rm -rf /opt/vpnmanager/current/plugins/prometheus-metrics/
sudo systemctl restart vpnmanager-api
```

## Why this is the reference plugin

This plugin is intentionally written as the canonical example for community-plugin authoring. It demonstrates:

- **Plugin manifest** with `requires_license_feature: "community"`
- **Plugin lifecycle** — `Plugin` subclass with `get_router` and `on_load`
- **FastAPI router** mounted at the root (`/metrics`) and a status route under `/api/v1/plugins/<name>/status`
- **Optional auth** via env var
- **Defensive DB access** — never crashes the endpoint if the DB hiccups
- **Clean shutdown safety** — no module-level state that breaks reload

Copy `plugins/prometheus-metrics/` to `plugins/your-plugin/` and start hacking. See [docs/plugins.md](../../docs/plugins.md) for the full plugin authoring guide.
