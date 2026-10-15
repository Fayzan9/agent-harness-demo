import inspect
from dataclasses import dataclass
from typing import Callable

from .config import workspace_var

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable


REGISTRY: dict[str, Tool] = {}


def tool(fn: Callable) -> Callable:
    """Register a function as a tool. Schema comes from its type hints and docstring."""
    params = inspect.signature(fn).parameters
    props = {name: {"type": _JSON_TYPES[p.annotation]} for name, p in params.items()}
    required = [name for name, p in params.items() if p.default is inspect.Parameter.empty]  # a default makes it optional
    schema = {"type": "object", "properties": props, "required": required}
    REGISTRY[fn.__name__] = Tool(fn.__name__, inspect.getdoc(fn) or "", schema, fn)
    return fn


def schemas(names: list[str]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for n in names
        if (t := REGISTRY.get(n))
    ]


def _safe(path: str):
    root = workspace_var.get().resolve()
    full = (root / path).resolve()
    if not full.is_relative_to(root):
        raise ValueError("Path is outside the workspace")
    return full


@tool
def list_files() -> str:
    """List the files in the workspace folder."""
    return "\n".join(p.name for p in sorted(workspace_var.get().iterdir())) or "(empty)"


@tool
def read_file(path: str, offset: int = 0, max_chars: int = 0) -> str:
    """Read a text file from the workspace. Whatever you read stays in your context, so a long file is expensive. If you only need one fact, use search_file first. To read a long file in pieces, set offset (where to start) and max_chars (how much; 0 means everything)."""
    text = _safe(path).read_text()[offset:]
    return text[:max_chars] if max_chars > 0 else text


@tool
def search_file(path: str, query: str) -> str:
    """Find the lines of a file that contain a word or phrase (not case sensitive). Returns up to 10 matches with line numbers, so you do not have to read the whole file."""
    hits = [f"line {n}: {line}" for n, line in enumerate(_safe(path).read_text().splitlines(), 1) if query.lower() in line.lower()]
    if not hits:
        return "No matches."
    more = f"\n({len(hits) - 10} more matches not shown)" if len(hits) > 10 else ""
    return "\n".join(hits[:10]) + more


@tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a text file in the workspace."""
    _safe(path).write_text(content)
    return f"Wrote {len(content)} characters to {path}"


@tool
def delegate(task: str) -> str:
    """Hand a self-contained task to a helper agent. It works in its own fresh context and returns only a short summary."""
    raise NotImplementedError("The loop runs this one itself, because it needs to start another loop")


SCRATCHPAD = "scratchpad.md"


@tool
def save_note(text: str) -> str:
    """Save a short note to a scratchpad file outside the conversation. Notes stay available even after old messages are summarized."""
    path = _safe(SCRATCHPAD)
    with path.open("a") as f:
        f.write(f"- {text}\n")
    return f"Saved. The scratchpad now has {len(path.read_text().splitlines())} notes."


@tool
def read_notes() -> str:
    """Read everything saved to the scratchpad."""
    path = _safe(SCRATCHPAD)
    return path.read_text() if path.exists() else "(no notes yet)"
