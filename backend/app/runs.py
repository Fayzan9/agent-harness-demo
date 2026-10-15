import json
from pathlib import Path

from .events import Event

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def append(run_id: str, event: Event):
    """Keep every event of a run on disk, one JSON object per line."""
    RUNS_DIR.mkdir(exist_ok=True)
    with open(RUNS_DIR / f"{run_id}.jsonl", "a") as f:
        f.write(event.to_json() + "\n")


def load(run_id: str) -> list[dict]:
    """Read back every event of a saved run, in order."""
    path = RUNS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
