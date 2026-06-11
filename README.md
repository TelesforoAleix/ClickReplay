# ClickReplay

> **Record your mouse and keyboard, then replay them — for clean, repeatable screen demos.**

[![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)](#install)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/TelesforoAleix/ClickReplay/releases)
[![Tests](https://img.shields.io/badge/tests-25%20passing-brightgreen.svg)](#how-it-works)

ClickReplay captures your clicks, key presses, scrolls and drags into a small,
editable file, then plays them back with smooth, eased mouse movement. Point a
screen recorder (OBS, Xbox Game Bar, Teams, etc.) at the replay and you get a
polished walkthrough every time — no shaky cursor, no fumbled clicks.

> [!NOTE]
> **ClickReplay does not record video.** It reproduces your *actions*. Pair it
> with any screen-capture tool to record the result.

---

## Table of contents

- [Who it's for](#who-its-for)
- [Install](#install)
- [Quick start (command line)](#quick-start-command-line)
- [Using the app (GUI)](#using-the-app-gui)
- [The config file](#the-config-file)
- [Point-stop: pause on every step](#point-stop-pause-on-every-step)
- [Hotkeys](#hotkeys)
- [Commands](#commands)
- [How it works](#how-it-works)
- [Build a double-click .exe](#build-a-double-click-exe)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Who it's for

- **Just want to click buttons?** Use the **app** (a small window with Record
  and Play buttons), or a packaged `ClickReplay.exe` that needs nothing
  installed.
- **Comfortable with a terminal?** Use the **`clickreplay` command line**.

Both share the same engine and the same settings file.

---

## Install

### Option A — Download the app (easiest)

Grab `ClickReplay.exe` (see [Build a double-click .exe](#build-a-double-click-exe)
if you're producing it yourself), put it in a folder, and double-click it.
Nothing else to install.

### Option B — Install with pip (for developers)

```powershell
# from the project folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

# check it works
clickreplay --help
clickreplay monitors
```

---

## Quick start (command line)

```powershell
# 1. See your monitors and their numbers
clickreplay monitors

# 2. Record on monitor 0. Do your steps, then press F9 to stop.
clickreplay record --monitor 0 -o output/my-demo.json

# 3. Replay it (start your screen recorder first)
clickreplay play output/my-demo.json

# 4. Preview the steps without moving the mouse
clickreplay play output/my-demo.json --dry-run
```

Replay faster or slower with `--speed` (e.g. `--speed 1.5` or `--speed 0.7`).

---

## Using the app (GUI)

Launch it with `clickreplay-gui` (or double-click `ClickReplay.exe`).

1. Pick the **Monitor** that shows what you want to record.
2. Click **● Record**, wait for the countdown, then do your steps.
3. Press **F9** (or click **■ Stop**) to finish — the recording is saved.
4. Click **▶ Play…**, choose the file, and watch it replay.
5. Click **⚙ Settings** to change speed, hotkeys, the point-stop pause, and more.

Tick **Dry run** to preview a replay without actually clicking.

---

## The config file

All settings live in a plain text `config.ini`. The app's **Settings** screen
edits this same file, so the GUI and command line always agree.

ClickReplay looks for the file in this order:

1. a path you pass with `--config`,
2. the `CLICKREPLAY_CONFIG` environment variable,
3. **`config.ini` next to the program** (great for a portable folder you can
   copy to another PC),
4. `%APPDATA%\ClickReplay\config.ini` (created automatically on first run).

See [`config.example.ini`](config.example.ini) for a fully commented template.

| Setting | Default | Meaning |
|---|---|---|
| `stop_hotkey` | `<f9>` | Key that stops recording |
| `waypoint_hotkey` | `<f10>` | Key that drops a "move here" waypoint |
| `speed` | `1.0` | Playback speed (2.0 = twice as fast) |
| `countdown` | `3` | Seconds before recording/playback starts |
| `point_stop_seconds` | `1.0` | Pause after each click/waypoint (0 = off) |
| `easing` | `easeInOutQuad` | Mouse movement smoothing curve |
| `min_move_duration` / `max_move_duration` | `0.05` / `2.0` | Limits on how long a glide takes |
| `default_monitor` | `0` | Monitor used when none is given |
| `directory` | `output` | Where recordings are saved |

---

## Point-stop: pause on every step

When you replay a recording, ClickReplay can **pause briefly after each click,
drag, or waypoint** so viewers can actually see what happened. That pause is the
*point-stop*.

- Set a global default with `point_stop_seconds` in the config (or the Settings
  screen), or per-run with `clickreplay play file.json --point-stop 1.5`.
- Set it to `0` to turn pausing off.
- Want a longer pause at one specific spot? Open the recording (it's just JSON)
  and add `"hold": 2.0` to that event.
- The point-stop pause is **not** sped up or slowed down by `--speed`, so your
  steps stay readable even at high playback speed.

---

## Hotkeys

| When | Key | Does |
|---|---|---|
| Recording | **F9** | Stop recording |
| Recording | **F10** | Drop a waypoint (move the cursor here on replay, no click) |
| Playback | **Esc** | Abort immediately |
| Playback | slam mouse into a screen corner | Emergency abort (pyautogui failsafe) |

---

## Commands

| Command | What it does |
|---|---|
| `clickreplay monitors` | List displays and their indices |
| `clickreplay record --monitor N -o FILE` | Record until F9 |
| `clickreplay play FILE [--speed S] [--point-stop S] [--dry-run]` | Replay a recording |
| `clickreplay info FILE` | Show a summary of a recording |
| `clickreplay-gui` | Launch the app window |

Run any command with `--help` for all options.

---

## How it works

- **Recording** uses [`pynput`](https://pypi.org/project/pynput/) to listen for
  clicks, scrolls, keys, and drags. It stores *meaningful* positions (clicks,
  drag start/end, waypoints) rather than every tiny mouse wiggle, so recordings
  stay small and replay looks smooth.
- A recording is a small JSON file: monitor info plus a list of time-stamped
  events. You can edit it by hand to fix a coordinate or adjust timing.
- **Replay** uses [`pyautogui`](https://pypi.org/project/pyautogui/) to move,
  click, scroll, and type. Movement between points is re-created with an easing
  curve, and the point-stop pause is added after each step.
- Coordinates are stored relative to the monitor you recorded on, and are scaled
  proportionally if you replay on a differently-sized display.

---

## Build a double-click .exe

```powershell
pip install -e ".[build]"
pyinstaller packaging/clickreplay.spec
```

This produces `dist/ClickReplay.exe` — a single windowed executable that opens
the app. Drop a `config.ini` next to it to ship custom defaults.

> **Note:** one-file executables sometimes trip antivirus heuristics on first
> run, and they start a little slower than an installed copy. Both are normal
> for PyInstaller builds.

---

## Troubleshooting

**Clicks land in the wrong place.** Make sure you replay on the same monitor (or
size) you recorded on; use `--monitor` to choose. On high-DPI screens, keep the
display scale the same between recording and replay.

**Nothing happens / it clicks the wrong window.** Increase the `countdown` so you
have time to focus the target window before playback starts.

**`clickreplay monitors` shows too few displays.** Make sure all monitors are
connected and active in Windows Display Settings.

**Recording seems empty.** ClickReplay only records on the monitor you selected.
Clicks on other monitors are ignored.

---

## Project status

ClickReplay is a focused, single-purpose tool and is **stable for everyday use**.
It is Windows-only by design. The 25-test suite runs headless (no real input
devices required) and covers the recording format, configuration, recorder
logic, and playback timing including the point-stop behaviour.

For agents and contributors, [AGENTS.md](AGENTS.md) documents the architecture,
invariants, and extension points.

## Contributing

Issues and pull requests are welcome.

```powershell
# set up a dev environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Please keep tests headless and run `pytest` before opening a pull request. When
changing user-facing behaviour or commands, update this README in the same
change.

## License

Released under the [MIT License](LICENSE).
