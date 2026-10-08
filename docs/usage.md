# Usage reference

[Back to README](../README.md)

## The config file

All settings live in a plain text `config.ini`. The app's **Settings** screen
edits this same file, so the GUI and command line always agree.

ClickReplay looks for the file in this order:

1. a path you pass with `--config`,
2. the `CLICKREPLAY_CONFIG` environment variable,
3. **`config.ini` next to the program** (great for a portable folder you can
   copy to another PC),
4. `%APPDATA%\ClickReplay\config.ini` (created automatically on first run).

See [`config.example.ini`](../config.example.ini) for a fully commented template.

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
| `directory` | `output` | Where timestamped recordings are saved by default |

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

## Build a double-click .exe

```powershell
pip install -e ".[build]"
pyinstaller packaging/clickreplay.spec
```

This produces `dist/ClickReplay.exe` — a single windowed executable that opens
the app. Drop a `config.ini` next to it to ship custom defaults.

> **Architecture note:** PyInstaller builds for the architecture of the machine
> it runs on; it cannot cross-compile. Build the **x64** executable on an x64
> Windows PC and the **ARM64** executable on an ARM64 PC.

### Automated release builds

The repository includes a GitHub Actions workflow
([`.github/workflows/build.yml`](../.github/workflows/build.yml)) that builds the
**x64** executable on a GitHub-hosted x64 runner and attaches it to the matching
release. It runs automatically when a `v*` tag is pushed, and can also be run
manually against an existing tag from the **Actions** tab. The ARM64 build is
attached separately from an ARM64 machine.

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
