# -*- coding: utf-8 -*-
"""Export verified recordings and source files to the parent document folders."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT.parent / "custom_task_validation"
CHAPTERS = {
    "8": {"folder": "custom_task_validation", "cases": {"A": (40, 2), "B": (30, 2)}},
    "9": {"folder": "extended_task_validation", "cases": {
        "C": (30, 2), "D": (40, 2), "E": (30, 2), "F": (30, 2)}},
}
SCENES = {
    "A": ({"plate_1"}, {"flat_stove_1"}),
    "B": ({"milk_1", "plate_1"}, set()),
    "C": ({"custom_marker_box_1", "plate_1"}, set()),
    "D": ({"milk_1"}, {"raised_support_1"}),
    "E": ({"milk_1", "plate_1"}, set()),
    "F": ({"milk_1", "plate_1"}, set()),
}


def selected_chapters(chapter):
    return ("8", "9") if chapter == "both" else (chapter,)


def validate_results(chapter="both"):
    snapshots = {}
    for number in selected_chapters(chapter):
        config = CHAPTERS[number]
        media = ROOT / "images" / config["folder"]
        for task, (minimum_steps, expected_on_count) in config["cases"].items():
            result_path = media / "{}_result.json".format(task)
            if not result_path.is_file():
                raise FileNotFoundError("Run the simulator first: {}".format(result_path))
            snapshot = result_path.read_bytes()
            result = json.loads(snapshot.decode("utf-8"))
            action = result.get("action", {})
            checks = result.get("initial_on_checks", {})
            expected_objects, expected_fixtures = SCENES[task]
            valid = (result.get("task") == task and result.get("initial_goal") is False
                     and set(result.get("objects", [])) == expected_objects
                     and set(result.get("fixtures", [])) == expected_fixtures
                     and result.get("workspace") == "main_table"
                     and len(checks) == expected_on_count
                     and all(value is True for value in checks.values())
                     and result.get("initial_unwanted_contacts") == []
                     and action.get("goal_after_robot_action") is True
                     and action.get("goal_true_throughout_verification") is True
                     and action.get("verification_steps", 0) >= minimum_steps
                     and action.get("gripper_released") is True
                     and action.get("direct_object_state_changes_during_action") is False
                     and action.get("video") == "{}_robot_action.mp4".format(task))
            if task != "A":
                valid = (valid and action.get("grasp_confirmed") is True
                         and action.get("lift_height_m", 0) >= 0.1)
            if number == "9":
                metrics = result.get("final_metrics", {})
                valid = (valid and metrics.get("target_contact") is True
                         and result.get("initial_unwanted_support_contacts") == [])
                if task == "E":
                    valid = (valid and metrics.get("base_on") is True
                             and metrics.get("centered_upright_on") is True
                             and metrics.get("xy_center_distance_m", 1) <= 0.01
                             and metrics.get("milk_local_y_world_z", -1) >= 0.95)
            if not valid:
                raise RuntimeError("Task {} has no verified robot-action success; export refused."
                                   .format(task))
            suffixes = ["robot_action.mp4", "initial.png", "action_end.png"]
            if number == "8":
                suffixes.append("predicate_probe.png")
            for suffix in suffixes:
                recording = media / "{}_{}".format(task, suffix)
                if (not recording.is_file()
                        or recording.stat().st_mtime_ns > result_path.stat().st_mtime_ns):
                    raise RuntimeError("Task {} recording is incomplete or newer than its result JSON."
                                       .format(task))
            snapshots[result_path] = snapshot
    return snapshots


def find_ffmpeg(explicit):
    if explicit:
        executable = shutil.which(explicit)
        if executable is None and Path(explicit).is_file():
            executable = str(Path(explicit).resolve())
        if executable is None:
            raise FileNotFoundError("FFmpeg executable not found: {}".format(explicit))
        return executable
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
    except ImportError:
        raise RuntimeError("Pass --ffmpeg PATH, or install imageio-ffmpeg.")
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("FFmpeg failed:\n{}".format(result.stderr[-6000:]))


def temporary_output(destination):
    handle = tempfile.NamedTemporaryFile(prefix=destination.stem + "_",
                                         suffix=destination.suffix,
                                         dir=str(destination.parent), delete=False)
    handle.close()
    return Path(handle.name)


def encode_h264(ffmpeg, video):
    """Replace a recording only after the encoded copy has decoded successfully."""
    original_stat = video.stat()
    temporary = temporary_output(video)
    try:
        run_ffmpeg([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(video), "-an", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", "-pix_fmt", "yuv420p",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-movflags", "+faststart", str(temporary)])
        if temporary.stat().st_size == 0:
            raise RuntimeError("Encoded video is empty: {}".format(video))
        run_ffmpeg([ffmpeg, "-hide_banner", "-loglevel", "error", "-xerror",
                    "-i", str(temporary), "-f", "null", "-"])
        temporary.replace(video)
        # Preserve the simulation-recording time, used to pair it with its JSON.
        os.utime(str(video), ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    finally:
        if temporary.exists():
            temporary.unlink()


def make_gif(ffmpeg, video, destination):
    """Use recorded frames for a six-fps preview, with neither dimension over 384px."""
    temporary = temporary_output(destination)
    filters = ("fps=6,scale=w='min(384,iw)':h='min(384,ih)':"
               "force_original_aspect_ratio=decrease:flags=lanczos,split[a][b];"
               "[a]palettegen=stats_mode=diff[p];"
               "[b][p]paletteuse=dither=sierra2_4a")
    try:
        run_ffmpeg([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(video), "-filter_complex", filters,
                    "-loop", "0", str(temporary)])
        with temporary.open("rb") as handle:
            if handle.read(6) not in (b"GIF87a", b"GIF89a"):
                raise RuntimeError("Preview is not a GIF: {}".format(destination))
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def source_paths():
    filenames = (
        "test_custom_task_variants.py", "export_custom_task_media.py",
        "check_libero_setup.py", "configure_libero_windows.py",
        "requirements-windows-validation.txt",
        "test_panda_initial_pose.py", "test_libero_tabletop.py", "test_milk_source_scene.py",
        "test_extended_custom_tasks.py",
        "test_custom_predicate_conditions.py",
        "test_tabletop_configuration.py",
        "test_custom_bddl.py", "test_panda_drawer_action.py", "test_panda_drawer_info.py",
        "custom_tasks/custom_test.bddl",
        "custom_tasks/custom_goal_change.bddl", "custom_tasks/custom_milk_task.bddl",
        "custom_tasks/custom_new_object_task.bddl", "custom_tasks/custom_new_fixture_task.bddl",
        "custom_tasks/custom_new_predicate_task.bddl", "custom_tasks/custom_camera_control_task.bddl",
        "libero/libero/envs/objects/custom_validation_objects.py",
        "libero/libero/envs/objects/custom_validation_fixtures.py",
        "libero/libero/envs/problems/libero_custom_support.py",
        "libero/libero/envs/problems/libero_custom_camera_control.py",
        "libero/libero/envs/problems/libero_tabletop_manipulation.py",
        "libero/libero/envs/predicates/custom_validation_predicates.py",
        "libero/libero/assets/custom_validation_objects/marker_box.xml",
        "libero/libero/assets/custom_validation_objects/raised_support.xml",
    )
    return [ROOT / filename for filename in filenames]


def reference_paths():
    filenames = (
        "LICENSE",
        "libero/libero/envs/predicates/base_predicates.py",
        "libero/libero/envs/robots/mounted_panda.py",
        "libero/libero/envs/robots/__init__.py",
        "libero/libero/envs/arenas/table_arena.py",
        "libero/libero/envs/objects/hope_objects.py",
        "libero/libero/envs/bddl_base_domain.py",
        "libero/libero/envs/env_wrapper.py",
        "libero/libero/bddl_files/libero_object/pick_up_the_milk_and_place_it_in_the_basket.bddl",
        "libero/libero/bddl_files/libero_90/LIVING_ROOM_SCENE2_pick_up_the_milk_and_put_it_in_the_basket.bddl",
        "libero/libero/assets/stable_hope_objects/milk/milk.xml",
        "libero/libero/bddl_files/libero_goal/open_the_middle_drawer_of_the_cabinet.bddl",
        "libero/libero/bddl_files/libero_goal/push_the_plate_to_the_front_of_the_stove.bddl",
    )
    return [ROOT / filename for filename in filenames]


def export_sources(snapshots, reference_snapshots):
    for captured in (snapshots, reference_snapshots):
        if any(path.read_bytes() != content for path, content in captured.items()):
            raise RuntimeError("Source files changed during export; wait for edits to finish.")
    for source, contents in snapshots.items():
        destination = BUNDLE / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    for source, contents in reference_snapshots.items():
        destination = BUNDLE / "reference_code" / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
    readme = r"""# Custom Task 실행 파일

5장의 Panda 초기 장면과 6–9장의 검증에 사용한 코드와 BDDL이다. 실행 원본은 `../LIBERO/`에 있다. 각 Task에는 필요한 물체·Fixture만 남겼다.

## VSCode PowerShell에서 실행

새 터미널에서 아래 경로를 설정한다. 설치된 `libero` 환경이 없다면 [본문 3–4장](../NewTaskBDDL.md)의 설치 과정을 먼저 진행한다.

```powershell
$projectRoot = Join-Path $env:USERPROFILE 'Desktop\PML\urop\mirobot-vla'
$liberoRoot = Join-Path $projectRoot 'docs\W5\LIBERO'
$taskBundle = Join-Path $projectRoot 'docs\W5\custom_task_validation'
$liberoPython = Join-Path $env:USERPROFILE 'anaconda3\envs\libero\python.exe'
$liberoEnvironment = Split-Path -Parent $liberoPython
$env:PATH = "$liberoEnvironment;$liberoEnvironment\Library\bin;$liberoEnvironment\Scripts;$env:PATH"
if (-not (Test-Path -LiteralPath "$liberoRoot\setup.py")) {
    git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git $liberoRoot
    if ($LASTEXITCODE -ne 0) { throw 'LIBERO clone failed' }
    git -C $liberoRoot checkout 8f1084e3132a39270c3a13ebe37270a43ece2a01
    if ($LASTEXITCODE -ne 0) { throw 'LIBERO checkout failed' }
}
if (-not (Test-Path -LiteralPath "$liberoRoot\check_libero_setup.py")) {
    New-Item -ItemType Directory -Path "$liberoRoot\custom_tasks" -Force | Out-Null
    Copy-Item "$taskBundle\*.py" "$liberoRoot\" -Force
    Copy-Item "$taskBundle\requirements-windows-validation.txt" "$liberoRoot\" -Force
    Copy-Item "$taskBundle\custom_tasks\*.bddl" "$liberoRoot\custom_tasks\" -Force
    Copy-Item "$taskBundle\libero\libero\*" "$liberoRoot\libero\libero\" -Recurse -Force
}
Set-Location -LiteralPath $liberoRoot
$env:MUJOCO_GL = 'wgl'
$env:NUMBA_DISABLE_JIT = '1'
& $liberoPython .\check_libero_setup.py
if ($LASTEXITCODE -ne 0) { throw 'Resolve the setup error before running a task' }
```

각 실행은 위 준비가 끝난 같은 터미널에서 진행한다.

```powershell
& $liberoPython .\test_panda_initial_pose.py
& $liberoPython .\test_libero_tabletop.py
& $liberoPython .\test_custom_bddl.py --headless --steps 60 --size 512 --seed 0 --record --predicate-test
& $liberoPython .\test_panda_drawer_info.py
& $liberoPython .\test_panda_drawer_action.py --headless --size 512 --seed 0
& $liberoPython .\test_milk_source_scene.py
& $liberoPython .\test_custom_task_variants.py --task both --seed 0 --size 512
& $liberoPython .\test_extended_custom_tasks.py --case all --seed 0 --size 512
& $liberoPython .\test_custom_predicate_conditions.py
& $liberoPython .\test_tabletop_configuration.py
```

`test_milk_source_scene.py`는 우유 모델을 사용하는 공식 Tabletop 장면의 초기 상태를 렌더링한다. `test_tabletop_configuration.py`는 작업대 크기 변경과 초기화까지만 검사한다. C–F 실행 파일은 Object·Fixture·Predicate·Problem 모듈을 import해 등록한다.

## 사진과 영상 반영

현재 PC에서 확인한 FFmpeg를 지정해 결과를 반영한다.

```powershell
$liberoFFmpeg = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'
if (-not (Test-Path -LiteralPath $liberoFFmpeg)) { throw 'Set liberoFFmpeg to the installed ffmpeg.exe path' }
& $liberoPython .\export_custom_task_media.py --chapter both --ffmpeg $liberoFFmpeg
```

내보내기는 초기 상태와 실제 Panda 동작의 Goal·파지·해제·유지 검사를 통과한 결과에 적용한다. `--chapter 8`이나 `--chapter 9`로 해당 장의 결과만 선택할 수 있다. `reference_code`는 공식 코드와 MIT 라이선스의 참고 사본이며, 복원할 확장 코드와 별도로 보관한다.
"""
    (BUNDLE / "README.md").write_text(readme, encoding="utf-8")


def export_initial_and_drawer_media(ffmpeg):
    """Export chapters 5-7 and the unmodified source scene used to explain milk."""
    media = ROOT / "images"
    monitoring = json.loads((media / "custom_bddl_result.json").read_text(encoding="utf-8"))
    drawer = json.loads((media / "panda_drawer_action_result.json").read_text(encoding="utf-8"))
    for result in (monitoring, drawer):
        scene = result["scene"]
        if (scene["objects"] or scene["fixtures"] != ["wooden_cabinet_1"]
                or result["initial_goal"] or not all(result["initial_checks"].values())):
            raise RuntimeError("The minimal drawer scene has not been verified.")
    action = drawer["action"]
    if (not action["goal_after_robot_action"]
            or not action["goal_true_throughout_verification"]
            or action.get("verification_steps", 0) < 30
            or not action["grasp_confirmed"] or not action["gripper_released"]
            or action["direct_object_state_changes_during_action"]):
        raise RuntimeError("The drawer robot action did not pass verification.")
    for name in ("custom_bddl_monitoring", "custom_bddl_predicate_test", "panda_drawer_action"):
        video = media / (name + ".mp4")
        encode_h264(ffmpeg, video)
        make_gif(ffmpeg, video, media / (name + ".gif"))
    names = (
        "panda_initial_pose.png", "custom_bddl_test.png", "libero_live_agentview.png",
        "bddl_zero_action_test.png", "custom_bddl_goal_test.png", "custom_bddl_result.json",
        "custom_bddl_monitoring.mp4", "custom_bddl_monitoring.gif",
        "custom_bddl_predicate_test.mp4", "custom_bddl_predicate_test.gif",
        "panda_drawer_action_initial.png", "panda_drawer_action_result.png",
        "panda_drawer_action.mp4", "panda_drawer_action.gif",
        "panda_drawer_action_result.json", "panda_drawer_info.json",
        "milk_source_scene.png", "milk_source_scene.json",
    )
    shared = ROOT.parent / "images"
    shared.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(str(media / name), str(shared / name))
    shutil.copy2(str(ROOT / "libero_tabletop_test.png"), str(shared / "libero_tabletop_test.png"))
    print("Exported initial, drawer, and milk source recordings to {}".format(shared), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", help="Path to an FFmpeg executable")
    parser.add_argument("--chapter", choices=("8", "9", "both"), default="both",
                        help="Which chapter's verified recordings to export (default: both)")
    args = parser.parse_args()
    ffmpeg = find_ffmpeg(args.ffmpeg)
    snapshots = validate_results(args.chapter)
    sources = {path: path.read_bytes() for path in source_paths()}
    references = {path: path.read_bytes() for path in reference_paths()}
    videos = []
    for number in selected_chapters(args.chapter):
        config = CHAPTERS[number]
        media = ROOT / "images" / config["folder"]
        videos.extend(media / "{}_robot_action.mp4".format(task) for task in config["cases"])
    for video in videos:
        encode_h264(ffmpeg, video)
        make_gif(ffmpeg, video, video.with_suffix(".gif"))
    if any(path.read_bytes() != content for path, content in snapshots.items()):
        raise RuntimeError("Simulator results changed during export; wait for the run to finish.")
    if any(path.read_bytes() != content for path, content in sources.items()):
        raise RuntimeError("Source files changed during export; wait for edits to finish.")
    if any(path.read_bytes() != content for path, content in references.items()):
        raise RuntimeError("Reference files changed during export; wait for edits to finish.")
    for number in selected_chapters(args.chapter):
        config = CHAPTERS[number]
        media = ROOT / "images" / config["folder"]
        shared_media = ROOT.parent / "images" / config["folder"]
        shared_media.mkdir(parents=True, exist_ok=True)
        for source in sorted(media.iterdir()):
            if source.is_file() and source.suffix.lower() in (".png", ".json", ".mp4", ".gif"):
                shutil.copy2(str(source), str(shared_media / source.name))
        print("Exported recordings to {}".format(shared_media), flush=True)
    export_initial_and_drawer_media(ffmpeg)
    export_sources(sources, references)
    print("Exported source files to {}".format(BUNDLE), flush=True)


if __name__ == "__main__":
    main()
