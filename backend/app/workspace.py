from .config import WORKSPACE

_FILLER = [
    "Staff must badge in at the front desk before 9:30 every morning.",
    "Printer supplies are ordered on the first Monday of each month.",
    "Visitors sign the guest book and wear a lanyard while on site.",
    "Expense reports are due by the fifth working day of the month.",
    "The kitchen is cleaned on Fridays, so label food in the fridge.",
    "Meeting rooms are booked in the shared calendar, never by email.",
    "Laptops are encrypted and locked whenever they are left unattended.",
    "Team lunches are approved by the team lead and billed to the project.",
]


def _handbook() -> str:
    """A long file with one useful fact buried in the middle, to show what big tool results do to context."""
    lines = [f"Section {i}: {_FILLER[i % len(_FILLER)]}" for i in range(1, 121)]
    lines[71] = "Section 72 (Refunds): Customers may return items within 30 days with a receipt. Shipping fees are not refunded."
    return "\n".join(lines) + "\n"


# Demo files the scenarios rely on. Resetting rewrites these and clears the scratchpad, nothing else.
SEED = {
    "notes.txt": "Meeting notes: ship the playground demo on Friday. Owner: Faizan.\n",
    "contact.txt": "Contact: faizan@example.com for questions about the demo on Friday at noon.\n",
    "handbook.txt": _handbook(),
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
    (WORKSPACE / "scratchpad.md").unlink(missing_ok=True)  # the agent's own notes belong to one chat
