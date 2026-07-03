class DedupSet:
    def __init__(self):
        self._seen: set[str] = set()

    def seen(self, event_id: str) -> bool:
        return event_id in self._seen

    def add(self, event_id: str) -> None:
        self._seen.add(event_id)

    def clear(self) -> None:
        self._seen.clear()
