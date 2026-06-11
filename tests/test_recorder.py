"""Tests for the recorder's event-building logic (no real input devices)."""

from clickreplay.monitors import MonitorInfo
from clickreplay.recorder import Recorder, _hotkey_keyname, _key_to_str


def _mon() -> MonitorInfo:
    return MonitorInfo(index=0, name="TEST", x=0, y=0, width=1920, height=1080, is_primary=True)


def test_hotkey_keyname():
    assert _hotkey_keyname("<f9>") == "f9"
    assert _hotkey_keyname("<F10>") == "f10"


def test_build_script_filters_control_hotkeys():
    rec = Recorder(_mon())
    rec._queue.put({"type": "key_press", "key": "f9", "t": 0.0})
    rec._queue.put({"type": "key_release", "key": "f10", "t": 0.05})
    rec._queue.put({"type": "key_press", "key": "a", "t": 0.1})
    rec._queue.put({"type": "mouse_click", "x": 5, "y": 5, "button": "left", "t": 0.2})

    script = rec._build_script()
    kept_keys = [e.get("key") for e in script.events if e["type"] == "key_press"]
    assert kept_keys == ["a"]  # f9 removed
    assert any(e["type"] == "mouse_click" for e in script.events)
    assert script.metadata.monitor.width == 1920


def test_custom_hotkeys_are_filtered():
    rec = Recorder(_mon(), stop_hotkey="<f8>", waypoint_hotkey="<f7>")
    rec._queue.put({"type": "key_press", "key": "f8", "t": 0.0})
    rec._queue.put({"type": "key_press", "key": "b", "t": 0.1})
    script = rec._build_script()
    kept = [e.get("key") for e in script.events if e["type"] == "key_press"]
    assert kept == ["b"]


def test_collapse_down_to_click():
    rec = Recorder(_mon())
    down = {"type": "mouse_down", "x": 1, "y": 1, "button": "left", "t": 0.0}
    rec._last_input_evt = down
    rec._collapse_down_to_click()
    assert down["type"] == "mouse_click"


def test_key_to_str_handles_none():
    assert _key_to_str(None) == "unknown"
