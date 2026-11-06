"""Control a Windows USB bridge from the OASYS Bash terminal over its SSH tunnel."""
import json
import os
import subprocess

from server.policy_client import PolicyClient


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
    from tools.run_mirobot_local import REPO, reserve_inference, stop_child
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
    if args.no_record_video:
        directory = reserve_inference(args.output_root)
    else:
        try:
            windows_recordings = client.recording_names()
        except RuntimeError as error:
            raise RuntimeError(
                "Windows 연결 프로그램이 녹화 이름 조회를 지원하지 않습니다. "
                "DEPLOY_MIROBOT.md의 코드 업데이트 절차를 따라 Windows 연결 프로그램을 갱신하세요."
            ) from error
        directory = reserve_inference(args.output_root, windows_recordings)
    name = directory.name
    print(f"실행 기록: {directory} | Windows 장치 사용, 영상은 종료 후 OASYS에 저장", flush=True)
    if args.execute:
        prepared = client.prepare()
        (directory / "initialization.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prepared["events"]), encoding="utf-8")
        policy.append("--execute")
    policy.extend(("--log-dir", str(directory / "policy")))
    if not args.no_record_video:
        policy.extend(("--record-video", "--recording-name", name))
    process = None
    interrupted = False
    try:
        process = subprocess.Popen(policy, cwd=REPO, env=env, start_new_session=True)
        code = process.wait()
    except KeyboardInterrupt:
        interrupted = True
        raise
    finally:
        stop_child(process)
        # Stopping is idempotent, including when the model lost its start/stop reply.
        if not args.no_record_video:
            try:
                client.stop_recording()
                paths = client.download_recording(name, directory)
                summary_path = directory / "policy/summary.json"
                if summary_path.exists():
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    if "video" in summary:
                        summary["video"]["source_path"] = summary["video"]["path"]
                        summary["video"]["path"] = paths["video"]
                    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"OASYS 영상 저장 완료: {paths['video']}", flush=True)
            except (OSError, RuntimeError, ValueError) as error:
                print(f"영상 가져오기 실패: {error}. Windows의 policy_recordings/{name} 원본을 확인하세요.", flush=True)
                if not interrupted and process is not None and process.returncode == 0:
                    raise RuntimeError("추론은 끝났지만 OASYS 영상 저장이 완료되지 않았습니다") from error
    return code
