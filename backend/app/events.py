import json
import time
from dataclasses import asdict, dataclass, field


@dataclass
class Event:
    """One thing that happened in the loop. The UI only renders these."""

    type: str
    step: int = 0
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    agent: str = "main"  # which agent produced this: "main" or a subagent id

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def sse(self) -> str:
        return f"data: {self.to_json()}\n\n"
