"""Record mouse and keyboard events using pynput listeners."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from pynput import keyboard, mouse

from . import config
from .monitors import MonitorInfo, abs_to_relative, is_point_on_monitor
from .script import MonitorMeta, Script, ScriptMetadata


def _hotkey_keyname(hotkey: str) -> str:
    """Turn a pynput hotkey like ``"<f9>"`` into a key name like ``"f9"``."""
    return hotkey.strip("<>").lower()


class Recorder:
    """Captures input events on a specific monitor into an event list.

    Mouse positions are recorded only on clicks, drags, scrolls, or when the
    waypoint hotkey (F10) is pressed. This keeps scripts clean — the smooth
    movement between points is synthesised at playback time.

    Usage::

        rec = Recorder(monitor)
        rec.start()          # non-blocking; press F9 to stop
        script = rec.wait()  # blocks until recording stops
    """

    _DRAG_THRESHOLD = 5  # pixels — below this, a press+release is a click

    def __init__(
        self,
        monitor: MonitorInfo,
        *,
        stop_hotkey: str = config.RECORD_HOTKEY,
        waypoint_hotkey: str = config.WAYPOINT_HOTKEY,
    ) -> None:
        self._monitor = monitor
        self._hotkey = stop_hotkey
        self._waypoint_hotkey = waypoint_hotkey
        self._control_keynames = {
            _hotkey_keyname(stop_hotkey),
            _hotkey_keyname(waypoint_hotkey),
        }

        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._recording = False
        self._start_time: float = 0.0
        self._stop_event = threading.Event()

        self._mouse_listener: mouse.Listener | None = None
        self._kb_listener: keyboard.Listener | None = None
        self._hotkey_listener: keyboard.GlobalHotKeys | None = None

        # Drag tracking state
        self._drag_button: str | None = None
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._last_input_evt: dict[str, Any] | None = None

    # ----- public API -------------------------------------------------------

    def start(self) -> None:
        """Begin recording (non-blocking)."""
        self._recording = True
        self._start_time = time.monotonic()
        self._stop_event.clear()

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._kb_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        hotkeys = {
            self._hotkey: self._toggle_stop,
            self._waypoint_hotkey: self._mark_waypoint,
        }
        self._hotkey_listener = keyboard.GlobalHotKeys(hotkeys)

        self._mouse_listener.start()
        self._kb_listener.start()
        self._hotkey_listener.start()

    def wait(self) -> Script:
        """Block until recording stops and return the captured script."""
        self._stop_event.wait()
        return self._build_script()

    def stop(self) -> None:
        """Programmatically stop recording."""
        self._toggle_stop()

    # ----- callbacks (run on pynput background threads) ---------------------

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _on_click(
        self,
        x: int,
        y: int,
        button: mouse.Button,
        pressed: bool,
    ) -> None:
        if not self._recording:
            return
        if not is_point_on_monitor(x, y, self._monitor):
            return

        rel_x, rel_y = abs_to_relative(x, y, self._monitor)
        btn = "right" if button == mouse.Button.right else "left"

        if pressed:
            # Button down — start a potential drag.
            self._drag_button = btn
            self._drag_start_x = rel_x
            self._drag_start_y = rel_y

            move_evt: dict[str, Any] = {
                "type": "mouse_move", "x": rel_x, "y": rel_y, "t": self._elapsed(),
            }
            down_evt: dict[str, Any] = {
                "type": "mouse_down",
                "x": rel_x, "y": rel_y, "button": btn, "t": self._elapsed(),
            }
            self._queue.put(move_evt)
            self._queue.put(down_evt)
            self._last_input_evt = down_evt
        else:
            # Button up — decide click vs drag.
            dx = abs(rel_x - self._drag_start_x)
            dy = abs(rel_y - self._drag_start_y)
            was_drag = dx > self._DRAG_THRESHOLD or dy > self._DRAG_THRESHOLD

            if was_drag:
                up_evt: dict[str, Any] = {
                    "type": "mouse_up",
                    "x": rel_x, "y": rel_y, "button": btn, "t": self._elapsed(),
                }
                self._queue.put(up_evt)
                self._last_input_evt = up_evt
            else:
                # Small movement — collapse the press into a single click.
                self._collapse_down_to_click()

            self._drag_button = None

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._recording:
            return
        if not is_point_on_monitor(x, y, self._monitor):
            return
        rel_x, rel_y = abs_to_relative(x, y, self._monitor)
        self._queue.put({
            "type": "mouse_scroll",
            "x": rel_x, "y": rel_y, "dx": dx, "dy": dy, "t": self._elapsed(),
        })

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if not self._recording:
            return
        self._queue.put({"type": "key_press", "key": _key_to_str(key), "t": self._elapsed()})

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if not self._recording:
            return
        self._queue.put({"type": "key_release", "key": _key_to_str(key), "t": self._elapsed()})

    def _mark_waypoint(self) -> None:
        """Record the current mouse position as a waypoint (F10).

        Playback moves to the point and then dwells (point-stop), without
        clicking — handy for guiding the cursor along a path.
        """
        if not self._recording:
            return
        import pyautogui

        x, y = pyautogui.position()
        if not is_point_on_monitor(x, y, self._monitor):
            return
        rel_x, rel_y = abs_to_relative(x, y, self._monitor)
        self._queue.put({
            "type": "mouse_move",
            "x": rel_x, "y": rel_y, "waypoint": True, "t": self._elapsed(),
        })

    # ----- internal ----------------------------------------------------------

    def _collapse_down_to_click(self) -> None:
        """Turn the last ``mouse_down`` into a ``mouse_click`` (press == release)."""
        if (self._last_input_evt is not None
                and self._last_input_evt.get("type") == "mouse_down"):
            self._last_input_evt["type"] = "mouse_click"

    def _toggle_stop(self) -> None:
        """Stop recording. Safe to call from the hotkey listener thread."""
        self._recording = False
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._kb_listener:
            self._kb_listener.stop()
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self._stop_event.set()

    def _drain_queue(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _build_script(self) -> Script:
        events = self._drain_queue()
        # Drop the control hotkeys (e.g. F9/F10) used to drive recording.
        events = [
            e for e in events
            if not (
                e["type"] in ("key_press", "key_release")
                and e.get("key") in self._control_keynames
            )
        ]
        mon = self._monitor
        metadata = ScriptMetadata(
            monitor=MonitorMeta(
                index=mon.index,
                name=mon.name,
                width=mon.width,
                height=mon.height,
            ),
        )
        return Script(metadata=metadata, events=events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _key_to_str(key: keyboard.Key | keyboard.KeyCode | None) -> str:
    """Normalise a pynput key to a portable string name."""
    if key is None:
        return "unknown"
    if isinstance(key, keyboard.Key):
        return key.name  # e.g. "shift", "ctrl_l", "enter"
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return key.char  # e.g. "a", "1", "/"
        if key.vk is not None:
            return f"<{key.vk}>"
    return str(key)
