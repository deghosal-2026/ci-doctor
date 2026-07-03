"""
Evaluation harness: feed eval corpus through classifier, measure accuracy.

Usage:
    python scripts/evaluate.py
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier.rules import load_rules, match_rules
from app.config import load as load_config


LABELS_PATH = Path("tests/fixtures/logs/labels.yaml")
EVAL_DIR = Path("tests/fixtures/logs/eval")
RULES_PATH = Path("rules.yaml")


def evaluate():
    cfg = load_config()
    rules = load_rules(str(RULES_PATH))

    if not LABELS_PATH.exists():
        print("No labels.yaml found. Run issue #56 first.")
        return

    with open(LABELS_PATH) as f:
        labels_data = yaml.safe_load(f) or {}

    labels = labels_data.get("labels", {})
    if not labels:
        print("labels.yaml is empty. Run issue #56 first.")
        return

    results = {cat: {"correct": 0, "total": 0, "false_positives": 0} for cat in
               ["flake", "lint", "build", "dependency", "infra_timeout", "unknown"]}
    overall = {"correct": 0, "total": 0}

    for rel_path, meta in labels.items():
        expected = meta.get("category")
        log_path = EVAL_DIR / rel_path
        if not log_path.exists():
            continue

        text = log_path.read_text(encoding="utf-8", errors="replace")
        classification = match_rules(text, rules)

        predicted = classification.category if classification else "unknown"
        results.setdefault(predicted, {"correct": 0, "total": 0, "false_positives": 0})
        results.setdefault(expected, {"correct": 0, "total": 0, "false_positives": 0})

        results[expected]["total"] += 1
        overall["total"] += 1

        if predicted == expected:
            results[expected]["correct"] += 1
            overall["correct"] += 1
        else:
            results[predicted]["false_positives"] += 1

    print("=== Evaluation Results ===\n")
    print(f"{'Category':<20} {'Accuracy':>10} {'Total':>8} {'FP':>8}")
    print("-" * 50)
    for cat in ["flake", "lint", "build", "dependency", "infra_timeout", "unknown"]:
        r = results.get(cat, {"correct": 0, "total": 0, "false_positives": 0})
        acc = r["correct"] / r["total"] * 100 if r["total"] else 0
        print(f"{cat:<20} {acc:>8.1f}% {r['total']:>8} {r['false_positives']:>8}")

    overall_acc = overall["correct"] / overall["total"] * 100 if overall["total"] else 0
    print("-" * 50)
    print(f"{'Overall':<20} {overall_acc:>8.1f}% {overall['total']:>8}")
    print(f"\nTarget: >= 85% overall, < 10% false-positive per category")


if __name__ == "__main__":
    evaluate()
