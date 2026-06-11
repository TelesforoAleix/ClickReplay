# AGENTS.md — ClickReplay

Guidance for AI coding agents working in or with this repository. Humans should
read [README.md](README.md); this file is the machine-oriented companion.

## What this project is

ClickReplay is a small, **Windows-only** Python tool that records mouse/keyboard
input to an editable JSON file and replays it with smooth, eased motion. It is
used to produce repeatable screen demos (paired with an external screen
recorder). It does **not** capture video and has **no** browser/Business-Central
awareness — replay is pure OS-level automation via `pyautogui`.

## Tech stack

- Python 3.12+, packaged with setuptools (`pyproject.toml`).
- Runtime deps: `click`, `pynput`, `pyautogui`, `screeninfo`.
- GUI: `tkinter` (standard library). Config: `configparser` (standard library).
- Tests: `pytest`. Packaging: `pyinstaller` (see `packaging/clickreplay.spec`).

## Layout

```
src/clickreplay/
  __init__.py     # version
  cli.py          # click CLI: monitors / record / play / info
  gui.py          # Tkinter app + Settings window (entry: clickreplay-gui)
  recorder.py     # pynput listeners -> event list (Recorder)
  player.py       # pyautogui playback + point-stop (Player)
  script.py       # JSON load/save/validate + helpers
  monitors.py     # display enumeration, DPI awareness, coord transforms
  config.py       # defaults + Config dataclass + INI load/save
tests/            # headless tests (fake monitors, dry-run, monkeypatched sleep)
packaging/clickreplay.spec
config.example.ini
```

## Commands

```powershell
pip install -e ".[dev]"        # install with test deps
pytest                          # run the test suite (headless, no real input)
clickreplay --help              # CLI help
clickreplay monitors            # list displays
clickreplay record --monitor 0 -o output/demo.json   # record until F9
clickreplay play output/demo.json --dry-run           # preview without clicking
clickreplay-gui                 # launch the GUI
pyinstaller packaging/clickreplay.spec                # build dist/ClickReplay.exe
```

## Recording file format (v1)

A recording is JSON: `{ "metadata": {...}, "events": [...] }`.

- `metadata.monitor` = `{ index, name, width, height }`; plus `recorded_at`,
  `description`, `format_version`.
- Each event has `type` and `t` (seconds from start). Types: `mouse_move`,
  `mouse_click`, `mouse_down`, `mouse_up`, `mouse_scroll`, `key_press`,
  `key_release`, `wait`.
- Optional per-event keys: `waypoint` (bool — playback dwells after it) and
  `hold` (float — overrides the global point-stop dwell, in seconds).

## Conventions & invariants

- **Windows-only** by design: `monitors.py` sets per-monitor DPI awareness on
  import; `player.py` sets `pyautogui.FAILSAFE = True`.
- **Point-stop dwell is never scaled by `--speed`** — keep it that way so steps
  stay readable at high speed.
- The recorder stores meaningful positions only (clicks, drag ends, waypoints),
  not continuous motion; smooth movement is synthesised at playback time.
- The config file is the single source of truth shared by CLI and GUI. Resolution
  order: explicit path → `CLICKREPLAY_CONFIG` env → `config.ini` next to the
  program → `%APPDATA%\ClickReplay\config.ini`.
- Tests must stay headless: never require real input devices. Pass a fake
  `MonitorInfo` as `target_monitor`, use `dry_run=True`, or monkeypatch
  `clickreplay.player.pyautogui` and `Player._sleep`.

## Extending

- **New event type:** emit it in `recorder.py`, document it in `script.py`,
  handle it in `Player.play`'s dispatch, add a test.
- **New setting:** add a field to `config.Config`, include it in `to_parser`/
  `from_parser`, surface it in `gui.SettingsWindow`, document it in
  `config.example.ini` and the README table.
- After any change: run `pytest`, and update `README.md` if user-facing behavior
  or commands changed.

## Agentic auto-install prompt

Paste this into an AI assistant on a Windows machine to set the tool up:

```text
Set up the "ClickReplay" Python tool on my Windows machine:
1. Verify Python 3.12+ (`python --version`); if missing, tell me to install it.
2. From the ClickReplay project folder, create a venv: `python -m venv .venv`
3. Activate it: `.\.venv\Scripts\Activate.ps1`
4. Install it: `pip install -e ".[dev]"`
5. Verify: run `clickreplay --help` and `clickreplay monitors`.
6. Run `pytest` and report the result.
If any step fails, show the error and propose a fix before continuing.
```
