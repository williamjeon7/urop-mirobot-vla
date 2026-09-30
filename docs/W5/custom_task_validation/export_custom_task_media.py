"""Export verified section-8/9 recordings and source files to the parent Git repository."""

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
    "8": {"folder": "custom_task_validation", "cases": {"A": (40, 7), "B": (30, 8)}},
    "9": {"folder": "extended_task_validation", "cases": {
        "C": (30, 8), "D": (40, 9), "E": (30, 8), "F": (30, 8)}},
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
            valid = (result.get("task") == task and result.get("initial_goal") is False
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
        "test_panda_initial_pose.py", "test_extended_custom_tasks.py",
        "test_custom_predicate_conditions.py",
        "test_custom_bddl.py", "test_panda_drawer_action.py", "test_panda_drawer_info.py",
        "custom_tasks/custom_test.bddl",
        "custom_tasks/custom_goal_change.bddl", "custom_tasks/custom_milk_task.bddl",
        "custom_tasks/custom_new_object_task.bddl", "custom_tasks/custom_new_fixture_task.bddl",
        "custom_tasks/custom_new_predicate_task.bddl", "custom_tasks/custom_camera_control_task.bddl",
        "libero/libero/envs/objects/custom_validation_objects.py",
        "libero/libero/envs/objects/custom_validation_fixtures.py",
        "libero/libero/envs/problems/libero_custom_support.py",
        "libero/libero/envs/problems/libero_custom_camera_control.py",
        "libero/libero/envs/predicates/custom_validation_predicates.py",
        "libero/libero/assets/custom_validation_objects/marker_box.xml",
        "libero/libero/assets/custom_validation_objects/raised_support.xml",
    )
    return [ROOT / filename for filename in filenames]


def reference_paths():
    filenames = (
        "LICENSE",
        "libero/libero/envs/predicates/base_predicates.py",
        "libero/libero/envs/objects/hope_objects.py",
        "libero/libero/envs/bddl_base_domain.py",
        "libero/libero/envs/env_wrapper.py",
        "libero/libero/bddl_files/libero_object/pick_up_the_milk_and_place_it_in_the_basket.bddl",
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
    readme = """# Custom Task 실행 파일

5.2의 Panda 초기 자세와 6~9장의 검증을 재현하는 코드와 BDDL이다. 실행 원본은 `../LIBERO/`에 있다. [8장 결과](../images/custom_task_validation/)와 [9장 결과](../images/extended_task_validation/)의 GIF는 실제 MP4 프레임으로 만든 미리보기다.

`libero` conda 환경은 [본문의 설치 절차](../NewTaskBDDL.md)에 따라 준비한다. 새로 받은 상위 저장소에 LIBERO 코드가 없으면 아래 조건부 명령으로 받는다. 이미 설치된 LIBERO가 있으면 같은 경로에 검증 파일을 복원한다. 9장 실행 코드는 새 물체·Fixture·Predicate·환경 모듈을 가져와 등록한다.

검증에 사용한 공식 LIBERO 기준 버전은 `8f1084e3132a39270c3a13ebe37270a43ece2a01`이다. `reference_code`는 문서에서 인용한 공식 소스와 원본 MIT 라이선스를 보관하는 참고용이며, 아래 복원 명령의 복사 대상에서 제외된다.

```powershell
if (-not (Test-Path -LiteralPath .\\docs\\W5\\LIBERO\\setup.py)) {
    git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git .\\docs\\W5\\LIBERO
    git -C .\\docs\\W5\\LIBERO checkout 8f1084e3132a39270c3a13ebe37270a43ece2a01
}
$taskBundle = Resolve-Path .\\docs\\W5\\custom_task_validation
$liberoRoot = Resolve-Path .\\docs\\W5\\LIBERO
New-Item -ItemType Directory -Path "$liberoRoot\\custom_tasks" -Force
Copy-Item "$taskBundle\\*.py" "$liberoRoot\\" -Force
Copy-Item "$taskBundle\\custom_tasks\\*.bddl" "$liberoRoot\\custom_tasks\\" -Force
Copy-Item "$taskBundle\\libero\\libero\\*" "$liberoRoot\\libero\\libero\\" -Recurse -Force
conda activate libero
cd $liberoRoot
python test_panda_initial_pose.py
python test_custom_task_variants.py --task both --size 512
python test_extended_custom_tasks.py --case all --size 512
python test_custom_predicate_conditions.py
python export_custom_task_media.py --chapter both --ffmpeg 'FFmpeg 실행 파일 경로'
```

FFmpeg가 PATH에 있거나 `imageio-ffmpeg`가 설치돼 있으면 `--ffmpeg`를 생략한다. `--chapter 8` 또는 `--chapter 9`로 해당 장의 결과만 내보낼 수 있다. 내보내기는 초기 상태와 실제 Panda 동작 후의 Goal·파지·해제·유지 조건이 모두 통과한 결과에만 실행된다.
"""
    (BUNDLE / "README.md").write_text(readme, encoding="utf-8")


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
    export_sources(sources, references)
    print("Exported source files to {}".format(BUNDLE), flush=True)


if __name__ == "__main__":
    main()
