"""
Download failed CI workflow logs from public repos.
Picks random (repo, date) pairs within last 30 days — safe to run multiple instances in parallel.
Saves to tests/fixtures/logs/{rules,eval}/{category}/{repo}_{run_id}.txt

Usage:
    python scripts/pull_failures.py [--rules 300] [--eval 1000]
    nohup python scripts/pull_failures.py > downloads.log 2>&1 &
"""

import datetime
import io
import random
import re
import string
import subprocess
import sys
import zipfile
from pathlib import Path

REPOS = [
    "python/cpython",
    "encode/httpx",
    "pytest-dev/pytest",
    "astral-sh/ruff",
    "fastapi/fastapi",
    "pypa/pip",
    "pandas-dev/pandas",
    "pydantic/pydantic",
    "microsoft/vscode",
    "nodejs/node",
]

MAX_PER_DAY = 20
FIXTURE_DIR = Path("tests/fixtures/logs")
RULES_DIR = FIXTURE_DIR / "rules"
EVAL_DIR = FIXTURE_DIR / "eval"
CATEGORIES = ["flake", "lint", "build", "dependency", "timeout"]


def log(msg: str):
    print(msg, flush=True)


def gh(*args: str, timeout: int = 60) -> str:
    r = subprocess.run(["gh"] + list(args), capture_output=True, text=True, timeout=timeout)
    return "" if r.returncode else r.stdout.strip()


def gh_bin(*args: str, timeout: int = 60) -> bytes:
    r = subprocess.run(["gh"] + list(args), capture_output=True, timeout=timeout)
    return b"" if r.returncode else r.stdout


def get_day_failures(owner: str, repo: str, date: str) -> list[int]:
    raw = gh(
        "api",
        f"repos/{owner}/{repo}/actions/runs?per_page=100&status=completed&conclusion=failure&created={date}",
        "--jq",
        ".workflow_runs[].id",
    )
    return [int(x) for x in raw.strip().split()] if raw else []


def download_logs(owner: str, repo: str, run_id: int) -> str | None:
    data = gh_bin("api", f"repos/{owner}/{repo}/actions/runs/{run_id}/logs")
    if not data:
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        parts = []
        for name in sorted(z.namelist()):
            if name.endswith(".txt"):
                parts.append(z.read(name).decode("utf-8", errors="replace"))
        return "\n".join(parts) if parts else None
    except zipfile.BadZipFile:
        return None


def guess_category(text: str) -> str | None:
    t = text.lower()
    patterns = {
        "flake": [
            r"(?:failed|flaky|rerun|re.run|re_run).*(?:test|assert)",
            r"assertion (?:failed|error)",
            r"test.*flaky",
            r"unexpected.*assertion",
        ],
        "lint": [
            r"(?:ruff|pylint|flake8|mypy|black).*(?:error|failure|found)",
            r"f401|e501|e302|w291",
            r"line too long",
            r"unused import",
        ],
        "build": [
            r"(?:compilation|build).*(?:error|failed)",
            r"modulenotfounderror|importerror",
            r"cannot find module",
            r"typeerror|attributeerror|syntaxerror",
            r"exit code 1",
        ],
        "dependency": [
            r"(?:version|dependency|requirement).*(?:conflict|not found|resolution)",
            r"no matching distribution",
            r"pip.*error",
            r"could not find.*package",
            r"lockfile.*conflict",
        ],
        "timeout": [
            r"(?:timeout|timed?out|cancelled|canceled)",
            r"deadline exceeded",
            r"the operation was canceled",
            r"context deadline",
        ],
    }
    scores = {}
    for cat, pats in patterns.items():
        s = sum(1 for p in pats if re.search(p, t))
        if s:
            scores[cat] = s
    return max(scores, key=lambda k: scores[k]) if scores else None


def already_saved(repo_name: str, run_id: int) -> bool:
    for d in [RULES_DIR, EVAL_DIR]:
        for cat in CATEGORIES:
            pfx = d / cat / f"{repo_name}_{run_id}"
            if pfx.with_suffix(".txt").exists():
                return True
            # chunked file: e.g. cpython_12345.part.aa
            if list((d / cat).glob(f"{pfx.name}.part.*")):
                return True
    return False


def needs_more(collected: dict) -> bool:
    per_cat_rules = rules_target // len(CATEGORIES)
    per_cat_eval = eval_target // len(CATEGORIES)
    for cat in CATEGORIES:
        if collected[cat]["rules"] < per_cat_rules:
            return True
        if collected[cat]["eval"] < per_cat_eval:
            return True
    return False


rules_target = 300
eval_target = 1000


def main():
    global rules_target, eval_target
    rules_target = int(sys.argv[sys.argv.index("--rules") + 1]) if "--rules" in sys.argv else 300
    eval_target = int(sys.argv[sys.argv.index("--eval") + 1]) if "--eval" in sys.argv else 1000

    for d in [RULES_DIR / c for c in CATEGORIES] + [EVAL_DIR / c for c in CATEGORIES]:
        d.mkdir(parents=True, exist_ok=True)

    collected = {c: {"rules": 0, "eval": 0} for c in CATEGORIES}
    # count what's already on disk
    def count_logs(base_dir: Path, cat: str) -> int:
        """Count unique log entries (single .txt files OR chunked .part.* sets)."""
        seen: set[str] = set()
        for p in (base_dir / cat).iterdir():
            name = p.name
            if name.endswith(".txt"):
                seen.add(name.removesuffix(".txt"))
            elif ".part." in name:
                seen.add(name.split(".part.")[0])
        return len(seen)

    for d, label in [(RULES_DIR, "rules"), (EVAL_DIR, "eval")]:
        for cat in CATEGORIES:
            collected[cat][label] = count_logs(d, cat)

    today = datetime.date.today()
    log(f"Starting download: rules={rules_target}, eval={eval_target}")
    log(f"Already on disk:")
    for cat in CATEGORIES:
        log(f"  {cat}: {collected[cat]['rules']}R / {collected[cat]['eval']}E")
    log(f"Running — Ctrl+C to stop, safe to restart\n")

    # random walk: pick random (repo, day) pairs
    date_pool = [(today - datetime.timedelta(days=d)).isoformat() for d in range(30)]
    attempts = 0

    while needs_more(collected) and attempts < 5000:
        attempts += 1
        repo_full = random.choice(REPOS)
        date = random.choice(date_pool)
        owner, repo_name = repo_full.split("/", 1)

        run_ids = get_day_failures(owner, repo_name, date)
        if not run_ids:
            continue

        random.shuffle(run_ids)
        day_saved = 0

        for rid in run_ids:
            if not needs_more(collected):
                break
            if already_saved(repo_name, rid):
                continue
            if day_saved >= MAX_PER_DAY:
                break

            try:
                logs = download_logs(owner, repo_name, rid)
            except Exception:
                continue
            if not logs:
                continue

            category = guess_category(logs)
            if not category:
                continue

            per_cat_rules = rules_target // len(CATEGORIES)
            per_cat_eval = eval_target // len(CATEGORIES)
            if collected[category]["rules"] < per_cat_rules:
                target = "rules"
            elif collected[category]["eval"] < per_cat_eval:
                target = "eval"
            else:
                continue

            out = (RULES_DIR if target == "rules" else EVAL_DIR) / category / f"{repo_name}_{rid}.txt"
            data = logs.encode("utf-8")
            if len(data) <= 20 * 1024 * 1024:
                out.write_bytes(data)
            else:
                out.unlink(missing_ok=True)
                chunk_size = 20 * 1024 * 1024
                letters = string.ascii_lowercase
                for idx, i in enumerate(range(0, len(data), chunk_size)):
                    suffix = f"{letters[idx // 26]}{letters[idx % 26]}"
                    part = out.parent / f"{repo_name}_{rid}.part.{suffix}"
                    part.write_bytes(data[i:i + chunk_size])

            collected[category][target] += 1
            day_saved += 1
            rem_r = per_cat_rules - collected[category]["rules"]
            rem_e = per_cat_eval - collected[category]["eval"]
            log(f"#{rid} [{category}] -> {target} ({rem_r}R/{rem_e}E remain for {category})  [{repo_full} {date}]")

    log("\n=== Final Summary ===")
    for cat in CATEGORIES:
        log(f"  {cat}: {collected[cat]['rules']}R / {collected[cat]['eval']}E")
    total = sum(c["rules"] + c["eval"] for c in collected.values())
    log(f"  Total: {total}")
    log(f"  Saved to {FIXTURE_DIR}")
    if needs_more(collected):
        log(f"  Stopped at {attempts} attempts — targets not reached. Run again to continue.")


if __name__ == "__main__":
    main()
