# Operations

## Scheduled Recall Radar cycle
`recallgraph radar cycle` = incremental ingestion (CPSC last two calendar years, full NHTSA
dataset) -> normalization -> radar run. Every stage is idempotent, so the job can be re-run
safely after a failure, and concurrent radar runs are prevented by a PostgreSQL advisory lock
(`status: skipped`).

Local schedule (daily 06:15), e.g. with cron:
```
15 6 * * * cd ~/Desktop/recallgraph/backend && /opt/homebrew/bin/uv run recallgraph radar cycle >> /tmp/recallgraph-radar.log 2>&1
```
In AWS (Step 28) the same command runs as an ECS scheduled task (EventBridge Scheduler).
