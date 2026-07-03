# Product Requirements Document — ci-doctor (CI-Agent)

> Self-Healing CI/CD Pipeline

**Status:** Complete — 2026-07-02 (shipped)

## Overview

A CI failure fires. Within 60 seconds, ci-doctor classifies the failure (flake, lint, build, dependency, infra timeout), comments on the PR with the diagnosis, and for known patterns (flaky tests, lint errors) suggests or applies the fix. The engineer sees: "Build failed — flaky test detected in auth_test.go:42. Auto re-ran and passed. No action needed."

For unknown failures, the agent analyzes the log + diff, proposes a root cause, and tags a human. The human confirms or corrects the diagnosis — and that feedback trains the agent for next time.

A Markdown report shows CI failure categorization over time, auto-resolved vs human-resolved ratio, MTTR trend, and token cost per resolution. The goal: 40-60% of failures auto-triaged. Engineers talk about "the CI bot that fixes its own problems" — not "the CI that's always red."

**v1 scope:** ci-doctor runs on itself. GitHub Actions is the CI platform. A self-hosted Docker service receives webhooks, classifies failures, and comments on PRs in this repo.

## Problem Statement — WHY

Failed CI builds waste engineering hours. Someone has to triage flakes, rebase, re-run, and diagnose — context-switching that kills flow.

**Concrete pain:**
- **Volume:** ~5 CI failures/week across the team's repos. Each requires manual investigation.
- **Time burned:** ~5 hours/week of engineer time spent on CI triage across 10 engineers — roughly half an engineering week per month. For a 5-team org, that's 2+ engineering-weeks/month burned on triage.
- **MTTR today:** Builds stay red for hours because no one has time to investigate immediately. The failure sits in someone's queue until they context-switch.
- **Who hurts most:** PR authors. A red build blocks their PR, blocks reviewers, and forces a context switch into log-diving instead of forward progress.

This is also an entry point into agentic design. CI triage is the perfect bounded problem: the domain is constrained (failed builds), the actions are well-defined (comment, re-run, rebase), and the feedback loop is fast (seconds, not minutes).

## Goals — WHAT

- **Classify every CI failure** into a category (flake, lint, build error, dependency conflict, infra timeout) within 60 seconds of the failure event.
- **Auto-resolve safe failure types** — flaky tests (re-run via GitHub Actions API), lint errors (suggest fix in a comment) — without human intervention.
- **Comment on the PR with a diagnosis** for every failure: what failed, why, and what action was taken or is recommended.
- **Escalate ambiguous failures to a human** with a proposed root cause + tagged reviewer; capture the human's correction as training signal.
- **Build a queryable knowledge base** of failure patterns: error signature → category → remediation → confidence. The agent gets smarter over time without retraining.
- **Surface failure trends** in a Markdown report: failures by category, auto-resolve rate, MTTR trend, token cost per resolution.
- **Prove the business case:** show that auto-triaging failures saves engineer-hours at a token cost that's a fraction of the time saved.

## Non-Goals

- **No auto-merge or auto-deploy.** The blast radius of a bad agent action must never reach production. PR comments and re-runs are safe; merges are not.
- **No general-purpose CI agent.** v1 targets GitHub Actions only, scoped to the ci-doctor repo itself. Patterns that work here may not generalize — that's fine for v1.
- **No multi-repo support in v1.** One repo (ci-doctor on ci-doctor). Multi-repo is a post-v1 expansion.
- **No replacing human judgment for novel failures.** The agent proposes; the human disposes for anything outside known patterns.
- **No polling fallback in v1.** Webhook-only. If the receiver is down, events are missed — acceptable for v1; add polling in a hardening pass.
- **No web UI dashboard.** v1 delivers a Markdown report. A web dashboard is a post-v1 enhancement if the Markdown report proves insufficient.
- **No notifications beyond PR comments.** No Slack, no email. The engineer is already watching their PR.
- **No knowledge base pruning in v1.** The KB will be small (one repo, ~5 failures/week). Pruning is a post-v1 concern.
- **No secret scrubbing in v1.** v1 is self-hosted on our own repo. Add scrubbing when we go multi-repo or external.

## Target Users

- **Primary:** PR authors whose builds fail. They want the failure triaged and (if safe) resolved before they even notice the red build.
- **Secondary:** Tech leads / engineering managers who want the trend report for their team's CI health — to prioritize which test suites to fix and to prove the agent's ROI.
- **Deployment model:** Self-hosted Docker service. Runs in our own infra (a VM or local machine for v1). Receives GitHub Actions webhooks, authenticates via a Personal Access Token (GitHub App migration is post-v1), calls the GitHub API to comment and re-run, stores its knowledge base as a local YAML file. All config via environment variables — no config file to mount.

## Customer Journeys

> Each journey shows the exact sequence of what the engineer sees on their GitHub PR, with timestamps relative to the CI failure event (T+0).

### Journey 1 — The flaky test (auto-resolved, no engineer action needed)

**Scenario:** Engineer pushes a PR. A flaky test fails intermittently in the test suite.

| Time | What happens | What the engineer sees |
|------|-------------|----------------------|
| T+0 | CI run fails on a flaky test. GitHub Actions webhook fires. | Red ❌ on the PR check status. |
| T+5s | ci-doctor receives webhook, posts initial comment. | 🤖 **ci-doctor** — *Received failure for job `test` — analyzing…* |
| T+30s | ci-doctor fetches the failure log, classifies as flake (confidence 0.95), triggers a re-run via GitHub Actions API. | 🤖 **ci-doctor** — *Diagnosis: **Flaky test** (confidence 95%). Root cause: `test_parser.py:42` — `AssertionError: expected 'passed' but got 'failed'`. Pattern matches known flaky behavior. **Auto-re-running job `test`…*** |
| T+3min | Re-run completes. Job passes. | 🤖 **ci-doctor** — *✅ Re-run passed. Flaky test confirmed. No action needed. Closing this analysis.* |
| — | Engineer never had to open the CI logs. | Green ✅ on the PR check status. PR is unblocked. |

**Engineer's experience:** "I pushed, saw a red check, was about to click in, and by the time I did the bot had already fixed it. I went back to coding."

---

### Journey 2 — The lint error (fix suggested, engineer applies)

**Scenario:** Engineer pushes a PR with an unused import. Lint check fails.

| Time | What happens | What the engineer sees |
|------|-------------|----------------------|
| T+0 | CI run fails on lint check. Webhook fires. | Red ❌ on the PR check status. |
| T+5s | ci-doctor posts initial comment. | 🤖 **ci-doctor** — *Received failure for job `lint` — analyzing…* |
| T+20s | Rules match: F401 unused import. Confidence 0.92. ci-doctor escalates to cloud model for fix generation. | (no new comment yet) |
| T+40s | Cloud model returns the one-line fix. ci-doctor posts the diagnosis + fix. | 🤖 **ci-doctor** — *Diagnosis: **Lint error** (confidence 92%). `server.py:14` — unused import `unused_module` (rule F401). **Suggested fix:*** ```diff - import unused_module ``` *Copy the fix, push, and CI should go green.* |
| T+? | Engineer copies the one-line fix, removes the import, pushes. | Green ✅ on the PR check status. |

**Engineer's experience:** "The bot told me exactly what to delete and where. One edit, one push, done. Didn't have to read the linter docs."

---

### Journey 3 — The real failure (human escalated, agent proposes root cause)

**Scenario:** Engineer pushes a PR that upgrades a dependency. The build fails because the new version dropped an API the code uses.

| Time | What happens | What the engineer sees |
|------|-------------|----------------------|
| T+0 | CI run fails on the build job. Webhook fires. | Red ❌ on the PR check status. |
| T+5s | ci-doctor posts initial comment. | 🤖 **ci-doctor** — *Received failure for job `build` — analyzing…* |
| T+45s | No rule matches. ci-doctor calls the local LLM. LLM classifies as "dependency conflict" but confidence is 0.40 (below 0.90 threshold). ci-doctor fetches the PR diff, sees the `requests` upgrade, correlates with the error. | (no new comment yet) |
| T+60s | ci-doctor posts the escalation with the root-cause hypothesis. | 🤖 **ci-doctor** — *Diagnosis: **Dependency conflict** (confidence 40% — below auto-resolve threshold). Root cause hypothesis: `requests` upgraded to 2.32 in this PR, which dropped the `urllib3` compat shim used in `client.py:88`. Error: `AttributeError: 'NoneType' object has no attribute 'urlopen'`. **Recommended fix:** pin `requests<2.32` or migrate to `httpx`. *@engineer please confirm or correct.* |
| T+? | Engineer reads the hypothesis, confirms it's correct, applies the fix (`httpx` migration), pushes. | Green ✅ on the PR check status. |
| T+?+1 | Engineer replies to the bot's comment: `/ci-doctor correct: confirmed, fix applied` | 🤖 **ci-doctor** — *✅ Correction logged. Pattern added to knowledge base. Next time this signature appears, I'll classify it correctly.* |

**Engineer's experience:** "The bot didn't fix it for me, but it told me exactly where to look — the dependency upgrade in my diff + the specific API that broke. I started debugging from its hypothesis, not from a 500-line error log. Saved me 15 minutes of log-diving."

---

### Journey 4 — The trend review (manager reads the report)

**Scenario:** Tech lead runs the weekly report before sprint planning.

```
$ ci-doctor report --days 7
```

**Output (Markdown):**

```markdown
# ci-doctor Weekly Report — 2026-06-25 to 2026-07-01

## Summary
| Metric | Value |
|--------|-------|
| Total failures | 5 |
| Auto-resolved | 3 (60%) |
| Human-resolved | 2 |
| Avg MTTR (auto) | 2 min |
| Avg MTTR (human) | 35 min |
| Token spend | $0.40 |
| Est. engineer time saved | 45 min |

## Failures by Category
| Category | Count | Auto-resolved |
|----------|-------|---------------|
| Flake | 3 | 3 (100%) |
| Lint | 1 | 1 (100%) |
| Dependency | 1 | 0 (escalated) |

## Top Recurring Signatures
1. `AssertionError.*passed.*failed` — 3 occurrences (flake)
2. `F401.*import` — 1 occurrence (lint)

## Cost vs Value
- Token spend: $0.40
- Engineer time saved: 45 min × $100/hr = $75
- **Multiplier: 187x**
```

**Tech lead's experience:** "Three of our five failures this week were flaky tests in the parser. I'm adding a story to next sprint to fix that test suite. The bot paid for itself 187x this week."

---

### Journey 5 — The agent learns over time (misclassification → correction → correct next time)

**Scenario:** ci-doctor misclassifies an infra timeout as a flake. The correction makes it smarter.

| Time | What happens | What the engineer sees |
|------|-------------|----------------------|
| **Week 2, T+0** | CI fails on a timeout. Webhook fires. | Red ❌ on the PR check status. |
| **Week 2, T+30s** | ci-doctor's rules match a flake signature (the error message contains "passed" and "failed"). Confidence 0.91. Auto-re-run triggered. | 🤖 **ci-doctor** — *Diagnosis: **Flaky test** (confidence 91%). Auto-re-running job `test`…* |
| **Week 2, T+5min** | Re-run also fails. ci-doctor reclassifies — but still says flake. | 🤖 **ci-doctor** — *⚠️ Re-run also failed. Reclassifying… Diagnosis still: flake. Escalating to @engineer.* |
| **Week 2, T+?** | Engineer replies: `/ci-doctor correct: category=infra_timeout, note="context deadline exceeded, not a flake"` | 🤖 **ci-doctor** — *✅ Correction logged. Category updated to **infra_timeout**. Confidence adjusted. I won't auto-re-run this signature next time.* |
| **Week 4, T+0** | Same error signature appears in a different PR. CI fails. | Red ❌ on the PR check status. |
| **Week 4, T+20s** | ci-doctor checks the knowledge base first. Finds the corrected pattern. Classifies as "infra timeout (confidence 0.88)." Does NOT auto-re-run. Escalates. | 🤖 **ci-doctor** — *Diagnosis: **Infra timeout** (confidence 88%). Root cause: context deadline exceeded in `integration_test.py:120`. This signature was corrected from a prior misclassification. **Escalating — not auto-re-running.** @engineer please review.* |

**Engineer's experience (week 4):** "The bot remembered. Last time it wasted a re-run on a timeout; this time it escalated immediately. It's learning."



## User Stories

- As a **PR author**, when my CI fails on a flaky test, I want the agent to detect it, re-run it via the GitHub Actions API, and confirm the pass automatically — so I don't context-switch to triage a non-issue.
- As a **PR author**, when my CI fails on a lint error, I want a comment with the exact file, line, rule, and a suggested fix — so I can apply it in one step and re-push.
- As a **PR author**, when my CI fails on a real bug, I want a root-cause hypothesis grounded in my diff and the failure log — so I start debugging from the agent's analysis, not from a wall of red text.
- As an **on-call engineer**, when a CI failure is ambiguous, I want the agent to tag me with a proposed diagnosis and the evidence — so I confirm or correct in one pass, not investigate from zero.
- As a **tech lead**, I want a Markdown report showing failure categories, auto-resolve rate, MTTR trend, and cost per resolution — so I can prioritize which test suites to fix and prove the ROI of the agent.
- As an **engineering manager**, I want the agent's corrections logged — so each misclassification makes the next one less likely.
- As an **engineer**, when I hit a failure I've seen before, I want the agent to already know the fix — because the knowledge base caught the pattern from last time.

## Functional Requirements

### M1 — Webhook Receiver + Failure Parser
- Listens for GitHub Actions `workflow_run` events (completed with conclusion=failure) via a webhook endpoint.
- Authenticates webhook payloads via GitHub's signature header.
- Parses the failure log (fetched via GitHub API) and extracts: failing job, failing step, error message, stack trace (if any), and the PR/commit context.
- Stores the raw failure event + parsed metadata for the classifier.

### M2 — Classifier
- Classifies each failure into one of: flake, lint, build error, dependency conflict, infra timeout, or unknown.
- **All 5 categories are in scope for v1** — classify everything, auto-resolve where confidence is high.
- **Hybrid approach:** rule-based (YAML config with regex signatures) for known patterns — fast, predictable, free. LLM-based (local model) for unknowns — handles novel failures, costs no tokens (local).
- Has access to both the failure log **and** the PR diff (fetched via GitHub API) for root-cause analysis.
- **One comment per failing job.** If a run has 3 failing jobs, ci-doctor posts 3 diagnosis comments — each with its own category, root cause, confidence, and recommended action.
- Posts a diagnosis comment on the PR per failure: category + root cause summary + confidence level + recommended action.
- **Confidence threshold:** 0.90 to auto-act (Level 1 re-run / Level 2 fix suggest). Below 0.90, propose only and escalate. Configurable per category in the rules YAML.

### M3 — Auto-Resolver
- **Flaky tests (Level 1):** Calls the GitHub Actions API to re-run the failed job. Polls for the re-run result. Comments with the outcome (passed/failed again). If the re-run passes, no further action. If it fails again, reclassifies and escalates.
- **Lint errors (Level 2):** Escalates to the cloud model to generate the suggested fix. Posts the fix as a code block in the PR comment (no auto-commit, no fix PR — engineer copy-pastes). Logs the suggestion + outcome.
- **Build errors / dependency conflicts / infra timeouts:** Classified + diagnosed. Auto-resolve (re-run or fix suggest) applies where confidence ≥ 0.90 and a safe action exists. Otherwise escalated to a human with the root-cause hypothesis.
- **Safety levels enforced:**
  - Level 0 (comment only) — default for all classifications below confidence threshold.
  - Level 1 (auto re-run) — enabled for flakes at confidence ≥ 0.90.
  - Level 2 (suggest code fix) — enabled for lint + dependency + build at confidence ≥ 0.90. Human confirms by applying the fix; the agent does not mutate code.
- **Never** auto-merge, auto-deploy, or push commits. All three levels are comment + API re-run only.
- Human-in-the-loop for all "unknown" classifications and any Level 2+ action.

### M4 — Knowledge Base
- Stores failure patterns in a local YAML file: `error_signature → { category, remediation, confidence, occurrences, last_seen, outcomes[] }`.
- Queryable: given a new failure's signature, find similar past failures and their resolutions.
- Learns from human corrections: when an engineer reacts with 👎 to a misclassification, ci-doctor prompts for the correct category and updates the pattern's confidence and category.
- Per-repo in v1 (the KB file lives alongside the ci-doctor service, scoped to the ci-doctor repo).

### M5 — Trend Report
- `ci-doctor report --days 7` generates a Markdown report showing:
  - Failures by category (table).
  - Auto-resolve rate (count + percentage).
  - MTTR trend (before vs after — estimated).
  - Top recurring failure signatures.
- Default time window: last 7 days. `--days` flag configurable.
- Output: a Markdown file that can be opened in Obsidian, committed to the repo, or piped to stdout.

### M6 — Cost Report
- Extends the trend report with: token cost per resolution, total token spend, estimated engineer time saved, and the cost-vs-value multiplier.
- **Engineer time saved:** estimated at 5 minutes per auto-resolved flake (the context-switch + triage time avoided) and 10 minutes per auto-suggested lint fix.
- The business case: "We spent $X on tokens, saved Y engineer-hours, at Zx multiplier."

### M7 — Testing, Docs, Packaging
- E2E tests against a corpus of labeled GitHub Actions failure logs (flakes, lint, build errors, dependency conflicts, timeouts).
- README + user guide (how to deploy, configure webhooks, set API tokens).
- Docker packaging — `docker build` produces a single image with the webhook receiver, classifier, and report generator.
- v1 deployment target: a single VM or local machine running the Docker container. Not Kubernetes for v1.

## Non-Functional Requirements

- **Latency:** Diagnosis comment posted within **60 seconds** of the webhook event. Includes: webhook receipt → log fetch → classification (local model) → comment post. Re-run verification (Level 1) may take longer (depends on the GitHub Actions job duration) — the initial comment posts within 60s; the re-run result comment posts when the job completes.
- **Cost:** Track token cost per resolution. Classification uses the local model (free). Fix generation uses the cloud model (costs tokens). A flaky test re-run that costs more in API fees than the engineer time it saved is a failure mode. Per-resolution cost ceiling: **$1.00** (configurable via env var). If a fix generation would exceed the ceiling, skip the cloud call and comment "fix generation skipped — cost ceiling exceeded."
- **Safety:** Never auto-merge, auto-deploy, or push commits. Level 0 is the default; autonomy is earned via confidence thresholds.
- **Observability:** `/health` HTTP endpoint (200 if the process is up). Structured JSON logs to stdout for every event: `event_id`, `timestamp`, `category`, `action`, `confidence`, `latency_ms`, `token_cost`. No external monitoring — Docker logs are the v1 observability layer.
- **Model strategy:** Local model (Llama 3.2 via MLX) for classification — free, private, fast. Cloud model (Deepseek V4 Flash) for fix generation only — powerful, costs tokens, used sparingly. **Rules-only is the floor:** if the MLX server is down, rules still classify + comment + re-run. The LLM is an optimization, never a requirement. If the cloud model is down, skip fix generation and comment "fix unavailable — manual triage." If GitHub API is rate-limited, log + retry with backoff.
- **Reliability:** v1 is webhook-only. If the receiver is down, events are missed — acceptable for v1. Add polling fallback in a post-v1 hardening pass.
- **Idempotency:** Dedup by GitHub event ID. Track processed event IDs in an in-memory set. A redelivered webhook is a no-op + 200 OK. Prevents duplicate comments, duplicate re-runs, and duplicate KB entries.
- **Concurrency:** In-memory queue with a single worker. Webhook receiver enqueues events; the worker processes them one at a time. No concurrent KB writes ever. Acceptable for v1 volume (~5 failures/week).
- **Auth:** Personal Access Token (PAT) with `repo`, `workflow` scopes. Stored in the `GITHUB_TOKEN` env var. Webhook signature verified via `GITHUB_WEBHOOK_SECRET` env var. GitHub App migration is post-v1.
- **Configuration:** All config via environment variables — no config file to mount. Required env vars: `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `MLX_ENDPOINT`, `CLOUD_API_KEY`, `CLOUD_MODEL`, `COST_CEILING`, `CONFIDENCE_THRESHOLD`, `KB_PATH`, `RULES_PATH`. The rules YAML (classification signatures) is the only file mounted — it's config, not secrets.
- **Privacy:** v1 is self-hosted on our own repo. No secret scrubbing before sending logs to the cloud model. Add scrubbing when we go multi-repo or external.

## Success Metrics

### Good (Done)
- [x] Agent listens to GitHub Actions failure events for the ci-doctor repo
- [x] Correctly classifies failures into at least 3 categories (flake, lint, build error)
- [ ] Auto-resolves flaky tests via GitHub Actions API re-run with false-positive rate < 10%
- [ ] Markdown report shows: failures by category, auto-resolve rate, MTTR trend
- [ ] Diagnosis comment posts within 60 seconds of the failure event

### Excellent (Stretch)
- [ ] 40%+ of CI failures auto-resolved without human intervention
- [ ] Knowledge base contains 50+ failure patterns with remediation
- [ ] Agent suggests code fixes for non-flake failures (lint errors, dependency conflicts)
- [ ] Cost report shows token cost per resolution — and it's cheaper than engineer time
- [ ] Agent demonstrates learning: a corrected misclassification leads to a correct classification next time

## Risks

- **False positives** — auto-re-running a real failure as if it's a flake wastes CI minutes and erodes trust. Mitigation: false-positive rate < 10% target; 0.90 confidence threshold; KB corrections feed back.
- **Cost runaway** — a flaky test that retries 20 times could cost more in API fees than the engineer time it saved. Mitigation: $1.00 per-resolution cost ceiling; local model for classification; cloud model only for fix generation.
- **Scope creep** — adding failure categories before mastering flakes end-to-end. Mitigation: the rules YAML makes adding categories trivial, but the classifier must prove accuracy on flakes first.
- **Agent trust** — if the diagnosis comments are noisy or wrong, engineers mute the bot. Mitigation: log every decision + outcome; iterate on the rules + prompt.
- **Webhook reliability** — if the receiver is down, events are missed with no fallback in v1. Mitigation: acceptable for v1 (self-hosted, single repo); add polling in hardening.
- **GitHub API rate limits** — re-runs + log fetches + comment posts all consume API quota. Mitigation: cache log fetches; batch where possible; monitor rate limit headers.

## Milestones

| Milestone | Deliverable | Target |
|-----------|-------------|--------|
| M1 | Webhook receiver + failure parser (GitHub Actions workflow_run) | Week 1 |
| M2 | Classifier (rule-based YAML + local LLM hybrid) + PR diagnosis comment | Week 1 |
| M3 | Auto-resolver (GitHub Actions API re-run for flakes, cloud-model fix suggest for lint) | Week 1 |
| M4 | Knowledge base (YAML file, queryable, learns from corrections) | Week 1 |
| M5 | Trend report (Markdown: failures by category, auto-resolve rate, MTTR) | Week 1 |
| M6 | Cost report (token cost vs engineer time saved, cost ceiling enforcement) | Week 1 |
| M7 | E2E tests (labeled failure corpus), README + user guide, Docker packaging, v1 tag, ship | Week 1 |

## Related

- Spec: [`spec.md`](./spec.md)
- Project page: [`vault/projects/04-CI-Agent.md`](https://github.com/deghosal-2026/my-2nd-brain/blob/main/vault/projects/04-CI-Agent.md)
- Repo: [ci-doctor](https://github.com/deghosal-2026/ci-doctor)
- Strategic context: AI-Native SDLC Maturity Plan (Phase 2: Agentic CI/CD)
- 90-Day Plan: CI-Agent ships Week 1 (2026-06-28 to 2026-07-04)
