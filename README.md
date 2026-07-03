# ci-doctor

Self-healing CI/CD pipeline. Classifies CI failures, auto-resolves flaky tests and lint errors, and escalates novel failures with root-cause hypotheses.

## Architecture

Webhook receiver → Classifier (rules + LLM hybrid) → Auto-resolver (re-run / fix / escalate) → Knowledge base + decision log.

Single Docker container, one event at a time. No external dependencies beyond GitHub API.

## Quick Start

```bash
# 1. Set env vars
export GITHUB_TOKEN=ghp_...
export GITHUB_WEBHOOK_SECRET=...

# 2. Start
docker compose up -d

# 3. Configure GitHub webhook
#    Repo Settings > Webhooks > Add webhook
#    Payload URL: https://your-host:8080/webhook
#    Content type: application/json
#    Secret: <GITHUB_WEBHOOK_SECRET>
#    Events: Workflow runs, Issue comments
```

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GITHUB_TOKEN` | Yes | — | PAT with `repo` + `workflow` scopes |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | Webhook secret |
| `MLX_ENDPOINT` | No | `http://localhost:8000` | Local LLM server |
| `CLOUD_API_KEY` | No | — | Deepseek API key |
| `COST_CEILING` | No | `1.00` | Max $ per fix generation |
| `CONFIDENCE_THRESHOLD` | No | `0.90` | Auto-act threshold |
| `PORT` | No | `8080` | Webhook port |

## Commands

```bash
# Report
ci-doctor report --days 7

# Development
make install    # pip install -e .
make test       # pytest
make lint       # ruff check .
make run        # uvicorn --reload
```

## Failure Categories

| Category | Auto-resolve | Action |
|---|---|---|
| flake | confidence >= 0.90 | Re-run job |
| lint | confidence >= 0.90 | Suggest fix |
| build | confidence >= 0.90 | Suggest fix |
| dependency | confidence >= 0.90 | Suggest fix |
| infra_timeout | — | Escalate (configurable) |
| unknown | — | Escalate |

## Correction Flow

Thumbs-down on a ci-doctor comment → bot asks for correct category → user replies → KB updated.
