"""Script format — event types, JSON serialisation, and validation.

A recording is a small JSON document: monitor metadata plus a flat list of
time-stamped events. The format is intentionally human-editable — you can open
it in any text editor to fix a coordinate, adjust timing, or insert a pause.

Each event is a plain dict with at least ``type`` and ``t`` (seconds since the
recording started). Recognised event types and their extra fields:

| type         | fields                         |
|--------------|--------------------------------|
| mouse_move   | x, y[, waypoint]               |
| mouse_click  | x, y, button[, hold]           |
| mouse_down   | x, y, button                   |
| mouse_up     | x, y, button[, hold]           |
| mouse_scroll | x, y, dx, dy                   |
| key_press    | key                            |
| key_release  | key                            |
| wait         | duration                       |

Optional per-event keys:

* ``waypoint`` (bool) — a move marked with F10; playback dwells after it.
* ``hold`` (float) — overrides the global point-stop dwell, in seconds.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

FORMAT_VERSION = "1"

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

EventType = Literal[
    "mouse_move",
    "mouse_click",
    "mouse_down",
    "mouse_up",
    "mouse_scroll",
    "key_press",
    "key_release",
    "wait",
]


@dataclass
class Event:
    type: EventType
    t: float  # seconds since recording start


@dataclass
class MouseMoveEvent(Event):
    x: int = 0
    y: int = 0
    waypoint: bool = False


@dataclass
class MouseClickEvent(Event):
    x: int = 0
    y: int = 0
    button: str = "left"
    hold: float | None = None


@dataclass
class MouseScrollEvent(Event):
    x: int = 0
    y: int = 0
    dx: int = 0
    dy: int = 0


@dataclass
class KeyPressEvent(Event):
    key: str = ""


@dataclass
class KeyReleaseEvent(Event):
    key: str = ""


@dataclass
class WaitEvent(Event):
    duration: float = 0.0


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@dataclass
class MonitorMeta:
    index: int
    name: str | None
    width: int
    height: int


@dataclass
class ScriptMetadata:
    monitor: MonitorMeta
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    description: str = ""
    format_version: str = FORMAT_VERSION


# ---------------------------------------------------------------------------
# Full script container
# ---------------------------------------------------------------------------

@dataclass
class Script:
    metadata: ScriptMetadata
    events: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def save_script(script: Script, path: str | Path) -> Path:
    """Write *script* to a JSON file and return the resolved path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(asdict(script), f, indent=2, ensure_ascii=False)
    return p


def load_script(path: str | Path) -> Script:
    """Read and validate a script JSON file."""
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)

    _validate_raw(raw, p)

    meta_raw = raw["metadata"]
    mon = meta_raw["monitor"]
    metadata = ScriptMetadata(
        monitor=MonitorMeta(
            index=mon["index"],
            name=mon.get("name"),
            width=mon["width"],
            height=mon["height"],
        ),
        recorded_at=meta_raw.get("recorded_at", ""),
        description=meta_raw.get("description", ""),
        format_version=meta_raw.get("format_version", FORMAT_VERSION),
    )
    return Script(metadata=metadata, events=raw.get("events", []))


def _validate_raw(raw: dict[str, Any], path: Path) -> None:
    """Raise ValueError if required fields are missing."""
    if "metadata" not in raw:
        raise ValueError(f"{path}: missing 'metadata' key")
    meta = raw["metadata"]
    if "monitor" not in meta:
        raise ValueError(f"{path}: metadata missing 'monitor' key")
    mon = meta["monitor"]
    for key in ("index", "width", "height"):
        if key not in mon:
            raise ValueError(f"{path}: monitor missing '{key}'")
    for evt in raw.get("events", []):
        if "type" not in evt:
            raise ValueError(f"{path}: event missing 'type': {evt}")
        if "t" not in evt:
            raise ValueError(f"{path}: event missing 't': {evt}")


# ---------------------------------------------------------------------------
# Script manipulation
# ---------------------------------------------------------------------------

def trim_script(script: Script, start: float, end: float) -> Script:
    """Return a new script with only events in [start, end], rebased to t=0."""
    trimmed = [
        {**evt, "t": evt["t"] - start}
        for evt in script.events
        if start <= evt["t"] <= end
    ]
    return Script(metadata=script.metadata, events=trimmed)


def script_duration(script: Script) -> float:
    """Return total duration in seconds (time of last event)."""
    if not script.events:
        return 0.0
    return max(evt["t"] for evt in script.events)


def script_summary(script: Script) -> dict[str, Any]:
    """Return a human-readable summary dict."""
    from collections import Counter

    counts = Counter(evt["type"] for evt in script.events)
    mon = script.metadata.monitor
    return {
        "total_events": len(script.events),
        "duration_secs": round(script_duration(script), 2),
        "monitor": f"{mon.width}x{mon.height} (index {mon.index})",
        "recorded_at": script.metadata.recorded_at,
        "description": script.metadata.description,
        "event_counts": dict(counts),
    }
