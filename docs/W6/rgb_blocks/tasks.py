"""Select the RGB scene or a colour-specific pick up task."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
TASK_NAMES = ("scene", "red", "green", "blue")


def task_spec(task="scene"):
    """Return task metadata. scene checks placement; colour tasks check Up (z >= 1.0 m)."""
    if task not in TASK_NAMES:
        raise ValueError("Unknown RGB task {!r}; choose from {}.".format(task, TASK_NAMES))
    if task == "scene":
        bddl_file = ROOT / "tabletop.bddl"
        language = "Display the red green and blue cubes on the table"
        target_object = None
    else:
        bddl_file = ROOT / "tasks" / (task + ".bddl")
        language = "Pick up the {} block on the table.".format(task)
        target_object = task + "_block_1"
    return {
        "name": task,
        "bddl_file": bddl_file,
        "language": language,
        "target_object": target_object,
        "pickup_implemented": task != "scene",
        "goal_kind": "placement" if task == "scene" else "pickup",
    }
