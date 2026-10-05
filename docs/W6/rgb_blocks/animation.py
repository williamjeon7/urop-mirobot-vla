"""Render an actual LIBERO simulation as an in-memory, looping GIF."""

import base64
import io
import math

import cv2
import numpy as np
from PIL import Image
from robosuite.utils.transform_utils import mat2quat

if __package__:
    from .preview import BLOCK_SIZE_MM, SEED, create_env
else:
    from preview import BLOCK_SIZE_MM, SEED, create_env


def camera_quaternion(eye, target):
    """MuJoCo cameras look down local -Z with local +Y pointing up."""
    back = eye - target
    back /= np.linalg.norm(back)
    right = np.cross([0.0, 0.0, 1.0], back)
    right /= np.linalg.norm(right)
    up = np.cross(back, right)
    xyzw = mat2quat(np.column_stack([right, up, back]))
    return xyzw[[3, 0, 1, 2]]


def render_animation(duration_s=4.0, fps=20, resolution=480,
                     camera_sweep_deg=15.0, size_mm=None, seed=SEED):
    """Return GIF bytes, without writing an image/video file or opening a port."""
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("duration_s must be finite and positive.")
    if not isinstance(fps, int) or fps < 1:
        raise ValueError("fps must be a positive integer.")
    if not math.isfinite(camera_sweep_deg):
        raise ValueError("camera_sweep_deg must be finite.")
    size_mm = BLOCK_SIZE_MM if size_mm is None else size_mm
    env = create_env(size_mm=size_mm, resolution=resolution, seed=seed,
                     ignore_done=True)
    frames = []
    count = max(2, round(duration_s * fps))
    try:
        env.reset()
        camera_id = env.sim.model.camera_name2id("agentview")
        initial_eye = env.sim.model.cam_pos[camera_id].copy()
        target = np.array([-0.1, 0.0, 0.92])
        offset = initial_eye - target
        control_freq = env.env.control_freq
        step = 0
        for index in range(count):
            # Gently change the camera angle to show all cube faces.
            # The blocks and Panda retain their physical simulation states.
            if camera_sweep_deg:
                angle = math.radians(camera_sweep_deg) * math.sin(2 * math.pi * index / count)
                cosine, sine = math.cos(angle), math.sin(angle)
                rotation = np.array([[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1]])
                eye = target + rotation @ offset
                env.sim.model.cam_pos[camera_id] = eye
                env.sim.model.cam_quat[camera_id] = camera_quaternion(eye, target)
            target_step = round((index + 1) * control_freq / fps)
            while step < target_step:
                env.step([0, 0, 0, 0, 0, 0, -1])
                step += 1
            env.sim.forward()
            rgb = cv2.flip(env.sim.render(width=resolution, height=resolution,
                                         camera_name="agentview"), 0)
            cv2.putText(rgb, "RGB cubes | {:g} mm | {:.1f}s".format(size_mm, index / fps),
                        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1, cv2.LINE_AA)
            frames.append(Image.fromarray(rgb))
    finally:
        env.close()

    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:],
                   duration=max(10, round(1000 / fps)), loop=0, optimize=False)
    return buffer.getvalue()


def show_animation(**settings):
    """Embed a looping GIF directly in a VS Code/Jupyter cell output."""
    from IPython.display import HTML, display

    gif = render_animation(**settings)
    encoded = base64.b64encode(gif).decode("ascii")
    display(HTML('<img alt="LIBERO RGB cube simulation" '
                 'src="data:image/gif;base64,' + encoded + '" />'))
