"""Tests for the script JSON format: round-trip, validation, trim, summary."""

import json

import pytest

from clickreplay.script import (
    FORMAT_VERSION,
    MonitorMeta,
    Script,
    ScriptMetadata,
    load_script,
    save_script,
    script_summary,
    trim_script,
)


def _script(events=None) -> Script:
    return Script(
        metadata=ScriptMetadata(monitor=MonitorMeta(0, "TEST", 1920, 1080)),
        events=events or [],
    )


def test_round_trip_preserves_waypoint_and_hold(tmp_path):
    s = _script([
        {"type": "mouse_move", "x": 1, "y": 2, "t": 0.0, "waypoint": True},
        {"type": "mouse_click", "x": 1, "y": 2, "button": "left", "t": 0.5, "hold": 2.0},
    ])
    p = save_script(s, tmp_path / "r.json")
    loaded = load_script(p)

    assert loaded.events[0]["waypoint"] is True
    assert loaded.events[1]["hold"] == 2.0
    assert loaded.metadata.format_version == FORMAT_VERSION
    assert loaded.metadata.monitor.width == 1920


def test_validation_rejects_event_without_type(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps({
            "metadata": {"monitor": {"index": 0, "width": 1, "height": 1}},
            "events": [{"t": 0}],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_script(p)


def test_validation_rejects_missing_monitor(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"metadata": {}, "events": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_script(p)


def test_trim_rebases_to_zero():
    s = _script([
        {"type": "mouse_click", "x": 0, "y": 0, "button": "left", "t": t}
        for t in (0.0, 1.0, 2.0, 3.0)
    ])
    trimmed = trim_script(s, 1.0, 2.0)
    assert [e["t"] for e in trimmed.events] == [0.0, 1.0]


def test_summary_counts_events():
    s = _script([
        {"type": "mouse_click", "x": 0, "y": 0, "button": "left", "t": 0.0},
        {"type": "key_press", "key": "a", "t": 0.2},
    ])
    summary = script_summary(s)
    assert summary["total_events"] == 2
    assert summary["event_counts"]["mouse_click"] == 1
    assert summary["duration_secs"] == 0.2
