# Observability

| Signal | Where | Notes |
|---|---|---|
| Structured logs | stdout (JSON, structlog) | Every line carries `request_id`; clients get it as `X-Request-ID` and in problem responses |
| Metrics | `GET /metrics` on the API container (not proxied publicly) | Route-template labels only; outbox sampled at scrape |
| Dashboards | Grafana, `ops/grafana/dashboards/recallgraph.json` | Traffic, p50/p95 latency, error ratio, outbox, explanation modes |
| Alerts | Prometheus rules, `ops/prometheus/alerts.yml` | API down, 5xx ratio > 5%, p95 > 1 s, dead letters, outbox backlog > 15 min |

Run: `RECALLGRAPH_JWT_SECRET=$(openssl rand -hex 32) make stack-up`, then open Grafana on
127.0.0.1:3000. Alert delivery (Alertmanager/CloudWatch) is wired in the AWS step; locally the
rules are evaluated and visible under Prometheus → Alerts.

Not included (yet): distributed tracing. One API process plus a worker share a database; request
ids already correlate logs across both. Tracing is reconsidered if services are split.
