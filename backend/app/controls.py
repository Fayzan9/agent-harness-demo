class Controls:
    """One-shot signals from the UI to a running loop."""

    def __init__(self):
        self._compact: set[str] = set()

    def request_compact(self, run_id: str):
        self._compact.add(run_id)

    def take_compact(self, run_id: str) -> bool:
        """True once per request. The loop calls this at the start of each pass."""
        if run_id in self._compact:
            self._compact.discard(run_id)
            return True
        return False
