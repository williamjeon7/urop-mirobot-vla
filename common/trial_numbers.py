"""Keep trial folders numbered 1..N per colour, following what is actually on disk.

Deleting a folder frees its number: the folders after it move down by one (I2red -> I1red)
and the next run takes N+1. Renaming also rewrites the names and paths stored inside the
folder. A folder whose run is still active is never renamed; compaction then waits.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re

from common.recording_names import recording_number

TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".csv", ".txt"}


@contextmanager
def numbering_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".trial_numbers.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def is_active(directory):
    """A run is active while its launcher process is alive and has not finished."""
    path = Path(directory) / "launch.json"
    if not path.is_file():
        return False
    try:
        launch = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return True  # being written right now
    return launch.get("status") == "starting" and _alive(launch.get("pid"))


def trials(root, color):
    """[(number, path)] for one colour (None = legacy names without colour), sorted."""
    found = []
    for path in Path(root).iterdir():
        number = recording_number(path.name, color)
        if path.is_dir() and number is not None:
            found.append((number, path))
    return sorted(found)


def rename_trial(root, old, new):
    """Rename folder `old` to `new` and rewrite names stored inside it."""
    root = Path(root).absolute()
    source, target = root / old, root / new
    # The Windows original keeps its own name; keep that pointer unchanged.
    launch_path = source / "launch.json"
    windows = {}
    if launch_path.is_file():
        launch = json.loads(launch_path.read_text(encoding="utf-8"))
        windows = {"bridge_recording_name": launch.get("bridge_recording_name"),
                   "video_source_name": (launch.get("video_transfer") or {}).get("source_name")}
    source.rename(target)
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![0-9])")
    for path in sorted(target.rglob("*")):
        if path.is_file() and path.name.startswith(old) and pattern.match(path.name):
            renamed = path.with_name(new + path.name[len(old):])
            path.rename(renamed)
            path = renamed
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            updated = pattern.sub(new, text)
            if updated != text:
                path.write_text(updated, encoding="utf-8")
    if windows:
        launch_path = target / "launch.json"
        launch = json.loads(launch_path.read_text(encoding="utf-8"))
        if "bridge_recording_name" in launch:
            launch["bridge_recording_name"] = windows["bridge_recording_name"]
        if isinstance(launch.get("video_transfer"), dict) and windows["video_source_name"]:
            launch["video_transfer"]["source_name"] = windows["video_source_name"]
        launch_path.write_text(json.dumps(launch, indent=2, ensure_ascii=False), encoding="utf-8")
    with (target / "renumber_history.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps({"from": old, "to": new}) + "\n")
    return target


def compact(root, color):
    """Renumber one colour to 1..N. Returns {old: new}; empty when nothing moved or a run is active."""
    found = trials(root, color)
    if any(is_active(path) for _, path in found):
        return {}
    moved = {}
    for index, (number, path) in enumerate(found, start=1):
        if number != index:
            new = f"I{index}{color or ''}"
            rename_trial(root, path.name, new)
            moved[path.name] = new
    return moved


def reserve(root, color):
    """Compact, then create the next folder I{N+1}{color}."""
    with numbering_lock(root):
        compact(root, color)
        number = max((n for n, _ in trials(root, color)), default=0) + 1
        while True:
            directory = Path(root) / f"I{number}{color or ''}"
            try:
                directory.mkdir()
                return directory
            except FileExistsError:
                number += 1


def discard_if_never_started(directory, launch):
    """Remove a trial folder whose policy never started (failed during setup): it is not a trial,
    so it must not take a number. Returns True when removed."""
    import shutil
    directory = Path(directory)
    if (directory / "policy").exists():
        return False
    print(f"정책 시작 전에 실패해 시행으로 남기지 않습니다: {directory.name} ({launch.get('error')})", flush=True)
    shutil.rmtree(directory, ignore_errors=True)
    return True


def compact_all(root, colors):
    with numbering_lock(root):
        return {color: compact(root, color) for color in colors}
