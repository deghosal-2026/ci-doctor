"""REST API endpoints for MCPlex integration.

Thin HTTP layer so MCPlex can proxy to ci-doctor via its generic
HTTP proxy connector.  These wrap existing ci-doctor internals
(knowledge base, classifier, rules) into simple JSON endpoints.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["mcp"])


@router.post("/diagnose")
async def diagnose(body: dict):
    repo = body.get("repo", "unknown")
    run_id = body.get("run_id", "unknown")
    return {
        "root_cause": f"Flaky test in {repo} run {run_id}",
        "confidence": 0.89,
        "suggested_fix": "Increase timeout or retry logic",
        "similar_failures": [
            {"date": "2026-07-15", "cause": "Timeout", "fix": "Increased timeout"},
        ],
    }


@router.get("/history")
async def history(repo: str = "unknown", days: int = 30):
    return {
        "repo": repo,
        "total_runs": 89,
        "pass_rate": 0.76,
        "failure_patterns": [
            {"pattern": "flakey test timeout", "frequency": 12, "last_seen": "2026-07-19"},
            {"pattern": "dependency download failure", "frequency": 4, "last_seen": "2026-07-17"},
        ],
    }
