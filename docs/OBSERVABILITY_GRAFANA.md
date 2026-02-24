# Observability with Grafana OSS

## Stack

- Prometheus: metrics scraping from backend `/metrics`
- Loki: log storage
- Promtail: backend log shipping
- Grafana: dashboards and alerting UI

## Local startup

```bash
cd /var/www/paf-ghl/Virtual-CarHub
docker compose up -d backend prometheus loki promtail grafana
```

URLs:
- Grafana: `http://localhost:3001` (`admin` / `admin`)
- Prometheus: `http://localhost:9090`
- Loki: `http://localhost:3100`

## Metrics emitted

- `vch_http_requests_total{method,path,status_code}`
- `vch_http_request_duration_seconds_bucket{method,path,le}`
- `vch_http_rate_limit_blocks_total{scope}`
- `vch_deal_state_transitions_total{from_state,to_state,actor}`
- `vch_external_sync_errors_total{provider,operation}`

## Environment knobs

- `METRICS_ENABLED=true`
- `METRICS_PATH=/metrics`
- `LOG_FILE_PATH=/var/log/virtual-carhub/backend.log`

## Notes

- Promtail reads backend rotating log files from shared volume `backend_logs`.
- This replaces Datadog-specific setup with an open-source monitoring plane.
