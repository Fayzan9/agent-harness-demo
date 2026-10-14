from .config import WORKSPACE

# Demo files the scenarios rely on. Resetting only rewrites these, it never deletes anything.
SEED = {
    "notes.txt": "Meeting notes: ship the playground demo on Friday. Owner: Faizan.\n",
    "contact.txt": "Contact: faizan@example.com for questions about the demo on Friday at noon.\n",
}


def snapshot() -> list[dict]:
    return [
        {"name": p.name, "content": p.read_text(errors="replace"), "seed": p.name in SEED}
        for p in sorted(WORKSPACE.iterdir())
        if p.is_file()
    ]


def reset():
    for name, text in SEED.items():
        (WORKSPACE / name).write_text(text)
