from contextvars import ContextVar
from pathlib import Path

from pydantic import BaseModel

WORKSPACE = Path(__file__).resolve().parents[2] / "workspace"
# Which folder the file tools use. Evals give every run its own temporary folder so runs cannot interfere.
workspace_var: ContextVar[Path] = ContextVar("workspace", default=WORKSPACE)
GATE_MODES = ["auto", "ask", "block"]


class HookSetting(BaseModel):
    name: str
    param: int | None = None  # None means the hook's default


class RunConfig(BaseModel):
    """Everything the UI can set before a run."""

    task: str = ""
    model: str = ""  # a model name for the chosen provider (Azure: a deployment name); empty means the MODEL env var
    tools: list[str] = []
    gates: dict[str, str] = {}  # tool name -> auto | ask | block (default: ask)
    hooks: list[HookSetting] = []  # run in this order
    memory: str = ""  # text of the memory file, loaded at start
    context_limit: int = 8000  # small on purpose, so compaction is easy to demo
    compact_at: int = 80  # auto-compact when context reaches this percent of the limit
    max_steps: int = 10
    tool_timeout: int = 20  # seconds a single tool call may take
    chaos: list[str] = []  # failures to inject on purpose, see chaos.py
