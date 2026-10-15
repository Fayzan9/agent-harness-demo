from .events import Event

KINDS = {
    "rate_limit": "Fail the first two model calls with a rate limit",
    "bad_json": "Send broken JSON arguments on the first tool call",
    "slow_tool": "Make the first tool call hang",
    "repeat_call": "Make the agent repeat the same tool call",
}


class SimulatedRateLimit(Exception):
    """Stands in for the provider answering 429."""


class Chaos:
    """Breaks things on purpose so the defences can be watched working. Main agent only."""

    def __init__(self, kinds: list[str]):
        self.kinds = set(kinds)
        self.rate_limited = 0
        self.broke_json = False
        self.hung = False
        self.first_call: dict | None = None
        self._notes: list[Event] = []

    def drain(self) -> list[Event]:
        notes, self._notes = self._notes, []
        return notes

    def _note(self, step: int, kind: str, detail: str):
        self._notes.append(Event("chaos", step, {"kind": kind, "detail": detail}))

    def before_model_call(self, step: int):
        if "rate_limit" in self.kinds and self.rate_limited < 2:
            self.rate_limited += 1
            self._note(step, "rate_limit", f"Pretending the API answered 429 (failure {self.rate_limited} of 2)")
            raise SimulatedRateLimit("429 Too Many Requests (simulated)")

    def tamper_raw(self, raw_calls: list[dict], step: int) -> list[dict]:
        if "bad_json" in self.kinds and not self.broke_json and raw_calls:
            self.broke_json = True
            raw_calls[0]["raw"] = raw_calls[0]["raw"].rstrip()[:-1]  # drop the closing brace
            self._note(step, "bad_json", f"Cutting the arguments of {raw_calls[0]['name']} so they are not valid JSON")
        return raw_calls

    def repeat(self, calls: list[dict], step: int) -> list[dict]:
        if "repeat_call" not in self.kinds:
            return calls
        if self.first_call is None:
            if calls:
                self.first_call = calls[0]
            return calls
        self._note(step, "repeat_call", f"Making the agent call {self.first_call['name']} again instead of finishing")
        return [{**self.first_call, "id": f"{self.first_call['id']}-r{step}"}]

    def hangs(self, step: int) -> bool:
        if "slow_tool" in self.kinds and not self.hung:
            self.hung = True
            self._note(step, "slow_tool", "Making this tool call hang")
            return True
        return False
