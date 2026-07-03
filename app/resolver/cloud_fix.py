import httpx

from app.config import Settings


def estimate_cost(text: str) -> float:
    tokens = len(text) // 4
    return round(tokens * 0.000002, 4)


async def generate_fix(
    log_snippet: str, diff: str, cfg: Settings
) -> str | None:
    estimated = estimate_cost(log_snippet + diff)
    if estimated > cfg.cost_ceiling:
        return None

    if not cfg.cloud_api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.cloud_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.cloud_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Fix the error in this CI failure.\n\nLog:\n{log_snippet}\n\nPR diff:\n{diff}\n\nRespond with a code fix.",
                        }
                    ],
                    "temperature": 0.1,
                },
            )
            if r.is_success:
                return r.json()["choices"][0]["message"]["content"]
    except Exception:
        pass
    return None
