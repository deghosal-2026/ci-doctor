# ci-doctor User Guide

## Setup

### 1. Create a GitHub Personal Access Token

Settings > Developer settings > Personal access tokens > Fine-grained tokens.
Scopes: `Actions: Read`, `Checks: Read & Write`, `Contents: Read`, `Issues: Read & Write`, `Pull requests: Read & Write`, `Metadata: Read`.

### 2. Configure Webhook

Repo Settings > Webhooks > Add webhook:
- Payload URL: `https://your-server:8080/webhook`
- Content type: `application/json`
- Secret: any value (must match `GITHUB_WEBHOOK_SECRET` env var)
- Events: select "Workflow runs" and "Issue comments"

### 3. Deploy

```bash
docker compose up -d
```

### 4. Verify

```bash
curl http://localhost:8080/health
# {"status": "ok"}
```

## Editing Rules

The `rules.yaml` file contains regex patterns for failure classification:

```yaml
rules:
  - category: flake
    patterns:
      - "FAILED.*re-run"
      - "flaky test"
    confidence: 0.95
```

Add new patterns, adjust confidence thresholds, or add new categories. Restart the container after changes.

## Correcting Misclassifications

When ci-doctor posts a diagnosis, you can correct it:
1. React with thumbs-down on the diagnosis comment
2. ci-doctor replies asking for the correct category
3. Reply with one of: flake, lint, build, dependency, infra_timeout
4. The knowledge base updates and future similar failures use the corrected category

## Running Reports

```bash
ci-doctor report --days 7
ci-doctor report --days 30
ci-doctor report --days 7 --decisions-path /custom/path/decisions.yaml
```

Output is Markdown to stdout. Redirect to a file or pipe to your preferred tool.
