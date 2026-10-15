from . import llm

PROMPT = (
    "You write progress notes for an assistant that is in the middle of a task. "
    "You are not doing the task yourself: never answer it, never refuse it, never mention missing tools. "
    "Describe only what has happened so far: the facts and file names found, results that matter, "
    "decisions made, and what is still left to do. Be concise."
)


def transcript(summary: str, messages: list[dict]) -> str:
    """Flatten the conversation to plain text so the summarizer sees one simple input."""
    lines = [f"Earlier summary: {summary}"] if summary else []
    for m in messages:
        if m["role"] == "tool":
            lines.append(f"Tool result: {m['content']}")
        elif m["role"] == "assistant":
            for c in m.get("tool_calls", []):
                lines.append(f"Assistant called {c['function']['name']}({c['function']['arguments']})")
            if m["content"]:
                lines.append(f"Assistant: {m['content']}")
        else:
            lines.append(f"User: {m['content']}")
    return "\n".join(lines)


async def summarize(model: str, summary: str, messages: list[dict]) -> tuple[str, dict]:
    """Returns the summary and the token usage of the call that wrote it."""
    notes = f"Write the progress notes for this conversation. Do not do the task in it.\n\n<conversation>\n{transcript(summary, messages)}\n</conversation>"
    prompt = [{"role": "system", "content": PROMPT}, {"role": "user", "content": notes}]
    resp = await llm.complete(model, prompt, None)
    return resp.choices[0].message.content or "", llm.usage_of(resp)
