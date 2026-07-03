import datetime
from pathlib import Path

import yaml


async def write_decision(
    path: str,
    event_id: str,
    repo: str,
    commit_sha: str,
    pr_number: int,
    job_name: str,
    category: str,
    confidence: float,
    action: str,
):
    filepath = Path(path)
    data = {"decisions": []}
    if filepath.exists():
        with open(filepath) as f:
            data = yaml.safe_load(f) or {"decisions": []}

    data["decisions"].append(
        {
            "event_id": event_id,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "repo": repo,
            "commit_sha": commit_sha,
            "pr_number": pr_number,
            "job_name": job_name,
            "category": category,
            "confidence": confidence,
            "action": action,
            "outcome": "pending",
        }
    )

    with open(filepath, "w") as f:
        yaml.dump(data, f)


async def update_outcome(path: str, event_id: str, outcome: str, latency_ms: int = 0, token_cost: float = 0.0):
    filepath = Path(path)
    if not filepath.exists():
        return
    with open(filepath) as f:
        data = yaml.safe_load(f) or {"decisions": []}
    for d in data["decisions"]:
        if d["event_id"] == event_id:
            d["outcome"] = outcome
            if latency_ms:
                d["latency_ms"] = latency_ms
            if token_cost:
                d["token_cost"] = token_cost
            break
    with open(filepath, "w") as f:
        yaml.dump(data, f)
