"""Save a table-and-Panda-only initial scene for chapter 5."""

from pathlib import Path
import shutil

from test_panda_initial_pose import main as render_initial_pose


def main():
    render_initial_pose()
    root = Path(__file__).resolve().parent
    source = root / "images" / "panda_initial_pose.png"
    for destination in (root / "libero_tabletop_test.png",
                        root.parent / "images" / "libero_tabletop_test.png"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(destination))
        print("Saved empty initial scene:", destination, flush=True)


if __name__ == "__main__":
    main()
