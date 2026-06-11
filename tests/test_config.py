"""Tests for configuration defaults and INI loading/saving."""

from clickreplay import config as cfgmod


def test_defaults_match_constants():
    c = cfgmod.Config()
    assert c.speed == cfgmod.DEFAULT_SPEED
    assert c.point_stop_seconds == cfgmod.DEFAULT_POINT_STOP_SECS
    assert c.stop_hotkey == cfgmod.RECORD_HOTKEY
    assert c.output_dir == cfgmod.DEFAULT_OUTPUT_DIR


def test_ini_round_trip(tmp_path):
    p = tmp_path / "config.ini"
    c = cfgmod.Config(
        speed=2.0,
        point_stop_seconds=0.5,
        stop_hotkey="<f8>",
        output_dir="recs",
        default_monitor=1,
    )
    cfgmod.save_config(c, p)
    loaded = cfgmod.load_config(p)

    assert loaded.speed == 2.0
    assert loaded.point_stop_seconds == 0.5
    assert loaded.stop_hotkey == "<f8>"
    assert loaded.output_dir == "recs"
    assert loaded.default_monitor == 1


def test_load_missing_creates_default_file(tmp_path):
    p = tmp_path / "sub" / "config.ini"
    c = cfgmod.load_config(p)
    assert p.exists()
    assert c.speed == cfgmod.DEFAULT_SPEED


def test_load_missing_without_create(tmp_path):
    p = tmp_path / "nope.ini"
    c = cfgmod.load_config(p, create_default=False)
    assert not p.exists()
    assert c.speed == cfgmod.DEFAULT_SPEED


def test_bad_values_fall_back_to_defaults(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text("[playback]\nspeed = not_a_number\ncountdown = oops\n", encoding="utf-8")
    c = cfgmod.load_config(p)
    assert c.speed == cfgmod.DEFAULT_SPEED
    assert c.countdown == cfgmod.DEFAULT_COUNTDOWN_SECS


def test_config_path_prefers_env(tmp_path, monkeypatch):
    target = tmp_path / "custom.ini"
    monkeypatch.setenv(cfgmod.CONFIG_ENV_VAR, str(target))
    assert cfgmod.config_path() == target


def test_config_path_explicit_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.CONFIG_ENV_VAR, str(tmp_path / "env.ini"))
    explicit = tmp_path / "explicit.ini"
    assert cfgmod.config_path(explicit) == explicit
