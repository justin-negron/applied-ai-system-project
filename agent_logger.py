"""Structured JSONL logger for the PawPal+ agent.

Every agent turn writes one JSON line to logs/agent.jsonl with the timestamp,
event type, and payload. Used for debugging, the eval harness, and showing
the user a transparent reasoning trace in the Streamlit UI.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "agent.jsonl"


def log_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append a structured event to the agent log. Returns the full record."""
    LOG_DIR.mkdir(exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event_type,
        **payload,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record


def read_recent(n: int = 50) -> list[dict[str, Any]]:
    """Return the last n log records for inspection."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(line) for line in lines if line.strip()]


def clear_log() -> None:
    """Wipe the log file (used by tests and eval runs)."""
    if LOG_FILE.exists():
        LOG_FILE.unlink()
