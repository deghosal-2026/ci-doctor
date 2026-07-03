import datetime
from pathlib import Path

import yaml


def load_decisions(path: str, days: int = 7) -> list[dict]:
    filepath = Path(path)
    if not filepath.exists():
        return []
    with open(filepath) as f:
        data = yaml.safe_load(f) or {}
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return [
        d for d in data.get("decisions", [])
        if datetime.datetime.fromisoformat(d.get("timestamp", "")).replace(tzinfo=None) >= cutoff
    ]


def aggregate(decisions: list[dict]) -> dict:
    total = len(decisions)
    by_category = {}
    auto_resolved = 0
    for d in decisions:
        cat = d.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1
        if d.get("action") in ("auto_rerun", "suggest_fix") and d.get("outcome") == "resolved":
            auto_resolved += 1

    top_signatures = {}
    for d in decisions:
        sig = d.get("category", "") + ":" + d.get("root_cause", "")[:60]
        top_signatures[sig] = top_signatures.get(sig, 0) + 1
    top = sorted(top_signatures.items(), key=lambda x: -x[1])[:10]

    return {
        "total": total,
        "auto_resolved": auto_resolved,
        "human_resolved": total - auto_resolved,
        "auto_resolve_rate": round(auto_resolved / total * 100, 1) if total else 0,
        "by_category": by_category,
        "top_signatures": top,
    }
