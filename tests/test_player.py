"""Tests for playback timing, point-stop dwell, and dry-run."""

import types

import pytest

from clickreplay.monitors import MonitorInfo
from clickreplay.player import Player
from clickreplay.script import MonitorMeta, Script, ScriptMetadata


def _mon() -> MonitorInfo:
    return MonitorInfo(index=0, name="TEST", x=0, y=0, width=1920, height=1080, is_primary=True)


def _script(events=None) -> Script:
    return Script(
        metadata=ScriptMetadata(monitor=MonitorMeta(0, "TEST", 1920, 1080)),
        events=events or [],
    )


@pytest.fixture
def player_with_sleeps(monkeypatch):
    """A Player whose pyautogui calls are stubbed and whose dwell is recorded."""
    dummy = types.SimpleNamespace(
        click=lambda *a, **k: None,
        moveTo=lambda *a, **k: None,
        mouseDown=lambda *a, **k: None,
        mouseUp=lambda *a, **k: None,
        scroll=lambda *a, **k: None,
        keyDown=lambda *a, **k: None,
        keyUp=lambda *a, **k: None,
        easeInOutQuad=lambda n: n,
    )
    monkeypatch.setattr("clickreplay.player.pyautogui", dummy)

    def _make(point_stop=1.0):
        p = Player(_script(), target_monitor=_mon(), point_stop=point_stop, dry_run=False)
        sleeps: list[float] = []
        monkeypatch.setattr(p, "_sleep", lambda s: sleeps.append(s))
        return p, sleeps

    return _make


def test_click_applies_default_point_stop(player_with_sleeps):
    p, sleeps = player_with_sleeps(point_stop=1.0)
    p._do_mouse_click({"type": "mouse_click", "x": 10, "y": 10, "button": "left", "t": 0})
    assert sleeps == [1.0]


def test_hold_overrides_default(player_with_sleeps):
    p, sleeps = player_with_sleeps(point_stop=1.0)
    p._do_mouse_click({"type": "mouse_click", "x": 10, "y": 10, "button": "left", "t": 0, "hold": 2.5})
    assert sleeps == [2.5]


def test_zero_point_stop_disables_dwell(player_with_sleeps):
    p, sleeps = player_with_sleeps(point_stop=0.0)
    p._do_mouse_click({"type": "mouse_click", "x": 10, "y": 10, "button": "left", "t": 0})
    assert sleeps == []


def test_waypoint_move_dwells(player_with_sleeps):
    p, sleeps = player_with_sleeps(point_stop=1.0)
    p._do_mouse_move({"type": "mouse_move", "x": 1, "y": 1, "t": 0, "waypoint": True}, 0.1)
    assert sleeps == [1.0]


def test_regular_move_does_not_dwell(player_with_sleeps):
    p, sleeps = player_with_sleeps(point_stop=1.0)
    p._do_mouse_move({"type": "mouse_move", "x": 1, "y": 1, "t": 0}, 0.1)
    assert sleeps == []


def test_drag_release_dwells(player_with_sleeps):
    p, sleeps = player_with_sleeps(point_stop=1.0)
    p._do_mouse_up({"type": "mouse_up", "x": 9, "y": 9, "button": "left", "t": 0}, 0.2)
    assert sleeps == [1.0]


def test_coordinate_scaling():
    # Recorded on 1920x1080, replay onto 960x540 -> coords halved.
    s = _script()
    target = MonitorInfo(index=1, name="HALF", x=0, y=0, width=960, height=540, is_primary=False)
    p = Player(s, target_monitor=target, dry_run=True)
    assert p._to_abs(1000, 500) == (500, 250)


def test_dry_run_play_emits_actions(capsys):
    events = [
        {"type": "mouse_move", "x": 1, "y": 1, "t": 0.0},
        {"type": "mouse_click", "x": 1, "y": 1, "button": "left", "t": 0.1, "hold": 0.5},
        {"type": "key_press", "key": "a", "t": 0.2},
        {"type": "key_release", "key": "a", "t": 0.3},
    ]
    p = Player(_script(events), target_monitor=_mon(), countdown=0, dry_run=True)
    p.play()
    err = capsys.readouterr().err
    assert "click(" in err
    assert "[hold 0.50s]" in err
