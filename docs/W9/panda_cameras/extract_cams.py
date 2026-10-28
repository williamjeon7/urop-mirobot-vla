"""Extract agentview / eye_in_hand camera geometry from the W6 RGB tabletop scene.

    conda activate libero
    LIBERO_CONFIG_PATH=docs/W6/.libero python -B docs/W9/panda_cameras/extract_cams.py

Writes cameras.json and the *_raw / *_flipud PNGs next to this file.
"""
import json
import math
import os
import sys

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "W6", "rgb_blocks"))

import numpy as np
from PIL import Image
from preview import create_env

OUT = os.path.dirname(os.path.abspath(__file__))
RES = 256  # policy input size

env = create_env(resolution=RES, cameras=("agentview", "robot0_eye_in_hand"))
obs = env.reset()
inner = env.env
sim = inner.sim
m, d = sim.model, sim.data


def body_pose(name):
    i = m.body_name2id(name)
    return d.body_xpos[i].copy(), d.body_xmat[i].reshape(3, 3).copy()


def site_pos(name):
    return d.site_xpos[m.site_name2id(name)].copy()


base_p, base_R = body_pose("robot0_base")
table_offset = np.array(inner.table_offset, dtype=float)
table_size = np.array(inner.table_full_size, dtype=float)
# table top from the actual collision geom (box: centre z + half height)
table_geoms = {}
for gi in range(m.ngeom):
    gname = m.geom_id2name(gi) or ""
    if "table" in gname and m.geom_type[gi] == 6:
        table_geoms[gname] = float(d.geom_xpos[gi][2] + m.geom_size[gi][2])
print("table box geoms top z:", table_geoms)
table_top_z = max(table_geoms.values()) if table_geoms else float(table_offset[2])
eef = site_pos("gripper0_grip_site")


def to_base(p):
    return base_R.T @ (p - base_p)


def ray_table(origin, direction):
    if direction[2] >= 0:
        return None
    t = (table_top_z - origin[2]) / direction[2]
    return origin + t * direction, t


out = {
    "scene": "docs/W6/rgb_blocks tabletop.bddl (LIBERO_Tabletop_Manipulation), env.reset() seed 0",
    "robot0_base_world_m": base_p.tolist(),
    "robot0_base_R": base_R.tolist(),
    "table_top_z_world_m": table_top_z,
    "table_full_size_m": table_size.tolist(),
    "table_offset_world_m": table_offset.tolist(),
    "eef_grip_site_world_m": eef.tolist(),
    "eef_grip_site_in_base_m": to_base(eef).tolist(),
    "robot0_joint_pos_rad": [float(v) for v in obs["robot0_joint_pos"]],
    "cameras": {},
}

for cam in ("agentview", "robot0_eye_in_hand"):
    cid = m.camera_name2id(cam)
    p = d.cam_xpos[cid].copy()
    R = d.cam_xmat[cid].reshape(3, 3).copy()  # columns: cam x(right), y(up), z(back) in world
    fwd = -R[:, 2]
    up = R[:, 1]
    fovy = float(m.cam_fovy[cid])
    f_px = RES / (2 * math.tan(math.radians(fovy) / 2))
    pitch_down = math.degrees(math.asin(-fwd[2]))
    yaw = math.degrees(math.atan2(fwd[1], fwd[0]))
    info = {
        "parent_body": m.body_id2name(int(m.cam_bodyid[cid])),
        "local_pos_m": m.cam_pos[cid].tolist(),
        "local_quat_wxyz": m.cam_quat[cid].tolist(),
        "fovy_deg": fovy,
        "world_pos_m": p.tolist(),
        "pos_in_robot_base_m": to_base(p).tolist(),
        "height_above_table_m": float(p[2] - table_top_z),
        "forward_world": fwd.tolist(),
        "image_up_world": up.tolist(),
        "pitch_below_horizontal_deg": pitch_down,
        "yaw_of_forward_deg(world, 0=+x)": yaw,
        f"K_{RES}px": [[f_px, 0, RES / 2], [0, f_px, RES / 2], [0, 0, 1]],
    }
    hit = ray_table(p, fwd)
    if hit is not None:
        pt, t = hit
        info["center_ray_hits_table_world_m"] = pt.tolist()
        info["center_ray_hits_table_in_base_m"] = to_base(pt).tolist()
        info["center_ray_distance_m"] = float(t)
    # image corners -> table footprint
    th = math.tan(math.radians(fovy) / 2)
    corners = {}
    for name, (sx, sy) in {"top_left": (-1, 1), "top_right": (1, 1),
                           "bottom_left": (-1, -1), "bottom_right": (1, -1)}.items():
        dvec = R @ np.array([sx * th, sy * th, -1.0])
        h = ray_table(p, dvec / np.linalg.norm(dvec))
        corners[name] = None if h is None else to_base(h[0]).tolist()
    info["image_corners_on_table_in_base_m(top=image top in MuJoCo cam frame)"] = corners
    if cam == "robot0_eye_in_hand":
        info["offset_from_grip_site_world_m"] = (p - eef).tolist()
        hand_p, hand_R = body_pose("robot0_right_hand")
        info["offset_from_grip_site_in_hand_frame_m"] = (hand_R.T @ (p - eef)).tolist()
    out["cameras"][cam] = info

    img = obs[f"{cam}_image"]
    Image.fromarray(img).save(os.path.join(OUT, f"{cam}_raw.png"))
    Image.fromarray(img[::-1].copy()).save(os.path.join(OUT, f"{cam}_flipud.png"))

with open(os.path.join(OUT, "cameras.json"), "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
env.close()
