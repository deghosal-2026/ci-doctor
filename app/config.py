import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    github_token: str
    github_webhook_secret: str
    mlx_endpoint: str = "http://localhost:8000"
    cloud_api_key: str = ""
    cloud_model: str = "deepseek-v4-flash"
    cost_ceiling: float = 1.00
    confidence_threshold: float = 0.90
    kb_path: str = "knowledge_base.yaml"
    rules_path: str = "rules.yaml"
    decisions_path: str = "decisions.yaml"
    engineer_hourly_rate: int = 100
    port: int = 8080


def load() -> Settings:
    token = os.environ.get("GITHUB_TOKEN", "")
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    errors = []
    if not token:
        errors.append("GITHUB_TOKEN is required")
    if not secret:
        errors.append("GITHUB_WEBHOOK_SECRET is required")
    if errors:
        raise RuntimeError("; ".join(errors))

    return Settings(
        github_token=token,
        github_webhook_secret=secret,
        mlx_endpoint=os.environ.get("MLX_ENDPOINT", "http://localhost:8000"),
        cloud_api_key=os.environ.get("CLOUD_API_KEY", ""),
        cloud_model=os.environ.get("CLOUD_MODEL", "deepseek-v4-flash"),
        cost_ceiling=float(os.environ.get("COST_CEILING", "1.00")),
        confidence_threshold=float(os.environ.get("CONFIDENCE_THRESHOLD", "0.90")),
        kb_path=os.environ.get("KB_PATH", "knowledge_base.yaml"),
        rules_path=os.environ.get("RULES_PATH", "rules.yaml"),
        decisions_path=os.environ.get("DECISIONS_PATH", "decisions.yaml"),
        engineer_hourly_rate=int(os.environ.get("ENGINEER_HOURLY_RATE", "100")),
        port=int(os.environ.get("PORT", "8080")),
    )
