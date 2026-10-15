from pathlib import Path

from pydantic import BaseModel

WORKSPACE = Path(__file__).resolve().parents[2] / "workspace"
GATE_MODES = ["auto", "ask", "block"]


class HookSetting(BaseModel):
    name: str
    param: int | None = None  # None means the hook's default


class RunConfig(BaseModel):
    """Everything the UI can set before a run."""

    task: str = ""
    model: str = ""  # Azure deployment name; empty means the MODEL env var
    tools: list[str] = []
    gates: dict[str, str] = {}  # tool name -> auto | ask | block (default: ask)
    hooks: list[HookSetting] = []  # run in this order
    memory: str = ""  # text of the memory file, loaded at start
    context_limit: int = 8000  # small on purpose, so compaction is easy to demo
    compact_at: int = 80  # auto-compact when context reaches this percent of the limit
    max_steps: int = 10
    tool_timeout: int = 20  # seconds a single tool call may take
    chaos: list[str] = []  # failures to inject on purpose, see chaos.py
