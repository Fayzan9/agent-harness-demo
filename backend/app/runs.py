from pathlib import Path

from .events import Event

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def append(run_id: str, event: Event):
    """Keep every event of a run on disk, one JSON object per line."""
    RUNS_DIR.mkdir(exist_ok=True)
    with open(RUNS_DIR / f"{run_id}.jsonl", "a") as f:
        f.write(event.to_json() + "\n")
