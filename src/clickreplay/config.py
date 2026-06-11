"""Default configuration and INI config-file handling for ClickReplay.

The module-level constants are the built-in defaults. They are used directly
by the core ``Recorder`` and ``Player`` classes as fall-back values, and they
seed a :class:`Config` instance when no config file exists yet.

A user-editable ``config.ini`` is the single source of truth for the CLI and
the GUI. It is discovered in this order:

1. an explicit path passed to :func:`load_config`,
2. the ``CLICKREPLAY_CONFIG`` environment variable,
3. a ``config.ini`` sitting next to the program (the ``.exe`` when frozen, or
   the current working directory otherwise) — this makes "copy the folder and
   go" portable installs work,
4. ``%APPDATA%\\ClickReplay\\config.ini`` (created from defaults on first run).
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults (module-level constants) — fall-backs for the core classes
# ---------------------------------------------------------------------------

# Recording
RECORD_HOTKEY: str = "<f9>"             # pynput GlobalHotKeys format — stop recording
WAYPOINT_HOTKEY: str = "<f10>"          # mark a mouse waypoint without clicking

# Playback
DEFAULT_SPEED: float = 1.0              # 1.0 = real-time, 2.0 = double speed
DEFAULT_COUNTDOWN_SECS: int = 3         # seconds before playback begins
FAILSAFE_KEY: str = "escape"            # press to abort playback immediately
MIN_MOVE_DURATION: float = 0.05         # minimum seconds for a moveTo animation
MAX_MOVE_DURATION: float = 2.0          # cap so a long idle doesn't produce a crawl
DEFAULT_EASING: str = "easeInOutQuad"   # pyautogui tween function name

# Point-stop (dwell) — a pause applied during playback after each click,
# drag release, or waypoint, so viewers can follow every step. 0 disables it.
DEFAULT_POINT_STOP_SECS: float = 1.0

# Output / monitor
DEFAULT_OUTPUT_DIR: str = "output"      # where recordings are saved by default
DEFAULT_MONITOR: int = 0                # monitor index used when none is given

APP_NAME: str = "ClickReplay"
CONFIG_ENV_VAR: str = "CLICKREPLAY_CONFIG"
CONFIG_FILENAME: str = "config.ini"

_HEADER_COMMENT = (
    "; ClickReplay configuration file.\n"
    "; Edit the values below and save, then re-run ClickReplay to apply them.\n"
    "; Delete this file to restore the built-in defaults.\n"
    "\n"
)


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """All user-editable settings, defaulting to the constants above."""

    stop_hotkey: str = RECORD_HOTKEY
    waypoint_hotkey: str = WAYPOINT_HOTKEY
    speed: float = DEFAULT_SPEED
    countdown: int = DEFAULT_COUNTDOWN_SECS
    point_stop_seconds: float = DEFAULT_POINT_STOP_SECS
    easing: str = DEFAULT_EASING
    min_move_duration: float = MIN_MOVE_DURATION
    max_move_duration: float = MAX_MOVE_DURATION
    default_monitor: int = DEFAULT_MONITOR
    output_dir: str = DEFAULT_OUTPUT_DIR

    # -- INI (de)serialisation ------------------------------------------------

    def to_parser(self) -> configparser.ConfigParser:
        """Return a ConfigParser populated from this config."""
        parser = configparser.ConfigParser()
        parser["recording"] = {
            "stop_hotkey": self.stop_hotkey,
            "waypoint_hotkey": self.waypoint_hotkey,
        }
        parser["playback"] = {
            "speed": str(self.speed),
            "countdown": str(self.countdown),
            "point_stop_seconds": str(self.point_stop_seconds),
            "easing": self.easing,
            "min_move_duration": str(self.min_move_duration),
            "max_move_duration": str(self.max_move_duration),
            "default_monitor": str(self.default_monitor),
        }
        parser["output"] = {
            "directory": self.output_dir,
        }
        return parser

    @classmethod
    def from_parser(cls, parser: configparser.ConfigParser) -> "Config":
        """Build a Config from a ConfigParser, tolerating missing/bad values."""
        cfg = cls()  # start from defaults
        cfg.stop_hotkey = parser.get("recording", "stop_hotkey", fallback=cfg.stop_hotkey)
        cfg.waypoint_hotkey = parser.get(
            "recording", "waypoint_hotkey", fallback=cfg.waypoint_hotkey
        )
        cfg.speed = _getfloat(parser, "playback", "speed", cfg.speed)
        cfg.countdown = _getint(parser, "playback", "countdown", cfg.countdown)
        cfg.point_stop_seconds = _getfloat(
            parser, "playback", "point_stop_seconds", cfg.point_stop_seconds
        )
        cfg.easing = parser.get("playback", "easing", fallback=cfg.easing)
        cfg.min_move_duration = _getfloat(
            parser, "playback", "min_move_duration", cfg.min_move_duration
        )
        cfg.max_move_duration = _getfloat(
            parser, "playback", "max_move_duration", cfg.max_move_duration
        )
        cfg.default_monitor = _getint(
            parser, "playback", "default_monitor", cfg.default_monitor
        )
        cfg.output_dir = parser.get("output", "directory", fallback=cfg.output_dir)
        return cfg


# ---------------------------------------------------------------------------
# Tolerant getters
# ---------------------------------------------------------------------------

def _getfloat(parser: configparser.ConfigParser, section: str, option: str, default: float) -> float:
    try:
        return parser.getfloat(section, option, fallback=default)
    except ValueError:
        return default


def _getint(parser: configparser.ConfigParser, section: str, option: str, default: int) -> int:
    try:
        return parser.getint(section, option, fallback=default)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _program_dir() -> Path:
    """Directory of the running program — the .exe folder when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def appdata_config_path() -> Path:
    """Return the per-user config location under %APPDATA%."""
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME / CONFIG_FILENAME


def config_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Resolve which config file to use (see module docstring for order)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env)
    portable = _program_dir() / CONFIG_FILENAME
    if portable.exists():
        return portable
    return appdata_config_path()


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_config(
    path: str | os.PathLike[str] | None = None,
    *,
    create_default: bool = True,
) -> Config:
    """Load configuration, falling back to defaults for anything missing.

    When no config file exists and *create_default* is True, a default file is
    written to the resolved location so the user can discover and edit it.
    """
    p = config_path(path)
    if p.exists():
        parser = configparser.ConfigParser()
        try:
            parser.read(p, encoding="utf-8")
            return Config.from_parser(parser)
        except (OSError, configparser.Error):
            return Config()

    cfg = Config()
    if create_default:
        try:
            save_config(cfg, p)
        except OSError:
            pass  # read-only location — fall back to in-memory defaults
    return cfg


def save_config(cfg: Config, path: str | os.PathLike[str] | None = None) -> Path:
    """Write *cfg* to an INI file and return the resolved path."""
    p = Path(path) if path is not None else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(_HEADER_COMMENT)
        cfg.to_parser().write(f)
    return p
