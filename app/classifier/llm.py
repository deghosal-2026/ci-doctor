import json

import httpx

from app.classifier.models import Classification


async def classify_with_mlx(
    log_snippet: str, endpoint: str, prompt_template: str | None = None
) -> Classification | None:
    if not prompt_template:
        prompt_template = _DEFAULT_PROMPT

    prompt = prompt_template.format(log_snippet=log_snippet)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{endpoint}/v1/chat/completions",
                json={
                    "model": "llama-3.2-3b-instruct",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            if not r.is_success:
                return None
            body = r.json()
            content = body["choices"][0]["message"]["content"]
            return _parse_response(content)
    except Exception:
        return None


def _parse_response(text: str) -> Classification | None:
    try:
        data = json.loads(text)
        return Classification(
            category=data.get("category", "unknown"),
            root_cause=data.get("root_cause", ""),
            confidence=float(data.get("confidence", 0)),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


_DEFAULT_PROMPT = """Classify this CI failure log snippet into exactly one category:
- flake (flaky test, non-deterministic failure)
- lint (style, unused import, formatting)
- build (compilation, type error, import error)
- dependency (version conflict, missing package)
- infra_timeout (runner timeout, cancelled)

Respond with JSON:
{"category": "...", "root_cause": "...", "confidence": 0.0-1.0}

Log snippet:
{log_snippet}
"""
