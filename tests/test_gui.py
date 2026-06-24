"""Tests for GUI file-management helpers without launching Tk."""

import os

import pytest

from clickreplay.gui import list_recordings, recording_label, rename_recording


def test_list_recordings_returns_json_files_newest_first(tmp_path):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    ignored = tmp_path / "notes.txt"
    old.write_text("{}", encoding="utf-8")
    new.write_text("{}", encoding="utf-8")
    ignored.write_text("not a recording", encoding="utf-8")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))

    assert list_recordings(tmp_path) == [new, old]


def test_list_recordings_tolerates_missing_folder(tmp_path):
    assert list_recordings(tmp_path / "missing") == []


def test_recording_label_uses_file_name(tmp_path):
    assert recording_label(tmp_path / "demo.json") == "demo.json"


def test_rename_recording_appends_json(tmp_path):
    source = tmp_path / "recording.json"
    source.write_text("{}", encoding="utf-8")

    renamed = rename_recording(source, "demo")

    assert renamed == tmp_path / "demo.json"
    assert renamed.exists()
    assert not source.exists()


def test_rename_recording_rejects_paths(tmp_path):
    source = tmp_path / "recording.json"
    source.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        rename_recording(source, "nested/demo")


def test_rename_recording_rejects_existing_target(tmp_path):
    source = tmp_path / "recording.json"
    target = tmp_path / "demo.json"
    source.write_text("{}", encoding="utf-8")
    target.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        rename_recording(source, "demo.json")


def test_rename_recording_keeps_same_name(tmp_path):
    source = tmp_path / "recording.json"
    source.write_text("{}", encoding="utf-8")

    renamed = rename_recording(source, "recording.json")

    assert renamed == source
    assert source.exists()
