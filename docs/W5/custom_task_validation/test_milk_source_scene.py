"""Render the official living-room tabletop scene that uses the same milk asset."""

import json

from test_custom_task_variants import ROOT, cv2, OffScreenRenderEnv


def main():
    relative = ("libero/libero/bddl_files/libero_90/"
                "LIVING_ROOM_SCENE2_pick_up_the_milk_and_put_it_in_the_basket.bddl")
    source = ROOT / relative
    env = OffScreenRenderEnv(
        bddl_file_name=str(source), initialization_noise=None,
        camera_names=["agentview"], camera_heights=512, camera_widths=512,
    )
    try:
        env.seed(0)
        obs = env.reset()
        milk = env.env.objects_dict["milk_1"]
        if type(milk).__name__ != "Milk":
            raise RuntimeError("The source scene did not instantiate the registered Milk model.")
        folder = ROOT / "images"
        folder.mkdir(parents=True, exist_ok=True)
        image = folder / "milk_source_scene.png"
        frame = cv2.cvtColor(obs["agentview_image"][::-1], cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(image), frame):
            raise RuntimeError("Could not save the milk source scene.")
        position = env.sim.data.body_xpos[env.env.obj_body_id["milk_1"]].tolist()
        result = {
            "source_bddl": relative, "problem": env.problem_name,
            "language": env.language_instruction, "seed": 0,
            "image": image.name, "milk_instance": "milk_1",
            "milk_type": "milk", "model_class": type(milk).__name__,
            "objects": sorted(env.env.objects_dict),
            "milk_position_m": position, "initial_goal": bool(env.check_success()),
            "scope": "Unmodified official source scene; reset and rendering only, no robot action.",
        }
        (folder / "milk_source_scene.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    main()
