"""A small Tkinter GUI for ClickReplay — Record, Play, and Settings.

The GUI is a thin shell over the same core used by the CLI. Recording and
playback run on a background thread so the window stays responsive; updates
are marshalled back onto the Tk main thread with ``root.after``.
"""

from __future__ import annotations

import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import config as cfgmod
from .monitors import MonitorInfo, list_monitors, select_monitor
from .player import Player
from .recorder import Recorder
from .script import load_script, save_script

_EASING_CHOICES = [
    "linear",
    "easeInQuad",
    "easeOutQuad",
    "easeInOutQuad",
    "easeInOutCubic",
    "easeInOutSine",
    "easeInOutExpo",
]


def list_recordings(output_dir: str | Path) -> list[Path]:
    """Return JSON recordings in *output_dir*, newest first."""
    base_dir = Path(output_dir)
    try:
        recordings = [p for p in base_dir.glob("*.json") if p.is_file()]
    except OSError:
        return []
    return sorted(
        recordings,
        key=lambda p: (_recording_mtime(p), p.name.lower()),
        reverse=True,
    )


def recording_label(recording: str | Path) -> str:
    """Return the label shown for a recording in the GUI picker."""
    return Path(recording).name


def rename_recording(recording: str | Path, new_name: str) -> Path:
    """Rename *recording* within its folder, appending .json when omitted."""
    source = Path(recording)
    clean_name = new_name.strip()
    if not clean_name or clean_name in {".", ".."}:
        raise ValueError("Recording name cannot be empty.")
    if "/" in clean_name or "\\" in clean_name:
        raise ValueError("Use a file name, not a path.")
    if not clean_name.lower().endswith(".json"):
        clean_name = f"{clean_name}.json"

    target = source.with_name(clean_name)
    if _same_path(source, target):
        return source
    if target.exists():
        raise FileExistsError(f"A recording named '{target.name}' already exists.")
    return source.rename(target)


def _recording_mtime(recording: Path) -> float:
    try:
        return recording.stat().st_mtime
    except OSError:
        return 0.0


def _same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).resolve(strict=False) == Path(right).resolve(strict=False)


class ClickReplayApp:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = cfgmod.load_config()
        self._recorder: Recorder | None = None
        self._busy = False
        self._last_script_path: str | None = None
        self._recordings: list[Path] = []

        root.title("ClickReplay")
        root.resizable(False, False)
        root.minsize(520, 280)

        self._monitors = list_monitors()
        self._build_ui()

    # ----- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=1)

        # Monitor selector
        ttk.Label(frm, text="Monitor:").grid(row=0, column=0, sticky="w", **pad)
        self.monitor_var = tk.StringVar()
        self.monitor_box = ttk.Combobox(
            frm, textvariable=self.monitor_var, state="readonly", width=34
        )
        self.monitor_box["values"] = [self._monitor_label(m) for m in self._monitors]
        if self._monitors:
            idx = min(self.cfg.default_monitor, len(self._monitors) - 1)
            self.monitor_box.current(max(idx, 0))
        self.monitor_box.grid(row=0, column=1, columnspan=3, sticky="we", **pad)

        # Speed
        ttk.Label(frm, text="Speed:").grid(row=1, column=0, sticky="w", **pad)
        self.speed_var = tk.StringVar(value=str(self.cfg.speed))
        ttk.Entry(frm, textvariable=self.speed_var, width=8).grid(
            row=1, column=1, sticky="w", **pad
        )
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Dry run (no clicks)", variable=self.dry_run_var).grid(
            row=1, column=2, columnspan=2, sticky="w", **pad
        )

        # Recording picker
        ttk.Label(frm, text="Recording:").grid(row=2, column=0, sticky="w", **pad)
        self.recording_var = tk.StringVar()
        self.recording_box = ttk.Combobox(
            frm,
            textvariable=self.recording_var,
            state="readonly",
            width=34,
            postcommand=self._refresh_recordings,
        )
        self.recording_box.grid(row=2, column=1, columnspan=2, sticky="we", **pad)
        self.rename_btn = ttk.Button(frm, text="Rename", command=self.on_rename)
        self.rename_btn.grid(row=2, column=3, sticky="we", **pad)

        # Action buttons
        self.record_btn = ttk.Button(frm, text="● Record", command=self.on_record)
        self.record_btn.grid(row=3, column=0, sticky="we", **pad)
        self.stop_btn = ttk.Button(frm, text="■ Stop", command=self.on_stop, state="disabled")
        self.stop_btn.grid(row=3, column=1, sticky="we", **pad)
        self.play_btn = ttk.Button(frm, text="▶ Play", command=self.on_play)
        self.play_btn.grid(row=3, column=2, sticky="we", **pad)

        # Settings + status
        self.settings_btn = ttk.Button(frm, text="⚙ Settings", command=self.open_settings)
        self.settings_btn.grid(row=3, column=3, sticky="we", **pad)

        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(frm, textvariable=self.status_var, relief="sunken", anchor="w")
        status.grid(row=4, column=0, columnspan=4, sticky="we", padx=10, pady=(10, 4))

        hint = ttk.Label(
            frm,
            text=f"Stop: {self.cfg.stop_hotkey}   Waypoint: {self.cfg.waypoint_hotkey}   Abort play: Esc",
            foreground="#666",
        )
        hint.grid(row=5, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 4))
        self._refresh_recordings()

    @staticmethod
    def _monitor_label(m: MonitorInfo) -> str:
        tag = " (primary)" if m.is_primary else ""
        return f"{m.index}: {m.name or 'Unknown'} {m.width}x{m.height}{tag}"

    # ----- helpers -----------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _selected_monitor(self) -> MonitorInfo | None:
        if not self._monitors:
            return None
        return self._monitors[self.monitor_box.current()]

    def _selected_recording(self) -> Path | None:
        idx = self.recording_box.current()
        if idx < 0 or idx >= len(self._recordings):
            return None
        return self._recordings[idx]

    def _refresh_recordings(self, select_path: str | Path | None = None) -> None:
        selected = Path(select_path) if select_path is not None else self._selected_recording()
        if selected is None and self._last_script_path is not None:
            selected = Path(self._last_script_path)

        self._recordings = list_recordings(self.cfg.output_dir)
        self.recording_box["values"] = [recording_label(p) for p in self._recordings]

        if not self._recordings:
            self.recording_var.set("")
            self._update_recording_controls()
            return

        selected_index = 0
        if selected is not None:
            for idx, recording in enumerate(self._recordings):
                if _same_path(recording, selected):
                    selected_index = idx
                    break
        self.recording_box.current(selected_index)
        self._update_recording_controls()

    def _update_recording_controls(self) -> None:
        has_recording = bool(self._recordings)
        self.recording_box["state"] = "disabled" if self._busy else "readonly"
        self.rename_btn["state"] = "normal" if (has_recording and not self._busy) else "disabled"

    def _set_busy(self, busy: bool, *, recording: bool = False) -> None:
        self._busy = busy
        self.record_btn["state"] = "disabled" if busy else "normal"
        self.play_btn["state"] = "disabled" if busy else "normal"
        self.settings_btn["state"] = "disabled" if busy else "normal"
        self.stop_btn["state"] = "normal" if (busy and recording) else "disabled"
        self._update_recording_controls()

    def _countdown(self, n: int, then) -> None:
        if n <= 0:
            then()
            return
        self._set_status(f"Starting in {n}…")
        self.root.after(1000, lambda: self._countdown(n - 1, then))

    # ----- record ------------------------------------------------------------

    def on_record(self) -> None:
        if self._busy:
            return
        mon = self._selected_monitor()
        if mon is None:
            messagebox.showerror("ClickReplay", "No monitor detected.")
            return
        self._set_busy(True, recording=True)
        out_path = str(cfgmod.default_recording_path(self.cfg.output_dir))
        self._countdown(
            self.cfg.countdown,
            lambda: self._begin_record(mon, out_path),
        )

    def _begin_record(self, mon: MonitorInfo, out_path: str) -> None:
        self._set_status(f"Recording… press {self.cfg.stop_hotkey} (or Stop) to finish.")
        self.root.iconify()  # get the window out of the way
        threading.Thread(
            target=self._record_worker, args=(mon, out_path), daemon=True
        ).start()

    def _record_worker(self, mon: MonitorInfo, out_path: str) -> None:
        try:
            import time
            time.sleep(0.4)  # let the minimise settle; avoid catching the button-up
            rec = Recorder(
                mon,
                stop_hotkey=self.cfg.stop_hotkey,
                waypoint_hotkey=self.cfg.waypoint_hotkey,
            )
            self._recorder = rec
            rec.start()
            script = rec.wait()
            path = save_script(script, out_path)
            self._last_script_path = str(path)
            n = len(script.events)
            self.root.after(
                0,
                lambda: self._finish(f"Saved {n} events to {path}", selected_recording=path),
            )
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            self.root.after(0, lambda: self._finish(f"Error: {exc}", error=True))
        finally:
            self._recorder = None

    def on_stop(self) -> None:
        if self._recorder is not None:
            self._recorder.stop()

    # ----- play --------------------------------------------------------------

    def on_play(self) -> None:
        if self._busy:
            return
        recording = self._selected_recording()
        if recording is None:
            path = self._ask_recording_file()
        else:
            path = str(recording)
        if not path:
            return

        try:
            speed = float(self.speed_var.get())
        except ValueError:
            messagebox.showerror("ClickReplay", "Speed must be a number.")
            return

        mon = self._selected_monitor()
        self._set_busy(True)
        self._countdown(
            self.cfg.countdown,
            lambda: self._begin_play(path, speed, mon),
        )

    def _ask_recording_file(self) -> str:
        initial_dir = self.cfg.output_dir if Path(self.cfg.output_dir).is_dir() else "."
        initial_file = Path(self._last_script_path).name if self._last_script_path else ""
        return filedialog.askopenfilename(
            title="Choose a recording to play",
            initialdir=initial_dir,
            initialfile=initial_file,
            filetypes=[("ClickReplay recordings", "*.json"), ("All files", "*.*")],
        )

    def _begin_play(self, path: str, speed: float, mon: MonitorInfo | None) -> None:
        dry = self.dry_run_var.get()
        self._set_status("Playing… press Esc to abort." if not dry else "Dry run…")
        if not dry:
            self.root.iconify()
        threading.Thread(
            target=self._play_worker, args=(path, speed, mon, dry), daemon=True
        ).start()

    def _play_worker(self, path: str, speed: float, mon: MonitorInfo | None, dry: bool) -> None:
        try:
            script = load_script(path)
            player = Player(
                script,
                target_monitor=mon,
                speed=speed,
                countdown=0,  # the GUI already counted down
                point_stop=self.cfg.point_stop_seconds,
                easing=self.cfg.easing,
                min_move_duration=self.cfg.min_move_duration,
                max_move_duration=self.cfg.max_move_duration,
                dry_run=dry,
            )
            player.play()
            self.root.after(0, lambda: self._finish("Playback complete.", selected_recording=path))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._finish(f"Error: {exc}", error=True))

    # ----- rename ------------------------------------------------------------

    def on_rename(self) -> None:
        if self._busy:
            return
        recording = self._selected_recording()
        if recording is None:
            messagebox.showinfo("ClickReplay", "Select a recording to rename.")
            return

        new_name = simpledialog.askstring(
            "ClickReplay — Rename Recording",
            "New recording name:",
            initialvalue=recording.name,
            parent=self.root,
        )
        if new_name is None:
            return

        try:
            new_path = rename_recording(recording, new_name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("ClickReplay — Rename Recording", str(exc), parent=self.root)
            return

        self._last_script_path = str(new_path)
        self._refresh_recordings(new_path)
        self._set_status(f"Renamed to {new_path.name}.")

    # ----- shared finish -----------------------------------------------------

    def _finish(
        self,
        message: str,
        *,
        error: bool = False,
        selected_recording: str | Path | None = None,
    ) -> None:
        try:
            self.root.deiconify()
        except tk.TclError:
            pass
        self._set_busy(False)
        self._refresh_recordings(selected_recording)
        self._set_status(message)
        if error:
            messagebox.showerror("ClickReplay", message)

    # ----- settings ----------------------------------------------------------

    def open_settings(self) -> None:
        SettingsWindow(self.root, self.cfg, on_saved=self._on_settings_saved)

    def _on_settings_saved(self, cfg: cfgmod.Config) -> None:
        self.cfg = cfg
        self.speed_var.set(str(cfg.speed))
        self._refresh_recordings()
        self._set_status("Settings saved.")


class SettingsWindow:
    """A modal-ish settings editor bound to the INI config file."""

    def __init__(self, parent: tk.Misc, cfg: cfgmod.Config, on_saved) -> None:
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title("ClickReplay — Settings")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        self.vars: dict[str, tk.StringVar] = {}
        frm = ttk.Frame(self.win, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        rows = [
            ("Stop hotkey", "stop_hotkey", cfg.stop_hotkey),
            ("Waypoint hotkey", "waypoint_hotkey", cfg.waypoint_hotkey),
            ("Speed", "speed", cfg.speed),
            ("Countdown (s)", "countdown", cfg.countdown),
            ("Point-stop dwell (s)", "point_stop_seconds", cfg.point_stop_seconds),
            ("Min move (s)", "min_move_duration", cfg.min_move_duration),
            ("Max move (s)", "max_move_duration", cfg.max_move_duration),
            ("Default monitor", "default_monitor", cfg.default_monitor),
        ]
        r = 0
        for label, key, value in rows:
            ttk.Label(frm, text=label + ":").grid(row=r, column=0, sticky="w", padx=8, pady=4)
            var = tk.StringVar(value=str(value))
            ttk.Entry(frm, textvariable=var, width=22).grid(row=r, column=1, sticky="we", padx=8, pady=4)
            self.vars[key] = var
            r += 1

        # Easing as a combobox
        ttk.Label(frm, text="Easing:").grid(row=r, column=0, sticky="w", padx=8, pady=4)
        self.easing_var = tk.StringVar(value=cfg.easing)
        ttk.Combobox(frm, textvariable=self.easing_var, values=_EASING_CHOICES, width=20).grid(
            row=r, column=1, sticky="we", padx=8, pady=4
        )
        r += 1

        # Output dir + browse
        ttk.Label(frm, text="Output folder:").grid(row=r, column=0, sticky="w", padx=8, pady=4)
        self.output_var = tk.StringVar(value=cfg.output_dir)
        out_row = ttk.Frame(frm)
        out_row.grid(row=r, column=1, sticky="we", padx=8, pady=4)
        ttk.Entry(out_row, textvariable=self.output_var, width=16).grid(row=0, column=0, sticky="we")
        ttk.Button(out_row, text="Browse…", command=self._browse).grid(row=0, column=1, padx=(6, 0))
        r += 1

        # Where the file lives
        ttk.Label(
            frm, text=f"File: {cfgmod.config_path()}", foreground="#666"
        ).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
        r += 1

        # Buttons
        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=2, sticky="e", padx=8, pady=(10, 0))
        ttk.Button(btns, text="Restore defaults", command=self._restore_defaults).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Cancel", command=self.win.destroy).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="Save", command=self._save).grid(row=0, column=2, padx=4)

    def _browse(self) -> None:
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.output_var.set(d)

    def _restore_defaults(self) -> None:
        d = cfgmod.Config()
        self.vars["stop_hotkey"].set(d.stop_hotkey)
        self.vars["waypoint_hotkey"].set(d.waypoint_hotkey)
        self.vars["speed"].set(str(d.speed))
        self.vars["countdown"].set(str(d.countdown))
        self.vars["point_stop_seconds"].set(str(d.point_stop_seconds))
        self.vars["min_move_duration"].set(str(d.min_move_duration))
        self.vars["max_move_duration"].set(str(d.max_move_duration))
        self.vars["default_monitor"].set(str(d.default_monitor))
        self.easing_var.set(d.easing)
        self.output_var.set(d.output_dir)

    def _save(self) -> None:
        try:
            cfg = cfgmod.Config(
                stop_hotkey=self.vars["stop_hotkey"].get().strip(),
                waypoint_hotkey=self.vars["waypoint_hotkey"].get().strip(),
                speed=float(self.vars["speed"].get()),
                countdown=int(float(self.vars["countdown"].get())),
                point_stop_seconds=float(self.vars["point_stop_seconds"].get()),
                easing=self.easing_var.get().strip() or cfgmod.DEFAULT_EASING,
                min_move_duration=float(self.vars["min_move_duration"].get()),
                max_move_duration=float(self.vars["max_move_duration"].get()),
                default_monitor=int(float(self.vars["default_monitor"].get())),
                output_dir=self.output_var.get().strip() or cfgmod.DEFAULT_OUTPUT_DIR,
            )
        except ValueError:
            messagebox.showerror(
                "ClickReplay — Settings",
                "Numeric fields (speed, countdown, dwell, durations, monitor) must be numbers.",
                parent=self.win,
            )
            return

        try:
            cfgmod.save_config(cfg)
        except OSError as exc:
            messagebox.showerror("ClickReplay — Settings", f"Could not save: {exc}", parent=self.win)
            return

        self.on_saved(cfg)
        self.win.destroy()


def main() -> None:
    """Entry point for the ``clickreplay-gui`` command."""
    root = tk.Tk()
    ClickReplayApp(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
