"""
Label eval corpus using a local LLM (omlx/Ollama, OpenAI-compatible)
or cloud API (Deepseek, OpenAI, etc.).

Sends the tail of each eval log to the LLM and asks it to classify
into one of: flake, lint, build, dependency, infra_timeout.

Usage:
    python scripts/label_with_llm.py
    python scripts/label_with_llm.py --endpoint http://127.0.0.1:8000 --model DeepSeek-R1-Distill-Qwen-14B-4bit
    python scripts/label_with_llm.py --cloud   # uses CLOUD_API_KEY / CLOUD_MODEL from env
    python scripts/label_with_llm.py --cloud --model deepseek-v4-flash --api-key sk-...
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EVAL_DIR = Path("tests/fixtures/logs/eval")
LABELS_PATH = Path("tests/fixtures/logs/labels.yaml")
TAIL_LINES = 200
DEFAULT_ENDPOINT = "http://127.0.0.1:8000"
DEFAULT_CLOUD_ENDPOINT = "https://api.deepseek.com"
DEFAULT_MODEL = "DeepSeek-R1-Distill-Qwen-14B-4bit"
DEFAULT_CLOUD_MODEL = "deepseek-v4-flash"
DEFAULT_API_KEY = "omlx-test"

CATEGORIES = ["flake", "lint", "build", "dependency", "infra_timeout"]

PROMPT = """Classify this CI failure log into exactly one category:
- flake: flaky test, non-deterministic failure, passes on retry
- lint: style violation, unused import, formatting, type checker error
- build: compilation error, import error, syntax error, assertion failure, module not found
- dependency: version conflict, missing package, resolution failure, dependency mismatch
- infra_timeout: runner timeout, job cancelled, deadline exceeded, infrastructure issue

Respond with ONLY a JSON object, no other text:
{{"category": "<one of flake|lint|build|dependency|infra_timeout>", "reason": "<short explanation>"}}

Log (last {n} lines):
{log}
"""


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


def collect_files() -> list[tuple[str, str]]:
    """Return [(rel_path, dir_category), ...] for all eval logs."""
    files = []
    for cat_dir in sorted(EVAL_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        category = cat_dir.name
        seen = set()
        for f in sorted(cat_dir.iterdir()):
            name = f.name
            if not name.endswith(".txt") and ".part." not in name:
                continue
            base = name.split(".part.")[0].removesuffix(".txt")
            if base in seen:
                continue
            seen.add(base)
            files.append((f"{category}/{base}.txt", category))
    return files


async def classify_log(
    client: httpx.AsyncClient,
    text: str,
    endpoint: str,
    model: str,
    api_key: str,
    sem: asyncio.Semaphore,
) -> dict | None:
    prompt = PROMPT.format(log=text[:8000], n=TAIL_LINES)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with sem:
        try:
            r = await client.post(
                f"{endpoint}/v1/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                },
                timeout=60,
            )
            if not r.is_success:
                print(f"  HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr, flush=True)
                return None
            content = r.json()["choices"][0]["message"]["content"]
            return _parse_response(content)
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return None


def _parse_response(text: str) -> dict | None:
    # try to extract JSON from the response
    m = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if not m:
        # try to find category keyword directly
        for cat in CATEGORIES:
            if cat in text.lower():
                return {"category": cat, "reason": "keyword match"}
        return None
    try:
        data = json.loads(m.group(0))
        cat = data.get("category", "").strip().lower()
        if cat in CATEGORIES:
            return data
        # handle infra_timeout variations
        if "timeout" in cat or "infra" in cat:
            data["category"] = "infra_timeout"
            return data
        return None
    except json.JSONDecodeError:
        return None


async def main():
    endpoint = DEFAULT_ENDPOINT
    model = DEFAULT_MODEL
    api_key = DEFAULT_API_KEY
    concurrency = 5
    use_cloud = False

    for i, a in enumerate(sys.argv):
        if a == "--cloud":
            use_cloud = True
        elif a == "--cloud-endpoint" and i + 1 < len(sys.argv):
            endpoint = sys.argv[i + 1]
        elif a == "--endpoint" and i + 1 < len(sys.argv):
            endpoint = sys.argv[i + 1]
        elif a == "--model" and i + 1 < len(sys.argv):
            model = sys.argv[i + 1]
        elif a == "--api-key" and i + 1 < len(sys.argv):
            api_key = sys.argv[i + 1]
        elif a == "--concurrency" and i + 1 < len(sys.argv):
            concurrency = int(sys.argv[i + 1])

    if use_cloud:
        endpoint = endpoint if any(a == "--cloud-endpoint" for a in sys.argv) else DEFAULT_CLOUD_ENDPOINT
        model = model if any(a == "--model" for a in sys.argv) else os.environ.get("CLOUD_MODEL", DEFAULT_CLOUD_MODEL)
        api_key = api_key if any(a == "--api-key" for a in sys.argv) else os.environ.get("CLOUD_API_KEY", "")
        if not api_key:
            print("ERROR: --api-key or CLOUD_API_KEY env var required in --cloud mode", file=sys.stderr)
            sys.exit(1)

    files = collect_files()
    total = len(files)
    print(f"Labeling {total} eval logs with {model} at {endpoint}", file=sys.stderr, flush=True)
    print(f"Concurrency: {concurrency}", file=sys.stderr, flush=True)

    sem = asyncio.Semaphore(concurrency)
    labels = {}
    correct = 0
    changed = 0

    async with httpx.AsyncClient() as client:
        batch_size = 10
        for start in range(0, total, batch_size):
            batch = files[start:start + batch_size]
            texts = []
            for rel, dir_cat in batch:
                text = read_log_tail(rel)
                texts.append((rel, dir_cat, text))

            tasks = []
            valid = []
            for rel, dir_cat, text in texts:
                if text is None:
                    continue
                tasks.append(classify_log(client, text, endpoint, model, api_key, sem))
                valid.append((rel, dir_cat))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (rel, dir_cat), result in zip(valid, results):
                if isinstance(result, BaseException) or result is None:
                    labels[rel] = {
                        "category": "timeout" if dir_cat == "timeout" else dir_cat,
                        "source_repo": "",
                        "run_id": "",
                        "llm_labeled": False,
                    }
                    continue
                llm_cat = result["category"]
                labels[rel] = {
                    "category": llm_cat,
                    "source_repo": "",
                    "run_id": "",
                    "llm_labeled": True,
                    "reason": result.get("reason", ""),
                }
                mapped_dir = "infra_timeout" if dir_cat == "timeout" else dir_cat
                if llm_cat == mapped_dir:
                    correct += 1
                else:
                    changed += 1

            done = min(start + batch_size, total)
            print(f"  [{done}/{total}] agree={correct} changed={changed}", file=sys.stderr, flush=True)

    source = "cloud" if use_cloud else "local"
    with open(LABELS_PATH, "w") as f:
        f.write("# Ground-truth labels for eval corpus.\n")
        f.write(f"# Labeled by {source} LLM ({model}).\n\n")
        yaml.dump({"labels": dict(sorted(labels.items()))}, f, default_flow_style=False)

    print(f"\nDone. {len(labels)} labels written to {LABELS_PATH}", file=sys.stderr)
    print(f"LLM agreed with dir-based heuristic: {correct}/{total}", file=sys.stderr)
    print(f"LLM changed: {changed}/{total}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
