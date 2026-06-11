"""Command-line interface for ClickReplay."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click

from . import config as cfgmod
from .monitors import list_monitors, select_monitor
from .player import Player
from .recorder import Recorder
from .script import load_script, save_script, script_summary


@click.group()
@click.version_option(package_name="clickreplay")
def main() -> None:
    """ClickReplay — record and replay mouse/keyboard input for screen demos."""


# ── monitors ─────────────────────────────────────────────────────────────

@main.command()
def monitors() -> None:
    """List connected monitors and their indices."""
    for m in list_monitors():
        tag = " (primary)" if m.is_primary else ""
        click.echo(
            f"  [{m.index}] {m.name or 'Unknown'}  "
            f"{m.width}x{m.height}  at ({m.x},{m.y}){tag}"
        )


# ── record ───────────────────────────────────────────────────────────────

@main.command()
@click.option(
    "--monitor", "monitor_idx", type=int, default=None,
    help="Monitor index (from 'clickreplay monitors'). Defaults to config.",
)
@click.option(
    "--output", "-o", "output_path", default=None,
    help="Output JSON file path. Defaults to <output_dir>/recording.json.",
)
@click.option(
    "--config", "config_file", default=None,
    help="Path to a config.ini to use instead of the default.",
)
def record(monitor_idx: int | None, output_path: str | None, config_file: str | None) -> None:
    """Record mouse and keyboard events on a monitor."""
    cfg = cfgmod.load_config(config_file)

    if monitor_idx is None:
        monitor_idx = cfg.default_monitor
    try:
        mon = select_monitor(monitor_idx)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output_path is None:
        output_path = str(Path(cfg.output_dir) / "recording.json")

    click.echo(
        f"Recording on monitor [{mon.index}] {mon.name} "
        f"({mon.width}x{mon.height})"
    )
    click.echo(
        f"Press {cfg.stop_hotkey} to stop, "
        f"{cfg.waypoint_hotkey} to mark a waypoint (move-to without clicking)."
    )
    click.echo()
    for i in range(cfg.countdown, 0, -1):
        click.echo(f"  Starting in {i}...")
        time.sleep(1)

    rec = Recorder(
        mon,
        stop_hotkey=cfg.stop_hotkey,
        waypoint_hotkey=cfg.waypoint_hotkey,
    )
    rec.start()
    script = rec.wait()

    path = save_script(script, output_path)
    click.echo(f"\nSaved {len(script.events)} events to {path}")


# ── play ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("script_path")
@click.option("--monitor", "monitor_idx", type=int, default=None, help="Override target monitor index.")
@click.option("--speed", type=float, default=None, help="Playback speed multiplier (e.g. 2.0 = double).")
@click.option("--countdown", type=int, default=None, help="Seconds to wait before starting.")
@click.option(
    "--point-stop", "point_stop", type=float, default=None,
    help="Dwell seconds after each click/waypoint (overrides config; 0 disables).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Print actions without executing them.")
@click.option("--config", "config_file", default=None, help="Path to a config.ini to use instead of the default.")
def play(
    script_path: str,
    monitor_idx: int | None,
    speed: float | None,
    countdown: int | None,
    point_stop: float | None,
    dry_run: bool,
    config_file: str | None,
) -> None:
    """Replay a recorded script (press Escape to abort)."""
    cfg = cfgmod.load_config(config_file)

    try:
        script = load_script(script_path)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        click.echo(f"Error loading script: {exc}", err=True)
        sys.exit(1)

    target_mon = None
    if monitor_idx is not None:
        try:
            target_mon = select_monitor(monitor_idx)
        except ValueError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

    speed_val = speed if speed is not None else cfg.speed
    player = Player(
        script,
        target_monitor=target_mon,
        speed=speed_val,
        countdown=countdown if countdown is not None else cfg.countdown,
        point_stop=point_stop if point_stop is not None else cfg.point_stop_seconds,
        easing=cfg.easing,
        min_move_duration=cfg.min_move_duration,
        max_move_duration=cfg.max_move_duration,
        dry_run=dry_run,
    )

    suffix = ", dry-run" if dry_run else ""
    click.echo(f"Playing {script_path} (speed={speed_val}x{suffix}, press Escape to abort)")
    player.play()


# ── info ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("script_path")
def info(script_path: str) -> None:
    """Show a summary of a recorded script."""
    try:
        script = load_script(script_path)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    summary = script_summary(script)
    click.echo(f"  File:        {script_path}")
    click.echo(f"  Monitor:     {summary['monitor']}")
    click.echo(f"  Recorded at: {summary['recorded_at']}")
    click.echo(f"  Description: {summary['description'] or '(none)'}")
    click.echo(f"  Events:      {summary['total_events']}")
    click.echo(f"  Duration:    {summary['duration_secs']}s")
    click.echo(f"  Breakdown:   {summary['event_counts']}")


if __name__ == "__main__":  # pragma: no cover
    main()
