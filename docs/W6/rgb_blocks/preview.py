"""Render the cubes in memory. Set BLOCK_SIZE_MM in objects.py to resize."""

import base64
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Prefer the W6 profile on OASYS; reuse the working W5 profile on another PC.
w6_config = ROOT.parent / ".libero"
if (w6_config / "config.yaml").is_file():
    os.environ.setdefault("LIBERO_CONFIG_PATH", str(w6_config))
os.environ.setdefault("MUJOCO_GL", "wgl" if sys.platform == "win32" else "egl")

import numpy as np
from PIL import Image
from libero.libero.envs import OffScreenRenderEnv

if __package__:
    from .objects import BLOCK_SIZE_MM, register_blocks
    from .tasks import task_spec
else:
    from objects import BLOCK_SIZE_MM, register_blocks
    from tasks import task_spec

# 렌더링 설정도 여기서 숫자로 변경할 수 있습니다.
RESOLUTION = 640
SEED = 0


def create_env(size_mm=None, resolution=RESOLUTION, seed=SEED,
               cameras=("agentview",), ignore_done=False, task="scene"):
    """Construct the same RGB scene for a still preview or live viewer."""
    if size_mm is None:
        size_mm = BLOCK_SIZE_MM
    # These fixed BDDL regions allow at most 120 mm cubes with separation.
    if not np.isfinite(size_mm) or not 0 < size_mm <= 120:
        raise ValueError("This tabletop layout supports 0 < BLOCK_SIZE_MM <= 120.")
    if resolution < 1:
        raise ValueError("RESOLUTION must be positive.")
    edge_m = size_mm / 1000
    spec = task_spec(task)
    register_blocks(edge_m)
    env = OffScreenRenderEnv(
        bddl_file_name=str(spec["bddl_file"]),
        robots=["Panda"], initialization_noise=None,
        camera_names=list(cameras),
        camera_heights=resolution,
        camera_widths=resolution,
        horizon=1000,
        ignore_done=ignore_done,
    )
    env.rgb_task = spec
    env.rgb_size_mm = size_mm
    env.seed(seed)
    return env


def scene_state(env, size_mm=None, require_contact=False):
    """Check the prepared scene and report current world poses in memory.

    The BDDL goal checks placement only; it does not evaluate a pickup.
    """
    if size_mm is None:
        size_mm = env.rgb_size_mm
    scene = env.env
    spec = env.rgb_task
    expected = {color + "_block_1" for color in ("red", "green", "blue")}
    if set(scene.objects_dict) != expected or scene.fixtures_dict:
        raise RuntimeError("Expected only the three RGB objects on the tabletop.")
    interested = ([spec["target_object"]] if spec["target_object"] else sorted(expected))
    if set(scene.obj_of_interest) != set(interested):
        raise RuntimeError("The BDDL target does not match the selected task.")
    if env.language_instruction.lower() != spec["language"].rstrip(".").lower():
        raise RuntimeError("The BDDL instruction does not match the selected task.")
    checks = {"({})".format(" ".join(state)): bool(scene._eval_predicate(state))
              for state in scene.parsed_problem["initial_state"]}
    if not checks or not all(checks.values()) or not env.check_success():
        raise RuntimeError("The RGB blocks must remain in their initial table regions.")
    rows = {}
    table_geom = env.sim.model.geom_name2id("table_collision")
    contact_pairs = {frozenset((contact.geom1, contact.geom2))
                     for contact in env.sim.data.contact[:env.sim.data.ncon]}
    colors = {"red": (1, 0, 0, 1), "green": (0, 1, 0, 1), "blue": (0, 0, 1, 1)}
    for name, obj in scene.objects_dict.items():
        collision = env.sim.model.geom_name2id(obj.contact_geoms[0])
        visual = env.sim.model.geom_name2id(obj.visual_geoms[0])
        size = env.sim.model.geom_size[collision]
        if not (np.allclose(size, size_mm / 2000)
                and np.allclose(env.sim.model.geom_size[visual], size)):
            raise RuntimeError("Render and collision dimensions disagree: " + name)
        rgba = env.sim.model.geom_rgba[visual]
        if not np.allclose(rgba, colors[obj.color]):
            raise RuntimeError("The block color does not match its BDDL type: " + name)
        touching_table = frozenset((collision, table_geom)) in contact_pairs
        if require_contact and not touching_table:
            raise RuntimeError("Cube did not settle on the table: " + name)
        body_id = scene.obj_body_id[name]
        rows[name] = {
            "edge_length_mm": size_mm,
            "xyz_m": env.sim.data.body_xpos[body_id].tolist(),
            "quaternion_wxyz": env.sim.data.body_xquat[body_id].tolist(),
            "rgba": rgba.tolist(),
            "mass_kg": float(env.sim.model.body_mass[body_id]),
            "table_contact": touching_table,
        }
    return {
        "task": spec["name"], "instruction": spec["language"],
        "target_object": spec["target_object"],
        "bddl": str(spec["bddl_file"].relative_to(ROOT)),
        "pickup_implemented": False, "goal_kind": "placement",
        "placement_ok": True, "initial_checks": checks,
        "table_top_z_m": float(scene.table_offset[2]), "blocks": rows,
    }


def render_scene(size_mm=None, resolution=RESOLUTION, seed=SEED, task="scene"):
    """Return (PIL image, scene metadata) without saving any files."""
    if size_mm is None:
        size_mm = BLOCK_SIZE_MM
    env = create_env(size_mm=size_mm, resolution=resolution, seed=seed,
                     ignore_done=True, task=task)
    try:
        obs = env.reset()
        # Let gravity settle the free objects; do not run a pickup action.
        for _ in range(50):
            obs, _, _, _ = env.step(np.zeros(7, dtype=np.float32))
        result = scene_state(env, size_mm=size_mm, require_contact=True)
        # Copy the frame before closing the renderer. MuJoCo images are upside-down.
        image = Image.fromarray(obs["agentview_image"][::-1].copy())
        result.update(size_mm=size_mm, seed=seed)
        return image, result
    finally:
        env.close()


def main():
    image, result = render_scene()
    print(json.dumps(result, indent=2), file=sys.stderr)
    # Emit an inline image from RAM; no PNG/JPEG file is written.
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    print("data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"))


if __name__ == "__main__":
    main()
