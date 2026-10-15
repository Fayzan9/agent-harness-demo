import re
from dataclasses import dataclass
from typing import Callable

from .config import HookSetting

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class Hook:
    name: str
    phase: str  # "before" can block a tool call, "after" can rewrite its result
    description: str
    fn: Callable
    param_label: str | None = None
    param_default: int | None = None


HOOKS: dict[str, Hook] = {}


def hook(phase: str, description: str, param: tuple[str, int] | None = None):
    """Register a hook. The UI can only switch these on and off, never add code."""

    def register(fn: Callable) -> Callable:
        HOOKS[fn.__name__] = Hook(fn.__name__, phase, description, fn, *(param or (None, None)))
        return fn

    return register


def run_before(settings: list[HookSetting], tool: str, args: dict):
    """Yields (hook name, reason). A reason means blocked, and no later hook runs."""
    for s in settings:
        h = HOOKS.get(s.name)
        if h and h.phase == "before":
            reason = h.fn(tool, args, s.param if s.param is not None else h.param_default)
            yield h.name, reason
            if reason:
                return


def run_after(settings: list[HookSetting], tool: str, result: str):
    """Yields (hook name, new result). Each hook receives the previous hook's output."""
    for s in settings:
        h = HOOKS.get(s.name)
        if h and h.phase == "after":
            result = h.fn(tool, result, s.param if s.param is not None else h.param_default)
            yield h.name, result


@hook("before", "Block any tool call that touches .env or secret files")
def block_sensitive_files(tool: str, args: dict, param) -> str | None:
    path = str(args.get("path", "")).lower()
    if ".env" in path or "secret" in path:
        return f"'{args['path']}' looks sensitive"


@hook("before", "Block file writes longer than a limit", ("Max characters", 200))
def limit_write_size(tool: str, args: dict, param) -> str | None:
    size = len(str(args.get("content", "")))
    if tool == "write_file" and size > param:
        return f"write is {size} characters, the limit is {param}"


@hook("after", "Hide email addresses in tool results")
def redact_emails(tool: str, result: str, param) -> str:
    return EMAIL.sub("[email hidden]", result)


@hook("after", "Cut long tool results to a limit", ("Max characters", 300))
def truncate_result(tool: str, result: str, param) -> str:
    if len(result) <= param:
        return result
    return f"{result[:param]}... [cut, {len(result) - param} more characters. For a long file, read the rest in pieces with read_file offset and max_chars]"
