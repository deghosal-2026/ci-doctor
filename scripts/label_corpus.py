"""
Label eval corpus: generate ground-truth labels from directory structure.

The download script (pull_failures.py) already sorted logs into category dirs
using regex heuristics. This script reads that structure and writes labels.yaml.

Usage:
    python scripts/label_corpus.py
"""

import re
from pathlib import Path

import yaml

EVAL_DIR = Path("tests/fixtures/logs/eval")
LABELS_PATH = Path("tests/fixtures/logs/labels.yaml")

REPO_MAP = {
    "cpython": "python/cpython",
    "httpx": "encode/httpx",
    "pytest": "pytest-dev/pytest",
    "ruff": "astral-sh/ruff",
    "fastapi": "fastapi/fastapi",
    "pip": "pypa/pip",
    "pandas": "pandas-dev/pandas",
    "pydantic": "pydantic/pydantic",
    "vscode": "microsoft/vscode",
    "node": "nodejs/node",
}

DIR_TO_CATEGORY = {
    "timeout": "infra_timeout",
}


def parse_filename(name: str) -> tuple[str, str]:
    """Extract repo name and run_id from filename like 'cpython_27303945910.txt'."""
    base = name.removesuffix(".txt")
    if ".part." in base:
        base = base.split(".part.")[0]
    m = re.match(r"(.+)_(\d+)$", base)
    if m:
        return m.group(1), m.group(2)
    return base, ""


def main():
    labels = {}
    for cat_dir in sorted(EVAL_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        category = cat_dir.name
        seen = set()
        for f in sorted(cat_dir.iterdir()):
            name = f.name
            if not name.endswith(".txt") and ".part." not in name:
                continue
            repo_short, run_id = parse_filename(name)
            base = name.split(".part.")[0].removesuffix(".txt")
            if base in seen:
                continue
            seen.add(base)
            key = f"{category}/{base}.txt"
            labels[key] = {
                "category": DIR_TO_CATEGORY.get(category, category),
                "source_repo": REPO_MAP.get(repo_short, f"unknown/{repo_short}"),
                "run_id": run_id,
            }

    header = (
        "# Ground-truth labels for eval corpus.\n"
        "# Auto-generated from directory structure.\n"
        "# Review and correct manually for ground truth.\n\n"
    )
    with open(LABELS_PATH, "w") as f:
        f.write(header)
        yaml.dump({"labels": dict(sorted(labels.items()))}, f, default_flow_style=False)

    cats = {}
    for v in labels.values():
        c = v["category"]
        cats[c] = cats.get(c, 0) + 1
    print(f"Generated {len(labels)} labels:")
    for c in sorted(cats):
        print(f"  {c}: {cats[c]}")
    print(f"Written to {LABELS_PATH}")


if __name__ == "__main__":
    main()
