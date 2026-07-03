import yaml
from pathlib import Path

from app.classifier.models import Classification


class KnowledgeBase:
    def __init__(self, path: str):
        self._path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                return yaml.safe_load(f) or {"entries": []}
        return {"entries": []}

    def _save(self):
        with open(self._path, "w") as f:
            yaml.dump(self._data, f)

    def query(self, text: str) -> Classification | None:
        for entry in self._data.get("entries", []):
            for sig in entry.get("signatures", []):
                if sig in text:
                    return Classification(
                        category=entry["category"],
                        root_cause=entry.get("remediation", ""),
                        confidence=min(entry.get("confidence", 0.90) + 0.05, 0.99),
                    )
        return None

    def update(self, entry: dict):
        self._data.setdefault("entries", []).append(entry)
        self._save()
