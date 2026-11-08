"""Control a Windows USB bridge from the OASYS Bash terminal over its SSH tunnel."""
import json
from pathlib import Path
import os
import subprocess
import sys

from server.policy_client import PolicyClient
from server.experiment_log import capture_trial_layout, finish_launch, start_launch
from common.recording_names import COLORS, recording_number
from common.trial_numbers import compact_all, discard_if_never_started
from server.start_pose import prepare_without_homing, return_to_initial


def legacy_start_number(root):
    """First I{n} to try on an older bridge: one past any name this server already used."""
    used = []
    for launch in Path(root).glob("I*/launch.json"):
        try:
            name = json.loads(launch.read_text()).get("bridge_recording_name") or ""
        except ValueError:
            continue
        if (number := recording_number(name)) is not None:
            used.append(number)
    return max(used, default=0) + 1


def run(args, policy_args):
    from tools.run_mirobot_local import REPO
    if args.devices or args.check:
        return _run(args, policy_args)
    import fcntl
    log_root = REPO / "logs"
    log_root.mkdir(exist_ok=True)
    with (log_root / "mirobot_remote.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("다른 원격 로봇 실행이 진행 중입니다. 해당 실행이 끝난 뒤 시작하세요.") from error
        return _run(args, policy_args)


def _run(args, policy_args):
    from tools.run_mirobot_local import REPO, policy_color, reserve_inference, should_save, stop_child
    client = PolicyClient(f"http://127.0.0.1:{args.http_port}", timeout_s=40)
    try:
        health = client.health()
    except RuntimeError as error:
        raise RuntimeError(
            "Windows USB 연결 프로그램/역터널이 아직 연결되지 않았습니다. "
            "노트북에서 start_mirobot_windows.cmd 를 실행하세요. "
            "VS Code의 원격 Bash는 노트북 USB를 직접 볼 수 없습니다."
        ) from error
    if args.devices:
        print(json.dumps(dict(connection="Windows USB bridge → SSH → OASYS", **health),
                         ensure_ascii=False, indent=2))
        return 0
    policy = ["bash", str(REPO / "tools/run_mirobot_policy.sh"), *policy_args,
              "--bridge-url", client.base_url]
    env = os.environ.copy()
    for key in ("NO_PROXY", "no_proxy"):
        env[key] = ",".join(filter(None, (env.get(key), "127.0.0.1", "localhost")))
    if args.check:
        return subprocess.run([*policy, "--bridge-check"], cwd=REPO, env=env).returncode
    if args.execute and not health["execute_enabled"]:
        raise RuntimeError("Windows 브리지를 --execute 지원 모드로 다시 시작하세요.")
    save = should_save(args)
    record_video = save and not args.no_record_video
    directory = launch = None
    windows_recordings = []
    if not save:
        policy.append("--no-save")
    elif not record_video:
        directory = reserve_inference(args.output_root, color=policy_color(policy_args))
    else:
        try:
            windows_recordings = client.recording_names()
        except RuntimeError:
            # Older Windows bridge: no name listing and only I1, I2, ... names. The policy run
            # tries I{n}, I{n+1}, ... until the bridge accepts a name it has not used yet.
            windows_recordings = None
        directory = reserve_inference(args.output_root, color=policy_color(policy_args))
    name = directory.name if directory else None
    remote_name = name
    if record_video and windows_recordings is None:
        remote_name = f"I{legacy_start_number(args.output_root)}"
    elif record_video and health.get("recording_name_format") != "color-v1":
        used = [n for item in windows_recordings if (n := recording_number(item)) is not None]
        remote_name = f"I{max(used, default=0)+1}"
    elif record_video and name in windows_recordings:
        # Local numbers are reused after deletion; the Windows copy keeps a fresh name.
        color = policy_color(policy_args)
        used = [n for item in windows_recordings if (n := recording_number(item, color)) is not None]
        remote_name = f"I{max(used, default=0)+1}{color}"
    print(f"실행 기록: {directory or '저장 안 함'} | Windows 장치 사용", flush=True)
    process = None
    code = None
    interrupted = False
    prepared = False
    transfer = None
    try:
        if save:
            launch = start_launch(directory, policy_args, "execute" if args.execute else "preview")
            launch["bridge_recording_name"] = remote_name
            policy_args = capture_trial_layout(directory, policy_args, args.execute)
            policy = ["bash", str(REPO / "tools/run_mirobot_policy.sh"), *policy_args,
                      "--bridge-url", client.base_url, "--log-dir", str(directory / "policy")]
        if args.execute:
            # No homing: open the gripper and step to the start pose with ordinary bridge moves.
            events = prepare_without_homing(client, log=lambda text: print(text, flush=True))
            prepared = True
            if save:
                (directory / "initialization.jsonl").write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in events), encoding="utf-8")
            policy.append("--execute")
        if record_video:
            policy.extend(("--record-video", "--recording-name", remote_name))
        process = subprocess.Popen(policy, cwd=REPO, env=env, start_new_session=True)
        code = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        raise
    finally:
        stop_child(process)
        # Stopping is idempotent, including when the model lost its start/stop reply.
        if record_video:
            try:
                client.stop_recording()
                summary_path = directory / "policy/summary.json"
                if summary_path.exists():  # the policy may have moved to a free legacy name
                    remote_name = json.loads(summary_path.read_text()).get("recording_name") or remote_name
                    if launch is not None:
                        launch["bridge_recording_name"] = remote_name
                paths = client.download_recording(remote_name, directory, output_name=name)
                transfer = dict(status="saved", source_name=remote_name, **paths)
                summary_path = directory / "policy/summary.json"
                if summary_path.exists():
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    if "video" in summary:
                        summary["video"]["source_path"] = summary["video"]["path"]
                        summary["video"]["path"] = paths["video"]
                    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"OASYS 영상 저장 완료: {paths['video']}", flush=True)
            except (OSError, RuntimeError, ValueError) as error:
                transfer = dict(status="failed", error=str(error), source_name=remote_name)
                print(f"영상 가져오기 실패: {error}. Windows의 policy_recordings/{name} 원본을 확인하세요.", flush=True)
        if args.execute and prepared and not interrupted and not getattr(args, "no_return", False):
            # Whatever ended the run (pickup, wrong colour, limit, timeout), go back to the start pose.
            # Ctrl+C means a person stopped the arm, so it is not moved again.
            try:
                rows = return_to_initial(client, log=lambda text: print(text, flush=True))
                returned = "returned"
            except (OSError, RuntimeError, ValueError) as error:
                rows, returned = [dict(kind="return_failed", error=str(error))], f"not_returned: {error}"
                print(f"초기 위치 복귀 안 함: {error}", flush=True)
            if save:
                (directory / "return_to_initial.jsonl").write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            if launch is not None:
                launch["return_to_initial"] = returned
        if save and launch is not None:
            finish_launch(directory, launch, code=code,
                          error=sys.exc_info()[1], video_transfer=transfer)
            discard_if_never_started(directory, launch)
            compact_all(args.output_root, COLORS)  # reflect folders deleted during the run
        if (transfer and transfer["status"] == "failed" and not interrupted
                and process is not None and process.returncode == 0):
            raise RuntimeError("추론은 끝났지만 OASYS 영상 저장이 완료되지 않았습니다")
    return code
