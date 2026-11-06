"""Package the Windows policy bridge without recordings or model weights."""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO = Path(__file__).resolve().parents[1]


def package(output: Path) -> int:
    files = {REPO / name for name in (
        "README.md", "pyproject.toml", "requirements/policy_robot.txt",
        "trajectories/policy_start.gcode", "docs/W10/DEPLOY_MIROBOT.md",
        "Mirobot_data/W10/L01_red/color_profile.json",
        "Mirobot_data/W10/L01_red/reference.jsonl", "Mirobot_data/W10/L01_red/source.gcode",
    )}
    for directory in ("common", "robot", "server", "tools", "docs/W9/d405"):
        files.update((REPO / directory).glob("*.py"))
    missing = [str(path.relative_to(REPO)) for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Package inputs missing: {missing}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial.zip")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(files):
                archive.write(path, Path("mirobot-policy") / path.relative_to(REPO))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return len(files)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=REPO / "dist/mirobot-policy-robot.zip")
    a = p.parse_args()
    count = package(a.output)
    print(f"{a.output}: {count} files, {a.output.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    main()
