"""A small Tkinter GUI for ClickReplay — Record, Play, and Settings.

The GUI is a thin shell over the same core used by the CLI. Recording and
playback run on a background thread so the window stays responsive; updates
are marshalled back onto the Tk main thread with ``root.after``.
"""

from __future__ import annotations

import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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


class ClickReplayApp:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = cfgmod.load_config()
        self._recorder: Recorder | None = None
        self._busy = False
        self._last_script_path: str | None = None

        root.title("ClickReplay")
        root.resizable(False, False)
        root.minsize(380, 240)

        self._monitors = list_monitors()
        self._build_ui()

    # ----- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

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
        self.monitor_box.grid(row=0, column=1, columnspan=2, sticky="we", **pad)

        # Speed
        ttk.Label(frm, text="Speed:").grid(row=1, column=0, sticky="w", **pad)
        self.speed_var = tk.StringVar(value=str(self.cfg.speed))
        ttk.Entry(frm, textvariable=self.speed_var, width=8).grid(
            row=1, column=1, sticky="w", **pad
        )
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Dry run (no clicks)", variable=self.dry_run_var).grid(
            row=1, column=2, sticky="w", **pad
        )

        # Action buttons
        self.record_btn = ttk.Button(frm, text="● Record", command=self.on_record)
        self.record_btn.grid(row=2, column=0, sticky="we", **pad)
        self.stop_btn = ttk.Button(frm, text="■ Stop", command=self.on_stop, state="disabled")
        self.stop_btn.grid(row=2, column=1, sticky="we", **pad)
        self.play_btn = ttk.Button(frm, text="▶ Play…", command=self.on_play)
        self.play_btn.grid(row=2, column=2, sticky="we", **pad)

        # Settings + status
        self.settings_btn = ttk.Button(frm, text="⚙ Settings", command=self.open_settings)
        self.settings_btn.grid(row=3, column=0, sticky="we", **pad)

        self.status_var = tk.StringVar(value="Ready.")
        status = ttk.Label(frm, textvariable=self.status_var, relief="sunken", anchor="w")
        status.grid(row=4, column=0, columnspan=3, sticky="we", padx=10, pady=(10, 4))

        hint = ttk.Label(
            frm,
            text=f"Stop: {self.cfg.stop_hotkey}   Waypoint: {self.cfg.waypoint_hotkey}   Abort play: Esc",
            foreground="#666",
        )
        hint.grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4))

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

    def _set_busy(self, busy: bool, *, recording: bool = False) -> None:
        self._busy = busy
        self.record_btn["state"] = "disabled" if busy else "normal"
        self.play_btn["state"] = "disabled" if busy else "normal"
        self.settings_btn["state"] = "disabled" if busy else "normal"
        self.stop_btn["state"] = "normal" if (busy and recording) else "disabled"

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
        out_path = str(Path(self.cfg.output_dir) / "recording.json")
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
            self.root.after(0, lambda: self._finish(f"Saved {n} events to {path}"))
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
        initial_dir = self.cfg.output_dir if Path(self.cfg.output_dir).is_dir() else "."
        path = filedialog.askopenfilename(
            title="Choose a recording to play",
            initialdir=initial_dir,
            initialfile=self._last_script_path or "",
            filetypes=[("ClickReplay recordings", "*.json"), ("All files", "*.*")],
        )
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
            self.root.after(0, lambda: self._finish("Playback complete."))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self._finish(f"Error: {exc}", error=True))

    # ----- shared finish -----------------------------------------------------

    def _finish(self, message: str, *, error: bool = False) -> None:
        try:
            self.root.deiconify()
        except tk.TclError:
            pass
        self._set_busy(False)
        self._set_status(message)
        if error:
            messagebox.showerror("ClickReplay", message)

    # ----- settings ----------------------------------------------------------

    def open_settings(self) -> None:
        SettingsWindow(self.root, self.cfg, on_saved=self._on_settings_saved)

    def _on_settings_saved(self, cfg: cfgmod.Config) -> None:
        self.cfg = cfg
        self.speed_var.set(str(cfg.speed))
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
