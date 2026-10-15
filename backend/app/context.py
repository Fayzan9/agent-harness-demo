import json

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
        self.messages: list[dict] = []

    def add(self, message: dict):
        self.messages.append(message)

    def compact(self, summary: str):
        self.summary = summary
        self.messages = []

    def to_dict(self) -> dict:
        return {"memory": self.memory, "summary": self.summary, "messages": self.messages}

    @classmethod
    def from_dict(cls, data: dict) -> "Context":
        ctx = cls(data.get("memory", ""))
        ctx.summary = data.get("summary", "")
        ctx.messages = data.get("messages", [])
        return ctx

    def system_prompt(self) -> str:
        return SYSTEM + (f"\n\nMemory file:\n{self.memory}" if self.memory else "")

    def as_messages(self) -> list[dict]:
        recap = []
        if self.summary:
            text = f"Summary of the work so far:\n{self.summary}\n\nContinue the task from here."
            recap = [{"role": "user", "content": text}]
        return [{"role": "system", "content": self.system_prompt()}, *recap, *self.messages]

    def usage(self, tool_schemas: list[dict], limit: int) -> dict:
        parts = {
            "instructions": tokens(SYSTEM),
            "tools": tokens(tool_schemas) if tool_schemas else 0,
            "memory": tokens(self.memory),
            "summary": tokens(self.summary),
            "chat": sum(tokens(m) for m in self.messages if m["role"] != "tool"),
            "tool_results": sum(tokens(m) for m in self.messages if m["role"] == "tool"),
        }
        return {"limit": limit, "total": sum(parts.values()), "parts": parts}
