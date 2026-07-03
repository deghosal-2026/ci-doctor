import datetime

import yaml
from pathlib import Path


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
