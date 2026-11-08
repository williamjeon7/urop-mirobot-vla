"""Renumber trial folders to I1..IN per colour now (the launcher also does this before and after each run).

    urop/bin/python -m tools.renumber_trials            # Mirobot_data/W10
"""
import argparse
from pathlib import Path

from common.recording_names import COLORS
from common.trial_numbers import compact_all

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path, nargs="?", default=REPO / "Mirobot_data/W10")
    moved = compact_all(parser.parse_args().root, COLORS)
    changes = [f"{old} -> {new}" for mapping in moved.values() for old, new in mapping.items()]
    print("\n".join(changes) if changes else "번호 변경 없음 (빈 번호가 없거나 실행 중인 시행이 있음)")


if __name__ == "__main__":
    main()
