import inspect
from dataclasses import dataclass
from typing import Callable

from .config import WORKSPACE

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
    props = {
        name: {"type": _JSON_TYPES[p.annotation]}
        for name, p in inspect.signature(fn).parameters.items()
    }
    schema = {"type": "object", "properties": props, "required": list(props)}
    REGISTRY[fn.__name__] = Tool(fn.__name__, inspect.getdoc(fn) or "", schema, fn)
    return fn


def schemas(names: list[str]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for n in names
        if (t := REGISTRY.get(n))
    ]


def _safe(path: str):
    full = (WORKSPACE / path).resolve()
    if not full.is_relative_to(WORKSPACE.resolve()):
        raise ValueError("Path is outside the workspace")
    return full


@tool
def list_files() -> str:
    """List the files in the workspace folder."""
    return "\n".join(p.name for p in sorted(WORKSPACE.iterdir())) or "(empty)"


@tool
def read_file(path: str) -> str:
    """Read a text file from the workspace."""
    return _safe(path).read_text()


@tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a text file in the workspace."""
    _safe(path).write_text(content)
    return f"Wrote {len(content)} characters to {path}"


@tool
def delegate(task: str) -> str:
    """Hand a self-contained task to a helper agent. It works in its own fresh context and returns only a short summary."""
    raise NotImplementedError("The loop runs this one itself, because it needs to start another loop")
