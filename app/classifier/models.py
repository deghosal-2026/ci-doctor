from dataclasses import dataclass


@dataclass
class Classification:
    category: str
    root_cause: str
    confidence: float


CATEGORIES = ["flake", "lint", "build", "dependency", "infra_timeout"]
