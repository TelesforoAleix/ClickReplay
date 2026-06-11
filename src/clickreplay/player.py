"""Replay a recorded script with smooth, eased mouse movement."""

from __future__ import annotations

import sys
import threading
import time
from typing import Any

import pyautogui

from . import config
from .monitors import MonitorInfo, relative_to_abs, select_monitor
from .script import Script

# pyautogui safety — slamming the mouse into a screen corner aborts playback.
pyautogui.FAILSAFE = True


class Player:
    """Replay a Script on a target monitor with eased mouse movement.

    Timing between events is reconstructed from the recorded timestamps and
    divided by *speed*. After each click, drag release, or waypoint a
    "point-stop" dwell is applied so viewers can follow along; the dwell is
    deliberately **not** scaled by *speed*.

    Usage::

        player = Player(script, speed=1.0)
        player.play()   # blocks until done or aborted (Escape)
    """

    def __init__(
        self,
        script: Script,
        *,
        target_monitor: MonitorInfo | None = None,
        speed: float = config.DEFAULT_SPEED,
        countdown: int = config.DEFAULT_COUNTDOWN_SECS,
        point_stop: float = config.DEFAULT_POINT_STOP_SECS,
        easing: str = config.DEFAULT_EASING,
        min_move_duration: float = config.MIN_MOVE_DURATION,
        max_move_duration: float = config.MAX_MOVE_DURATION,
        dry_run: bool = False,
    ) -> None:
        self._script = script
        self._speed = max(speed, 0.1)
        self._countdown = countdown
        self._point_stop = max(point_stop, 0.0)
        self._min_move = min_move_duration
        self._max_move = max_move_duration
        self._dry_run = dry_run
        self._aborted = False
        self._easing = getattr(pyautogui, easing, pyautogui.easeInOutQuad)

        if target_monitor is not None:
            self._monitor = target_monitor
        else:
            self._monitor = select_monitor(script.metadata.monitor.index)

    # ----- public API -------------------------------------------------------

    def play(self) -> None:
        """Execute the full script. Blocks until completion or abort."""
        self._aborted = False
        self._check_resolution()

        # Escape-key listener for an emergency stop (skipped in dry-run).
        if not self._dry_run:
            threading.Thread(target=self._listen_for_abort, daemon=True).start()

        self._do_countdown()

        events = self._script.events
        if not events:
            self._print("[DONE] Nothing to play (empty script).")
            return

        prev_t = events[0]["t"]
        for evt in events:
            if self._aborted:
                self._print("[ABORTED] Escape pressed — stopping playback.")
                break

            delta = (evt["t"] - prev_t) / self._speed
            prev_t = evt["t"]
            etype = evt["type"]

            if etype == "mouse_move":
                self._do_mouse_move(evt, delta)
            elif etype == "mouse_click":
                self._sleep(delta)
                self._do_mouse_click(evt)
            elif etype == "mouse_down":
                self._sleep(delta)
                self._do_mouse_down(evt)
            elif etype == "mouse_up":
                # Use the gap as the drag-glide duration instead of sleeping.
                self._do_mouse_up(evt, delta)
            elif etype == "mouse_scroll":
                self._sleep(delta)
                self._do_mouse_scroll(evt)
            elif etype == "key_press":
                self._sleep(delta)
                self._do_key_press(evt)
            elif etype == "key_release":
                self._sleep(delta)
                self._do_key_release(evt)
            elif etype == "wait":
                duration = evt.get("duration", 0.0) / self._speed
                self._sleep(delta + duration)

        if not self._aborted:
            self._print("[DONE] Playback complete.")

    # ----- event handlers ----------------------------------------------------

    def _do_mouse_move(self, evt: dict[str, Any], duration: float) -> None:
        abs_x, abs_y = self._to_abs(evt["x"], evt["y"])
        duration = max(self._min_move, min(duration, self._max_move))
        if self._dry_run:
            tag = " [waypoint]" if evt.get("waypoint") else ""
            self._print(f"  moveTo({abs_x}, {abs_y}, duration={duration:.3f}){tag}")
        else:
            pyautogui.moveTo(abs_x, abs_y, duration=duration, tween=self._easing)
        # A waypoint move dwells like a click so the cursor pauses on the path.
        if evt.get("waypoint"):
            self._apply_point_stop(evt)

    def _do_mouse_click(self, evt: dict[str, Any]) -> None:
        abs_x, abs_y = self._to_abs(evt["x"], evt["y"])
        button = evt.get("button", "left")
        if self._dry_run:
            self._print(f"  click({abs_x}, {abs_y}, button='{button}')")
        else:
            pyautogui.click(abs_x, abs_y, button=button)
        self._apply_point_stop(evt)

    def _do_mouse_down(self, evt: dict[str, Any]) -> None:
        abs_x, abs_y = self._to_abs(evt["x"], evt["y"])
        button = evt.get("button", "left")
        if self._dry_run:
            self._print(f"  mouseDown({abs_x}, {abs_y}, button='{button}')")
            return
        pyautogui.moveTo(abs_x, abs_y)
        pyautogui.mouseDown(button=button)

    def _do_mouse_up(self, evt: dict[str, Any], duration: float = 0.0) -> None:
        abs_x, abs_y = self._to_abs(evt["x"], evt["y"])
        button = evt.get("button", "left")
        drag_duration = (
            max(self._min_move, min(duration, self._max_move)) if duration > 0 else 0.4
        )
        if self._dry_run:
            self._print(
                f"  dragTo({abs_x}, {abs_y}, duration={drag_duration:.3f}) -> mouseUp('{button}')"
            )
        else:
            pyautogui.moveTo(abs_x, abs_y, duration=drag_duration, tween=self._easing)
            pyautogui.mouseUp(button=button)
        self._apply_point_stop(evt)

    def _do_mouse_scroll(self, evt: dict[str, Any]) -> None:
        abs_x, abs_y = self._to_abs(evt["x"], evt["y"])
        dy = evt.get("dy", 0)
        if self._dry_run:
            self._print(f"  scroll({dy}, x={abs_x}, y={abs_y})")
            return
        pyautogui.scroll(dy, x=abs_x, y=abs_y)

    def _do_key_press(self, evt: dict[str, Any]) -> None:
        key = evt.get("key", "")
        if self._dry_run:
            self._print(f"  keyDown('{key}')")
            return
        pyautogui.keyDown(key)

    def _do_key_release(self, evt: dict[str, Any]) -> None:
        key = evt.get("key", "")
        if self._dry_run:
            self._print(f"  keyUp('{key}')")
            return
        pyautogui.keyUp(key)

    # ----- point-stop (dwell) ------------------------------------------------

    def _apply_point_stop(self, evt: dict[str, Any]) -> None:
        """Pause after an interaction. Per-event ``hold`` overrides the global."""
        secs = evt.get("hold")
        if secs is None:
            secs = self._point_stop
        try:
            secs = float(secs)
        except (TypeError, ValueError):
            secs = self._point_stop
        if secs <= 0:
            return
        if self._dry_run:
            self._print(f"    [hold {secs:.2f}s]")
            return
        self._sleep(secs)

    # ----- helpers ----------------------------------------------------------

    def _to_abs(self, rel_x: int, rel_y: int) -> tuple[int, int]:
        """Convert monitor-relative coords to absolute, scaling if resolutions differ."""
        rec_mon = self._script.metadata.monitor
        if rec_mon.width != self._monitor.width or rec_mon.height != self._monitor.height:
            scale_x = self._monitor.width / max(rec_mon.width, 1)
            scale_y = self._monitor.height / max(rec_mon.height, 1)
            rel_x = int(rel_x * scale_x)
            rel_y = int(rel_y * scale_y)
        return relative_to_abs(rel_x, rel_y, self._monitor)

    def _sleep(self, secs: float) -> None:
        """Sleep, staying responsive to abort. No-op during dry-run."""
        if self._dry_run or secs <= 0:
            return
        deadline = time.monotonic() + secs
        while not self._aborted:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))

    def _check_resolution(self) -> None:
        mon = self._script.metadata.monitor
        if mon.width != self._monitor.width or mon.height != self._monitor.height:
            self._print(
                f"[SCALE] Script recorded on {mon.width}x{mon.height}, "
                f"target is {self._monitor.width}x{self._monitor.height}. "
                f"Coordinates will be proportionally scaled."
            )

    def _do_countdown(self) -> None:
        if self._dry_run:
            return
        for i in range(self._countdown, 0, -1):
            self._print(f"  Starting in {i}...")
            time.sleep(1)

    def _listen_for_abort(self) -> None:
        """Block in a background thread; set _aborted when Escape is pressed."""
        from pynput import keyboard as kb

        def on_press(key: kb.Key | kb.KeyCode | None) -> bool | None:
            if key == kb.Key.esc:
                self._aborted = True
                return False  # stop listener
            return None

        with kb.Listener(on_press=on_press) as listener:
            listener.join()

    @staticmethod
    def _print(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)
