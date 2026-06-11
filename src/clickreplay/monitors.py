"""Monitor enumeration and coordinate transforms for multi-monitor support."""

from __future__ import annotations

import ctypes
import platform
from dataclasses import dataclass

from screeninfo import get_monitors


@dataclass(frozen=True)
class MonitorInfo:
    """Metadata for a single display monitor."""

    index: int
    name: str | None
    x: int          # virtual-desktop X of top-left corner
    y: int          # virtual-desktop Y of top-left corner
    width: int
    height: int
    is_primary: bool


def _set_dpi_awareness() -> None:
    """Tell Windows this process is per-monitor DPI aware.

    Must be called early — before any coordinate work — so that pynput
    listener coordinates and pyautogui controller coordinates agree.
    """
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        # Fallback for older Windows versions
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass


# Apply DPI awareness on import so every module benefits.
_set_dpi_awareness()


def list_monitors() -> list[MonitorInfo]:
    """Return all connected monitors sorted by index (left-to-right)."""
    raw = get_monitors()
    # Sort by x position so indices are spatially predictable.
    raw.sort(key=lambda m: (m.x, m.y))
    return [
        MonitorInfo(
            index=i,
            name=m.name,
            x=m.x,
            y=m.y,
            width=m.width,
            height=m.height,
            is_primary=bool(m.is_primary),
        )
        for i, m in enumerate(raw)
    ]


def select_monitor(index: int) -> MonitorInfo:
    """Return the monitor with the given index, or raise ValueError."""
    monitors = list_monitors()
    if index < 0 or index >= len(monitors):
        available = ", ".join(
            f"{m.index} ({m.width}x{m.height}{' primary' if m.is_primary else ''})"
            for m in monitors
        )
        raise ValueError(
            f"Monitor index {index} out of range. Available: {available}"
        )
    return monitors[index]


def abs_to_relative(abs_x: int, abs_y: int, monitor: MonitorInfo) -> tuple[int, int]:
    """Convert absolute virtual-desktop coords to monitor-relative coords."""
    return abs_x - monitor.x, abs_y - monitor.y


def relative_to_abs(rel_x: int, rel_y: int, monitor: MonitorInfo) -> tuple[int, int]:
    """Convert monitor-relative coords to absolute virtual-desktop coords."""
    return rel_x + monitor.x, rel_y + monitor.y


def is_point_on_monitor(abs_x: int, abs_y: int, monitor: MonitorInfo) -> bool:
    """Check whether an absolute point falls within the monitor bounds."""
    return (
        monitor.x <= abs_x < monitor.x + monitor.width
        and monitor.y <= abs_y < monitor.y + monitor.height
    )
