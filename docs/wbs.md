# Work Breakdown Structure — ci-doctor (CI-Agent)

> Granular task breakdown mapped to GitHub issues. Derived from [`spec.md`](./spec.md).

**Status:** Complete — 2026-07-02 (shipped)

## Milestone Summary

| Milestone | Deliverable | Issues |
|-----------|-------------|--------|
| M1 | Webhook receiver + failure parser | #1–#10 |
| M2 | Classifier + diagnosis comment | #11–#18 |
| M3 | Auto-resolver (re-run + fix suggest) | #19–#26 |
| M4 | Knowledge base + corrections | #27–#33 |
| M5 | Trend report | #34–#39 |
| M6 | Cost report | #40–#43 |
| M7 | Testing, docs, packaging, ship | #44–#52 |
| M7a | Data collection + evaluation (rules corpus + eval corpus) | #53–#58 |

---

## M1 — Webhook Receiver + Failure Parser

### Infrastructure / Scaffolding
- [x] #1 Project scaffold: pyproject.toml, app/ package, FastAPI entrypoint, Makefile
- [x] #2 Config module: env var loading + validation (config.py)
- [x] #3 Dockerfile + docker-compose.yml with volume mounts

### Webhook Receiver
- [x] #4 GitHub webhook signature verification (HMAC-SHA256, X-Hub-Signature-256)
- [x] #5 Event ID dedup (in-memory set, 200 OK no-op on redelivery)
- [x] #6 Event routing: workflow_run → classify queue, reaction → correction handler
- [x] #7 asyncio.Queue + single worker coroutine

### Failure Log Fetch + Parse
- [x] #8 GitHub API client: fetch run logs (zip download + extract failing job)
- [x] #9 Snippet extraction: -200 lines before error, +100 lines after

### Health
- [x] #10 GET /health endpoint (200 + {"status": "up"})

---

## M2 — Classifier + Diagnosis Comment

### Rules Engine
- [x] #11 rules.yaml loader + regex matcher (first match wins)
- [x] #12 Seed rules.yaml: 3 flake signatures + 3 lint signatures

### LLM Fallback
- [x] #13 MLX client: call local Llama 3.2, parse structured response {category, root_cause, confidence}
- [x] #14 Classification prompt: log snippet + PR diff + category list

### Classification Logic
- [x] #15 Classification dataclass + confidence threshold logic (0.90 default)
- [x] #16 KB query before rules/LLM (check corrected patterns first)

### Comment
- [x] #17 GitHub API: post PR comment (plain text, no emojis, template format)
- [x] #18 GitHub API: fetch PR diff for root-cause analysis

---

## M3 — Auto-Resolver

### GitHub Actions API
- [x] #19 GitHub API: re-run failed job (POST /actions/runs/{id}/rerun)
- [x] #20 Re-run polling: GET /actions/runs/{id} every 30s until completed
- [x] #21 Re-run result comment (passed: "no action needed" / failed: reclassify + escalate)

### Fix Generation
- [x] #22 Deepseek V4 Flash client: send log snippet + diff, receive fix
- [x] #23 Cost ceiling check: estimate tokens before call, skip if > $1.00
- [x] #24 Fix suggestion comment (plain text diff block, no auto-commit)

### Escalation
- [x] #25 Escalation comment: category + root cause + confidence + @author
- [x] #26 Action dispatch: route classification → Level 0 / 1 / 2 / escalate

---

## M4 — Knowledge Base + Corrections

### KB Storage
- [x] #27 KB YAML load/save (knowledge_base.yaml, in-memory + disk write)
- [x] #28 KB schema: signature → category, remediation, confidence, occurrences, last_seen, outcomes[]
- [x] #29 KB update on every classification (increment occurrences, add outcome)

### Corrections
- [x] #30 Reaction webhook handler: thumbs down on ci-doctor comment → trigger correction
- [x] #31 Correction prompt comment: "What is the correct category? Reply with: flake, lint, build, dependency, infra_timeout"
- [x] #32 Reply listener: parse category keyword from reply comment
- [x] #33 KB correction update: update category, decrement old confidence, add corrected outcome

---

## M5 — Trend Report

### Decision Log
- [x] #34 decisions.yaml writer: append decision after every agent action
- [x] #35 decisions.yaml schema: event_id, timestamp, repo, commit_sha, pr_number, job_name, category, confidence, action, latency_ms, token_cost, outcome, log_snippet

### Report Generation
- [x] #36 CLI: `ci-doctor report --days 7` (Click CLI entry point)
- [x] #37 Aggregation: failures by category, auto-resolve rate, MTTR, top signatures
- [x] #38 Markdown output: tables + summary to stdout
- [x] #39 Decision outcome updates: update outcome field when re-run completes or correction logged

---

## M6 — Cost Report

- [x] #40 Token cost aggregation: sum cloud model costs per resolution
- [x] #41 Engineer time saved: 5 min per flake, 10 min per lint/build/dep fix
- [x] #42 Cost-vs-value multiplier: (time saved x hourly rate) / token spend
- [x] #43 Cost report Markdown output (extends trend report)

---

## M7a — Data Collection + Evaluation

> Per spec: 300-log rules corpus (pattern engineering) + 1000-log eval corpus (accuracy measurement). Source from high-traffic public Python repos (FastAPI, pandas, pytest, ruff, httpx).

### Data Sourcing
- [x] #53 Data sourcing script: `scripts/pull_failures.py` — fetches failed workflow run logs from public GitHub repos via Actions API + `gh run view`
- [x] #54 Rules corpus collection: ~300 logs (~60 per category) — raw `.txt` files in `tests/fixtures/logs/rules/{category}/`
- [x] #55 Eval corpus collection: ~1000 logs (~200 per category) — raw `.txt` files in `tests/fixtures/logs/eval/{category}/`

### Pattern Engineering
- [x] #56 Label eval corpus: create `tests/fixtures/logs/labels.yaml` with ground-truth category for each eval log
- [x] #57 Craft seed regex patterns from rules corpus → update `rules.yaml` with 2-5 patterns per category

### Accuracy Measurement
- [x] #58 Evaluation harness: feed eval corpus through classifier, measure per-category accuracy, overall accuracy, false-positive rate. Target: >= 85% overall, < 10% false-positive.

---

## M7 — Testing, Docs, Packaging, Ship

### Test Fixtures
- [x] #44 Labeled failure log corpus: 2+ logs per category (flake, lint, build, dependency, timeout)

### Tests
- [x] #45 test_webhook.py: signature verification, dedup, event routing
- [x] #46 test_classifier.py: rules matching, LLM fallback, confidence threshold, KB-first query
- [x] #47 test_resolver.py: Level 1 re-run + polling, Level 2 fix + cost ceiling, escalation
- [x] #48 test_knowledge.py: KB query, update, correction flow (thumbs down → reply → update)
- [x] #49 test_report.py: trend + cost report generation from decisions.yaml

### Docs + Ship
- [x] #50 README.md: what it is, how to deploy, how to configure webhooks + env vars
- [x] #51 User guide: setup GitHub Actions webhook, PAT scopes, rules.yaml editing
- [x] #52 v1 tag + GitHub release + ship

---

## Dependency Order

```
#1 (scaffold) → #2 (config) → #3 (Docker)
#1 → #4 (sig verify) → #5 (dedup) → #6 (event routing) → #7 (queue)
#7 → #8 (log fetch) → #9 (snippet extraction)
#1 → #10 (health endpoint)

#7 → #11 (rules engine) → #12 (seed rules) → #16 (KB-first query)
#11 → #13 (MLX client) → #14 (prompt)
#13 → #15 (classification dataclass)
#15 → #17 (comment posting) → #18 (fetch PR diff)

#15 → #26 (action dispatch)
#26 → #19 (re-run API) → #20 (polling) → #21 (result comment)
#26 → #22 (Deepseek client) → #23 (cost ceiling) → #24 (fix comment)
#26 → #25 (escalation comment)

#11 → #27 (KB load/save) → #28 (schema) → #29 (update on classify)
#6 → #30 (reaction handler) → #31 (correction prompt) → #32 (reply listener) → #33 (KB correction)

#7 → #34 (decisions writer) → #35 (schema)
#34 → #36 (CLI) → #37 (aggregation) → #38 (markdown output) → #39 (outcome updates)
#37 → #40 (cost aggregation) → #41 (time saved) → #42 (multiplier) → #43 (cost report)

#9 → #44 (fixtures) → #45–#49 (tests)
#3 → #50 (README) → #51 (user guide) → #52 (v1 tag)
```

## Related

- PRD: [`prd.md`](./prd.md)
- Spec: [`spec.md`](./spec.md)
- Project page: [`vault/projects/04-CI-Agent.md`](https://github.com/deghosal-2026/my-2nd-brain/blob/main/vault/projects/04-CI-Agent.md)
