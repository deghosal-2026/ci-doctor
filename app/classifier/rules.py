import re

import yaml

from app.classifier.models import Classification


def load_rules(path: str) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def match_rules(text: str, rules: list[dict]) -> Classification | None:
    for rule in rules:
        category = rule["category"]
        for pattern in rule["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                return Classification(
                    category=category,
                    root_cause=f"Matched rule pattern: {pattern}",
                    confidence=rule.get("confidence", 0.90),
                )
    return None
