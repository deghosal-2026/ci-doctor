"""
Evaluation harness: feed eval corpus through classifier, measure accuracy.

Usage:
    python scripts/evaluate.py                          # rules only
    python scripts/evaluate.py --use-llm                 # KB -> rules -> LLM (MLX/Ollama)
    python scripts/evaluate.py --use-llm --batch 10      # process N at a time
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import classify
from app.classifier.rules import load_rules, match_rules
from app.config import load as load_config
from app.knowledge.base import KnowledgeBase

LABELS_PATH = Path("tests/fixtures/logs/labels.yaml")
EVAL_DIR = Path("tests/fixtures/logs/eval")
RULES_PATH = Path("rules.yaml")
TAIL_LINES = 2000


def read_log_tail(rel: str) -> str | None:
    path = EVAL_DIR / rel
    if path.exists():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-TAIL_LINES:]) if len(lines) > TAIL_LINES else "\n".join(lines)
    stem = path.stem
    chunks = sorted(path.parent.glob(f"{stem}.part.*"))
    if chunks:
        text = chunks[-1].read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return "\n".join(lines[-TAIL_LINES:]) if len(lines) > TAIL_LINES else text
    return None


async def evaluate(use_llm: bool = False, batch_size: int = 5):
    if use_llm:
        cfg = load_config()
        kb = KnowledgeBase(cfg.kb_path)
        mlx = cfg.mlx_endpoint
        print(f"Using LLM endpoint: {mlx}/v1/chat/completions", file=sys.stderr, flush=True)
    else:
        cfg = None
        kb = KnowledgeBase("knowledge_base.yaml")
        mlx = None

    rules = load_rules(str(RULES_PATH))

    if not LABELS_PATH.exists():
        print("No labels.yaml found. Run scripts/label_corpus.py first.", file=sys.stderr)
        return

    with open(LABELS_PATH) as f:
        labels_data = yaml.safe_load(f) or {}

    labels = labels_data.get("labels", {})
    if not labels:
        print("labels.yaml is empty.", file=sys.stderr)
        return

    results = {c: {"correct": 0, "total": 0, "fp": 0} for c in
               ["flake", "lint", "build", "dependency", "infra_timeout", "unknown"]}
    overall = {"correct": 0, "total": 0}

    items = sorted(labels.items())
    total = len(items)

    import asyncio

    for start in range(0, total, batch_size):
        batch = items[start:start + batch_size]
        tasks = []
        for rel_path, meta in batch:
            expected = meta.get("category")
            text = read_log_tail(rel_path)
            if text is None:
                continue
            if use_llm:
                tasks.append(classify(text, kb, str(RULES_PATH), mlx))
            else:
                tasks.append(None)

        if use_llm and tasks:
            classifications = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            classifications = []

        ci = 0
        for rel_path, meta in batch:
            expected = meta.get("category")
            text = read_log_tail(rel_path)
            if text is None:
                continue

            if use_llm:
                result = classifications[ci]
                if isinstance(result, BaseException):
                    classification = match_rules(text, rules)
                else:
                    classification = result  # type: ignore[assignment]
                ci += 1
            else:
                classification = match_rules(text, rules)

            predicted = classification.category if classification else "unknown"
            results.setdefault(predicted, {"correct": 0, "total": 0, "fp": 0})
            results.setdefault(expected, {"correct": 0, "total": 0, "fp": 0})
            results[expected]["total"] += 1
            overall["total"] += 1
            if predicted == expected:
                results[expected]["correct"] += 1
                overall["correct"] += 1
            else:
                results[predicted]["fp"] += 1

        i = min(start + batch_size, total)
        print(f"  [{i}/{total}]", file=sys.stderr, flush=True)

    print("\n=== Evaluation Results ===\n")
    print(f"{'Category':<20} {'Accuracy':>10} {'Total':>8} {'FP':>8}")
    print("-" * 50)
    for cat in ["flake", "lint", "build", "dependency", "infra_timeout", "unknown"]:
        r = results.get(cat, {"correct": 0, "total": 0, "fp": 0})
        acc = r["correct"] / r["total"] * 100 if r["total"] else 0
        print(f"{cat:<20} {acc:>8.1f}% {r['total']:>8} {r['fp']:>8}")
    overall_acc = overall["correct"] / overall["total"] * 100 if overall["total"] else 0
    print("-" * 50)
    print(f"{'Overall':<20} {overall_acc:>8.1f}% {overall['total']:>8}")
    print("\nTarget: >= 85% overall, < 10% false-positive per category")


if __name__ == "__main__":
    import asyncio
    use_llm = "--use-llm" in sys.argv
    batch = 10
    for i, a in enumerate(sys.argv):
        if a == "--batch" and i + 1 < len(sys.argv):
            batch = int(sys.argv[i + 1])
    asyncio.run(evaluate(use_llm=use_llm, batch_size=batch))
