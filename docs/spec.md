# Technical Spec — ci-doctor (CI-Agent)

> Implementation details for the v1 self-healing CI/CD pipeline. See [`prd.md`](./prd.md) for the why and what.

**Status:** Complete — 2026-07-01

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 |
| Web framework | FastAPI (webhook receiver + health endpoint) |
| Async | asyncio (queue + single worker coroutine) |
| GitHub API | httpx (async HTTP client) |
| LLM client | httpx (OpenAI-compatible REST to MLX + Deepseek) |
| KB + decisions | PyYAML (read/write YAML files) |
| CLI | Click (report generation) |
| Tests | pytest + pytest-asyncio |
| Lint | ruff |
| Packaging | Docker (single image) |

## Project Structure

```
ci-doctor/
  app/
    __init__.py
    main.py              # FastAPI app: webhook receiver + health endpoint
    config.py            # env var loading + validation
    webhook/
      __init__.py
      receiver.py        # POST /webhook — routes workflow_run + reaction events
      verifier.py        # GitHub signature verification (HMAC-SHA256)
      dedup.py           # in-memory event ID set
    worker/
      __init__.py
      queue.py           # asyncio.Queue + single worker coroutine
      processor.py       # event → classify → act → log
    classifier/
      __init__.py
      rules.py           # rules.yaml loader + regex matcher
      llm.py             # MLX client (local) + fallback logic
      models.py          # Classification dataclass (category, root_cause, confidence)
    resolver/
      __init__.py
      actions.py         # Level 0/1/2 action dispatch
      github.py          # GitHub API client (comment, re-run, fetch log, fetch diff)
      cloud_fix.py       # Deepseek V4 Flash client for fix generation
    knowledge/
      __init__.py
      base.py            # YAML KB load/save/query/update
      corrections.py     # reaction handler: 👎 → prompt → reply → update KB
    report/
      __init__.py
      trend.py           # M5: failures by category, auto-resolve rate, MTTR
      cost.py            # M6: token cost vs engineer time saved
    storage/
      __init__.py
      decisions.py       # decisions.yaml read/write (the decision log)
  cli/
    __init__.py
    report.py            # `ci-doctor report --days 7` CLI entry point
  tests/
    __init__.py
    test_webhook.py      # signature verification, dedup, event routing
    test_classifier.py   # rules matching, LLM fallback, confidence threshold
    test_resolver.py     # Level 1 re-run, Level 2 fix, escalation
    test_knowledge.py    # KB query, update, correction flow
    test_report.py       # trend + cost report generation
    fixtures/
      logs/              # labeled failure log corpus (flake, lint, build, dep, timeout)
  rules.yaml             # classification rules (mounted into container)
  knowledge_base.yaml    # KB (Docker volume — persists across restarts)
  decisions.yaml         # decision log (Docker volume — persists across restarts)
  Dockerfile
  docker-compose.yml     # single service: ci-doctor + volume mounts
  pyproject.toml         # dependencies, ruff config, pytest config
  Makefile               # make test, make lint, make build, make run
  README.md
  docs/
    prd.md
    spec.md
```

## Architecture

```
GitHub Actions failure
        │
        ▼ (workflow_run webhook)
┌───────────────┐
│  Webhook      │  (Docker container, port 8080)
│  Receiver     │  → verify signature → dedup by event ID → enqueue
└──────┬────────┘
       │
       ▼
┌───────────────┐
│  Single       │  (in-memory queue, one at a time)
│  Worker       │
└──────┬────────┘
       │
       ▼
┌───────────────┐         ┌─────────────────┐
│  Classifier   │────────▶│  Local MLX      │  (Llama 3.2, free, fast)
│  (rules +     │  LLM    │  server         │  (optional — rules are
│   LLM hybrid) │  call   └─────────────────┘   the floor)
└──────┬────────┘
       │
       ├── confidence ≥ 0.90 + flake ──▶ GitHub Actions API: re-run job
       │
       ├── confidence ≥ 0.90 + lint/build/dep ─▶ Cloud model: generate fix ──▶ comment
       │
       └── confidence < 0.90 ─────────▶ comment: "escalating — @reviewer"
       │
       ▼
┌───────────────┐
│  Knowledge    │  (YAML file, single-writer via queue)
│  Base         │  signature → category → remediation → confidence → outcomes
└───────────────┘
       │
       ▼
┌───────────────┐
│  Report Gen   │  (Markdown output)
│  (M5/M6)      │  `ci-doctor report --days 7`
└───────────────┘
```

Four components, all running in a single Docker container:

- **Webhook receiver** — HTTP server on port 8080. Receives GitHub Actions `workflow_run` events. Verifies the webhook signature, deduplicates by event ID, and enqueues the event for processing.
- **Worker** — Single-threaded consumer of the in-memory queue. Processes one event at a time. No concurrent knowledge base writes ever.
- **Classifier** — Hybrid: rules YAML (regex signatures) first, local MLX model for unknowns. Rules-only is the floor — the LLM is an optimization, never a requirement.
- **Report generator** — CLI command that reads the knowledge base + decision log and produces a Markdown report.

External dependencies:
- **Local MLX server** — Apple's native ML framework running on the host (not in Docker — needs direct Apple Silicon / Metal access). Served over HTTP via `mlx_lm.server` (OpenAI-compatible REST API). Model: `Llama-3.2-3B-Instruct-4bit`. Called only for unknown failure classifications. If down, rules-only classification runs.
- **Cloud model** — Deepseek V4 Flash (via OpenAI-compatible API). Called only for fix generation (Level 2). If down, skip fix and comment "fix unavailable — manual triage."
- **GitHub API** — PAT-authenticated. Used for: fetching failure logs, posting PR comments, re-running failed jobs, fetching PR diffs. If rate-limited, log + retry with exponential backoff.

## Webhook Receiver

### Event Model
- **Trigger:** GitHub Actions `workflow_run` event with `conclusion=failure`.
- **Webhook payload:** GitHub delivers the `workflow_run` object. The receiver extracts: repo, run ID, commit SHA, PR number (included in the payload — no separate API call needed), branch.
- **Signature verification:** GitHub's `X-Hub-Signature-256` header verified against `GITHUB_WEBHOOK_SECRET` env var using HMAC-SHA256. Reject + 401 if invalid.
- **v1:** Webhook only. No polling fallback. If the receiver is down, events are missed — acceptable for v1.

### Event Routing
The receiver handles two webhook event types:
- `workflow_run` (conclusion=failure) → enqueue for classification + resolution.
- `reaction` (on ci-doctor's own comments) → route to the correction handler (see Knowledge Base > Learning from Corrections).

### Idempotency
- Track processed GitHub event IDs in an in-memory `set()`.
- On receipt: check if `event_id` is in the set. If yes, return 200 OK + no-op (GitHub redelivers on timeout; this prevents duplicate comments, re-runs, and KB entries).
- If no, add to set + enqueue for processing.
- The set resets on container restart. Acceptable for v1 — a restart during a redelivery window (seconds) is unlikely, and the worst case is one duplicate comment.

### Concurrency
- Webhook receiver enqueues events into an in-memory `asyncio.Queue`.
- A single worker coroutine drains the queue one event at a time.
- No concurrent knowledge base writes. No concurrent GitHub API calls from the worker (though the receiver itself responds immediately).
- Acceptable for v1 volume (~5 failures/week).

### Comment Strategy
- No "analyzing…" placeholder comment. The engineer sees nothing from ci-doctor until the full diagnosis is ready (within 60s).
- Single diagnosis comment per failing job — no edits, no follow-up "analyzing" comments.
- For Level 1 re-runs: the diagnosis comment includes "auto-re-running job `X`…" and a second comment is posted when the re-run completes with the result.
- **Comment format: plain text. No emojis. No markdown headers.** Use simple structure with labels:
  ```
  ci-doctor diagnosis:
  
  Category: flake
  Confidence: 95%
  Root cause: test_parser.py:42 — AssertionError: expected 'passed' but got 'failed'
  Action: auto-re-running job 'test'
  ```
  Re-run result comment:
  ```
  ci-doctor update:
  
  Re-run passed. Flaky test confirmed. No action needed.
  ```
  Escalation comment:
  ```
  ci-doctor diagnosis:
  
  Category: dependency
  Confidence: 40% (below auto-resolve threshold)
  Root cause: requests upgraded to 2.32, dropped urllib3 compat shim used in client.py:88
  Action: escalating — @author please confirm or correct
  ```
  Fix suggestion comment:
  ```
  ci-doctor diagnosis:
  
  Category: lint
  Confidence: 92%
  Root cause: server.py:14 — unused import 'unused_module' (rule F401)
  Suggested fix:
      - import unused_module
  ```

## Failure Log Fetch + Parsing

- GitHub API: `GET /repos/{owner}/{repo}/actions/runs/{run_id}/logs` returns a zip archive of all job logs.
- ci-doctor downloads the zip, extracts the log for the failing job only, and parses it locally.
- **Snippet extraction:** find the error line in the log, then capture:
  - **-200 lines** before the error (context leading up to the failure).
  - **+100 lines** after the error (stack trace, cleanup, secondary errors).
- The snippet (not the full log) is what gets:
  - Passed to the rules engine for regex matching.
  - Passed to the local LLM for classification (if no rule matches).
  - Passed to the cloud model for fix generation (Level 2).
- Full log is discarded after snippet extraction. Only the snippet is stored in the decision log.

### Rules Engine (the floor)
- A YAML file (`RULES_PATH` env var, default `rules.yaml`) contains regex signatures for known failure patterns.
- Each rule: `signature` (regex), `category`, `confidence` (0-1), `action` (auto_rerun / suggest_fix / escalate).
- The classifier runs all rules against the failure log. First match wins (rules are ordered by specificity in the YAML).
- If a rule matches, classification is instant, free, and requires no LLM call.
- Rules YAML format (v1 ships rules for flakes + lint only; build/dependency/infra_timeout go through the LLM):
  ```yaml
  rules:
    # Flakes — auto-re-run
    - signature: "AssertionError.*passed.*failed"
      category: flake
      confidence: 0.95
      action: auto_rerun
    - signature: "TestResult.*failures.*flaky"
      category: flake
      confidence: 0.93
      action: auto_rerun
    - signature: "pytest.*failed.*passed.*on retry"
      category: flake
      confidence: 0.91
      action: auto_rerun
    # Lint — suggest fix
    - signature: "F401.*import"
      category: lint
      confidence: 0.92
      action: suggest_fix
    - signature: "E501.*line too long"
      category: lint
      confidence: 0.90
      action: suggest_fix
    - signature: "ruff.*unused.*variable"
      category: lint
      confidence: 0.91
      action: suggest_fix
  ```
- **Build, dependency, and infra_timeout categories start LLM-only** (no seed rules). The KB fills gaps over time as the LLM classifies them and engineers correct misclassifications.
- **Infra timeout action is configurable:** default action is `escalate`, but a rule can override to `auto_rerun` for specific timeout signatures known to be transient (e.g., `timeout.*runner.*busy` → re-run once).

### LLM Fallback (for unknowns)
- If no rule matches, the classifier calls the local MLX server.
- Prompt: the failure log (truncated to fit context window) + the PR diff (if available) + "Classify this CI failure into one of: flake, lint, build_error, dependency, infra_timeout, unknown. Provide category, root cause, and confidence (0-1)."
- The MLX server returns a structured response: `{ category, root_cause, confidence }`.
- If the MLX server is down, classify as `unknown` and escalate. Rules-only is the floor — the agent always functions.

### Classification Output
- Every classification produces: `category`, `root_cause` (1-2 sentences), `confidence` (0-1), `action` (determined by category + confidence vs threshold).
- One comment per failing job. If a run has 3 failing jobs, 3 diagnosis comments are posted.

### Confidence Threshold
- Default: `0.90` (configurable via `CONFIDENCE_THRESHOLD` env var).
- Above threshold: auto-act (Level 1 re-run for flakes, Level 2 fix suggest for lint/build/dep).
- Below threshold: Level 0 comment only + escalate (tag the PR author).

## Auto-Resolver

### Level 1 — Flaky Test Re-run
- Trigger: category = flake + confidence ≥ threshold.
- Call GitHub Actions API: `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun` with `GITHUB_TOKEN`.
- Poll for re-run result: `GET /repos/{owner}/{repo}/actions/runs/{run_id}` every 30 seconds until `status=completed`.
- If re-run passes: comment "Flaky test detected in `{file}:{line}` — auto re-ran, passed. No action needed." Log outcome to KB.
- If re-run fails again: reclassify the failure (the flake hypothesis was wrong). Comment "Re-run also failed — reclassifying. New diagnosis: {category}." Escalate if needed.

### Level 2 — Fix Suggestion
- Trigger: category = lint / build / dependency + confidence ≥ threshold.
- Call the cloud model with: the failure log + the PR diff + "Generate a fix for this failure. Return only the diff/code block, no explanation."
- **Cost check:** estimate token count before the call. If estimated cost > `COST_CEILING` ($1.00 default), skip the call and comment "Fix generation skipped — cost ceiling exceeded. Manual triage recommended."
- Post the fix as a code block in the PR comment: "Suggested fix:\n```{lang}\n{fix}\n```"
- No auto-commit, no fix PR. The engineer copy-pastes the fix.
- Log the suggestion + outcome to the KB.

### Escalation
- Trigger: confidence < threshold, or category = infra_timeout / unknown.
- Comment: "ci-doctor could not auto-resolve this failure. Category: {category}. Root cause hypothesis: {root_cause}. Confidence: {confidence}. @author please review."
- Log the escalation to the KB.
- No notifications beyond the PR comment (no Slack, no email in v1).

## Knowledge Base

### Storage
- A single YAML file (`KB_PATH` env var, default `knowledge_base.yaml`).
- Loaded into memory at startup. Written back to disk after each update by the single worker (no concurrent writes).
- Per-repo in v1 (the KB is scoped to the ci-doctor repo).
- No pruning in v1. The KB will be small (one repo, ~5 failures/week).

### Schema
```yaml
patterns:
  - signature: "AssertionError.*passed.*failed"
    category: flake
    remediation: "auto_rerun"
    confidence: 0.95
    occurrences: 3
    last_seen: 2026-07-01T14:32:00Z
    outcomes:
      - { result: resolved, timestamp: 2026-07-01T14:33:00Z }
      - { result: resolved, timestamp: 2026-07-02T09:15:00Z }
      - { result: corrected, note: "actually a timeout", timestamp: 2026-07-03T10:00:00Z }
```

### Query
- On classification, the classifier checks the KB for a matching signature before running rules or LLM.
- If a KB pattern matches and has `confidence ≥ threshold`, use the KB's category + action directly (faster than rules, and incorporates past corrections).
- If a KB pattern matches but has been corrected before, use the corrected category.

### Learning from Corrections
- **Correction mechanism:** GitHub reaction. An engineer reacts with thumbs down to the bot's diagnosis comment to signal "wrong classification."
- ci-doctor listens for `reaction` webhooks on its own comments (second event handler in the receiver). On thumbs down:
  1. Reply to the comment: "Got it -- this classification was wrong. What is the correct category? Reply with one of: flake, lint, build, dependency, infra_timeout."
  2. Wait for the engineer's reply comment containing a category keyword.
  3. On reply: update the KB pattern's category, decrement the old confidence, add an `outcome: corrected` entry with the engineer's category + timestamp.
  4. Post: "Correction logged. Category updated to {new_category}. I will not make this mistake next time."
- Next time the same signature appears, the corrected classification is used.

## Decision Log

### Storage
- A single YAML file (`DECISIONS_PATH` env var, default `decisions.yaml`).
- Appended to after every agent decision. Written by the single worker (no concurrent writes).
- Persisted via Docker volume so it survives container restarts.

### Schema
```yaml
decisions:
  - event_id: "12345678"
    timestamp: 2026-07-01T14:32:00Z
    repo: "deghosal-2026/ci-doctor"
    commit_sha: "abc1234"
    pr_number: 42
    job_name: "test"
    category: "flake"
    confidence: 0.95
    action: "auto_rerun"
    latency_ms: 28000
    token_cost: 0.0
    outcome: "resolved"
    log_snippet: "AssertionError: expected 'passed' but got 'failed'\n  at test_parser.py:42"
  - event_id: "12345679"
    timestamp: 2026-07-01T15:10:00Z
    repo: "deghosal-2026/ci-doctor"
    commit_sha: "def5678"
    pr_number: 43
    job_name: "lint"
    category: "lint"
    confidence: 0.92
    action: "suggest_fix"
    latency_ms: 35000
    token_cost: 0.003
    outcome: "resolved"
    log_snippet: "server.py:14: F401 unused import 'unused_module'"
```

### Usage
- The report generator reads `decisions.yaml` to produce trend + cost reports.
- Each decision is one entry. The `outcome` field is updated when a re-run completes or a correction is logged.

## Report Generator

### Trend Report (M5)
- CLI: `ci-doctor report --days 7`
- Reads the decision log (every agent decision is logged with: timestamp, event_id, category, action, confidence, latency_ms, outcome).
- Generates a Markdown table:
  - Failures by category (count per category).
  - Auto-resolve rate (auto-resolved / total, percentage).
  - MTTR trend (estimated: time from failure event to resolution comment).
  - Top recurring failure signatures (by occurrence count).
- Output: Markdown to stdout. Redirect to a file or pipe into Obsidian.

### Cost Report (M6)
- Extends the trend report with:
  - Token cost per resolution (sum of cloud model call costs for that period).
  - Total token spend.
  - Estimated engineer time saved: 5 min per auto-resolved flake, 10 min per auto-suggested lint/build/dep fix.
  - Cost-vs-value multiplier: (engineer time saved × hourly rate) / token spend.
- Default hourly rate: $100/hr (configurable via `ENGINEER_HOURLY_RATE` env var).

## Auth & Configuration

### GitHub Authentication
- **v1:** Personal Access Token (PAT) with `repo` and `workflow` scopes.
- Stored in `GITHUB_TOKEN` env var.
- Used for: fetching failure logs, posting PR comments, re-running jobs, fetching PR diffs.
- **Post-v1:** Migrate to GitHub App with installation token flow (supports multi-repo, scoped permissions, token refresh).

### Webhook Secret
- `GITHUB_WEBHOOK_SECRET` env var. Used to verify `X-Hub-Signature-256` header.

### Environment Variables
| Env var | Required | Default | Purpose |
|---------|----------|---------|---------|
| `GITHUB_TOKEN` | Yes | — | PAT for GitHub API calls |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | Webhook signature verification |
| `MLX_ENDPOINT` | No | `http://localhost:8000` | Local MLX server URL |
| `CLOUD_API_KEY` | No | — | Cloud model API key (for fix generation) |
| `CLOUD_MODEL` | No | `deepseek-v4-flash` | Cloud model identifier |
| `COST_CEILING` | No | `1.00` | Max token cost per resolution (USD) |
| `CONFIDENCE_THRESHOLD` | No | `0.90` | Auto-act confidence threshold |
| `KB_PATH` | No | `knowledge_base.yaml` | Path to the knowledge base file |
| `RULES_PATH` | No | `rules.yaml` | Path to the classification rules file |
| `DECISIONS_PATH` | No | `decisions.yaml` | Path to the decision log file |
| `ENGINEER_HOURLY_RATE` | No | `100` | Hourly rate for cost-vs-value calc |
| `PORT` | No | `8080` | Webhook receiver port |

### Mounted Files
- `rules.yaml` — the only file mounted into the container. It's config (classification signatures), not secrets.
- `knowledge_base.yaml` — persisted via a Docker volume so it survives container restarts.
- `decisions.yaml` — persisted via a Docker volume so it survives container restarts.

### Docker Deployment
```yaml
# docker-compose.yml
services:
  ci-doctor:
    build: .
    ports:
      - "8080:8080"
    environment:
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GITHUB_WEBHOOK_SECRET: ${GITHUB_WEBHOOK_SECRET}
      MLX_ENDPOINT: ${MLX_ENDPOINT:-http://host.docker.internal:8000}
      CLOUD_API_KEY: ${CLOUD_API_KEY}
      CLOUD_MODEL: ${CLOUD_MODEL:-deepseek-v4-flash}
    volumes:
      - ./rules.yaml:/app/rules.yaml:ro
      - kb_data:/app/knowledge_base.yaml
      - decisions_data:/app/decisions.yaml
    restart: unless-stopped

volumes:
  kb_data:
  decisions_data:
```

## Observability

### Health Endpoint
- `GET /health` → `200 OK` with `{"status": "up"}` if the process is running and the webhook receiver is listening.
- No deeper health checks in v1 (no dependency probes for MLX or GitHub API).

### Structured Logs
- JSON to stdout for every event. Docker logs are the v1 observability layer.
- Fields: `event_id`, `timestamp`, `repo`, `commit_sha`, `job_name`, `category`, `confidence`, `action`, `latency_ms`, `token_cost`, `outcome`.
- No external log aggregation in v1.

## Degradation Matrix

| Dependency down | Behavior |
|-----------------|----------|
| Local MLX server | Rules-only classification. Unknowns classified as `unknown` + escalate. Agent fully functional. |
| Cloud model | Skip fix generation. Comment "fix unavailable — manual triage." Classification + re-runs still work. |
| GitHub API (rate-limited) | Log + retry with exponential backoff (1s, 2s, 4s, 8s, max 60s). If still rate-limited after 5 retries, log + skip event. |
| GitHub API (fully down) | Cannot post comments or re-run. Log the failure. Event is lost (no retry queue persistence in v1). |

## Data Strategy: Rules Corpus & Evaluation

The classifier uses a hybrid approach (regex rules + LLM fallback). There is no ML model training — the "rules corpus" is the set of regex patterns hand-crafted from real failure logs.

### Sourcing

Pull from public GitHub repos via the Actions API:

```
gh api repos/{owner}/{repo}/actions/runs --jq '.workflow_runs[] | select(.conclusion=="failure") | .id'
gh run view <id> --log
```

Target repos: FastAPI, pandas, pytest, ruff, httpx (high-traffic Python OSS with visible CI).

### Rules Corpus (~300 logs)

Purpose: identify recurring failure patterns and craft seed regex rules.

| Category | Target count | Pattern discovery |
|----------|-------------|-------------------|
| flake | ~60 | assertion errors, flaky test messages, timeout-in-test |
| lint | ~60 | ruff/pylint/flake8 output, unused imports, line-length |
| build | ~60 | compilation errors, ModuleNotFoundError, type errors |
| dependency | ~60 | pip/conda version conflicts, missing packages, lockfile |
| infra_timeout | ~60 | runner timeout, context deadline, cancellation |

Expected output: ~2-5 regex patterns per category, added to `rules.yaml` seed rules.

### Evaluation Corpus (~1000 logs)

Purpose: measure classification accuracy, auto-resolve rate, and false-positive rate before ship.

Same category split as above (~200 each). Each log is manually labeled with its correct category. The evaluation runs:

1. Feed each log through the classifier.
2. Measure: accuracy per category, overall accuracy, false-positive rate (non-flake classified as flake).
3. Target: per-category accuracy >= 90%, overall >= 85%, false-positive rate < 10%.

### Storage

```
tests/fixtures/logs/
  rules/          # ~300 logs for pattern engineering
    flake/
    lint/
    build/
    dependency/
    timeout/
  eval/           # ~1000 logs for accuracy measurement
    flake/
    lint/
    build/
    dependency/
    timeout/
  labels.yaml     # ground-truth labels for eval corpus
```

Each log is a `.txt` file with the raw GitHub Actions log output. Metadata (repo, run ID, job name, timestamp) is optional in the filename or a companion `.meta.yaml`.

## Related

- PRD: [`prd.md`](./prd.md)
- Project page: [`vault/projects/04-CI-Agent.md`](https://github.com/deghosal-2026/my-2nd-brain/blob/main/vault/projects/04-CI-Agent.md)
- Repo: [ci-doctor](https://github.com/deghosal-2026/ci-doctor)
- Data strategy: § Data Strategy: Rules Corpus & Evaluation
