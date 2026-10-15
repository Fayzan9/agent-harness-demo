import json
import time

SYSTEM = (
    "You are a careful assistant that completes tasks step by step. "
    "Use the available tools when you need to read or change files in the workspace. "
    "When the task is done, reply in plain text without calling a tool."
)


def tokens(obj) -> int:
    """Rough estimate: about 4 characters per token. Good enough to visualize."""
    return len(obj if isinstance(obj, str) else json.dumps(obj)) // 4


class Context:
    """Everything the model sees. Re-sent in full on every loop pass."""

    def __init__(self, memory: str = ""):
        self.memory = memory
        self.summary = ""  # replaces old messages after compaction
        self.anchor: dict | None = None  # the latest user request, kept word for word through compaction
        self.clock_first = False  # the Break it "clock in prompt" switch. Not saved: it is set again on every run
        self.messages: list[dict] = []

    def add(self, message: dict):
        self.messages.append(message)

    def compact(self, summary: str):
        """Swap the old turns for a summary, but keep the latest request word for word.
        A summary can quietly lose what the user actually asked for (an eval caught exactly that)."""
        latest = next((m for m in reversed(self.messages) if m["role"] == "user"), self.anchor)
        self.anchor = latest
        self.summary = summary
        self.messages = []

    def to_dict(self) -> dict:
        return {"memory": self.memory, "summary": self.summary, "anchor": self.anchor, "messages": self.messages}

    @classmethod
    def from_dict(cls, data: dict) -> "Context":
        ctx = cls(data.get("memory", ""))
        ctx.summary = data.get("summary", "")
        ctx.anchor = data.get("anchor")
        ctx.messages = data.get("messages", [])
        return ctx

    def system_prompt(self) -> str:
        prompt = SYSTEM + (f"\n\nMemory file:\n{self.memory}" if self.memory else "")
        if self.clock_first:  # a changing value at the very top means no prefix ever matches again
            now = time.time()
            stamp = time.strftime("%H:%M:%S", time.localtime(now)) + f".{int(now * 1000) % 1000:03d}"
            return f"Current time: {stamp}\n\n{prompt}"
        return prompt

    def as_messages(self) -> list[dict]:
        kept = [self.anchor] if self.anchor else []
        if self.summary:
            text = (
                f"Progress notes so far:\n{self.summary}\n\n"
                "The request above is still the task. Continue from here and do not repeat steps that are already done."
            )
            kept.append({"role": "user", "content": text})
        return [{"role": "system", "content": self.system_prompt()}, *kept, *self.messages]

    def usage(self, tool_schemas: list[dict], limit: int) -> dict:
        parts = {
            "instructions": tokens(SYSTEM),
            "tools": tokens(tool_schemas) if tool_schemas else 0,
            "memory": tokens(self.memory),
            "summary": tokens(self.summary),
            "chat": sum(tokens(m) for m in self.messages if m["role"] != "tool") + (tokens(self.anchor) if self.anchor else 0),
            "tool_results": sum(tokens(m) for m in self.messages if m["role"] == "tool"),
        }
        return {"limit": limit, "total": sum(parts.values()), "parts": parts}
