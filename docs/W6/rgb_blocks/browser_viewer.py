"""Stream the real LIBERO simulation to a localhost browser without saving files."""

import argparse
import errno
import http.client
import json
import math
import secrets
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

if __package__:
    from .tasks import TASK_NAMES, task_spec
else:
    from tasks import TASK_NAMES, task_spec

PORT = 8766
CAMERA_SIZE = 512
SEED = 0
FPS = 20.0
# pickup/reach: seconds of hold frames after the result, before the episode waits.
RESULT_HOLD_SECONDS = 2.0
# view (placement check, zero actions): episode length, as test_rgb_blocks --steps 60.
VIEW_STEPS = 60
MODES = ("view", "pickup", "reach")
SCENARIO_NAMES = ("none", "adjacent", "sandwich")   # scenarios.SCENARIOS, without importing numpy
MAX_SEED = 2 ** 31 - 1
CONTROL_BODY_LIMIT = 1024
VIEWER_ID = "libero-rgb-blocks-v1"
# Windows can take about two seconds to refuse a closed loopback connection.
EXIT_PROBE_TIMEOUT = 3.0 if sys.platform == "win32" else 0.5


class _Stopped(Exception):
    """The server is shutting down."""


class _Restart(Exception):
    """A browser asked for another seed."""

PAGE = """<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LIBERO · RGB blocks</title>
<style>
body { margin: 0; background: #111827; color: #e5e7eb; font: 16px system-ui, sans-serif; }
main { max-width: 780px; margin: 32px auto; padding: 0 16px; }
h1 { font-size: 24px; } a { color: #93c5fd; }
#screen { background: #030712; border-radius: 12px; overflow: hidden; }
img { display: block; width: 100%; height: auto; min-height: 300px; object-fit: contain; }
#status { min-height: 48px; line-height: 1.6; white-space: pre-line; }
#controls { display: grid; gap: 10px; margin-top: 12px; }
#controls[hidden] { display: none; }
.row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
button { background: #1f2937; color: #e5e7eb; border: 1px solid #374151; border-radius: 8px;
         padding: 6px 12px; font: inherit; cursor: pointer; }
button:hover { background: #374151; }
input[type=number], select { background: #030712; color: #e5e7eb; border: 1px solid #374151;
                              border-radius: 8px; padding: 6px 8px; font: inherit; }
input[type=number] { width: 6em; }
select:disabled { opacity: .5; }
#setup { border: 1px solid #374151; border-radius: 12px; padding: 10px 12px; margin-bottom: 12px; }
#timeline { flex: 1; min-width: 160px; }
#position { font-variant-numeric: tabular-nums; min-width: 7em; }
#hint { color: #9ca3af; font-size: 14px; }
</style>
<main>
<h1>LIBERO Tabletop · Red / Green / Blue</h1>
<div id="setup" class="row">
  <label>task <select id="task">
    <option value="scene">scene (세 블록)</option><option value="red">red</option>
    <option value="green">green</option><option value="blue">blue</option></select></label>
  <label>동작 <select id="mode">
    <option value="view">배치 확인</option><option value="pickup">pick up</option>
    <option value="reach">손 뻗기</option></select></label>
  <label>시나리오 <select id="scenario">
    <option value="none">none</option><option value="adjacent">adjacent</option>
    <option value="sandwich">sandwich</option></select></label>
  <label>seed <input id="seed" type="number" min="0" step="1" value="0"></label>
  <button id="load">불러오기</button>
</div>
<p id="instruction">RGB 블록 초기 배치</p>
<p id="status">시뮬레이터 준비 중…</p>
<div id="screen"><img id="video" src="/stream.mjpg" alt="LIBERO 실시간 화면"></div>
<div id="controls" hidden>
  <div class="row">
    <button data-action="first" title="처음">⏮</button>
    <button data-action="back" title="한 step 뒤로 (←)">◀ 1</button>
    <button id="play" title="재생 / 일시정지 (Space)">⏸ 일시정지</button>
    <button data-action="forward" title="한 step 앞으로 (→)">1 ▶</button>
    <button data-action="last" title="마지막">⏭</button>
    <input id="timeline" type="range" min="0" max="0" value="0" aria-label="타임라인">
    <span id="position">0 / 0</span>
  </div>
  <div class="row">
    <button id="next">다음 seed</button>
    <label><input id="auto" type="checkbox"> 끝나면 자동으로 다음 seed</label>
  </div>
  <div id="hint">Space 재생/일시정지 · ← → 한 step · 일시정지하면 시뮬레이션도 멈춘다 · 지나간 장면은 슬라이더로 다시 본다 · task를 바꾸면 환경을 새로 만든다(약 1초)</div>
</div>
</main>
<script>
const status = document.getElementById('status');
const instruction = document.getElementById('instruction');
const video = document.getElementById('video');
const controls = document.getElementById('controls');
const play = document.getElementById('play');
const timeline = document.getElementById('timeline');
const position = document.getElementById('position');
const seedInput = document.getElementById('seed');
const taskSelect = document.getElementById('task');
const modeSelect = document.getElementById('mode');
const scenarioSelect = document.getElementById('scenario');
const auto = document.getElementById('auto');
let info = null, dragging = false, formEdited = false, timer = null;
video.onerror = () => setTimeout(() => { video.src = '/stream.mjpg?t=' + Date.now(); }, 2000);

async function control(body) {
  if (!info || !info.control_token) return;
  try {
    await fetch('/control', {method: 'POST', cache: 'no-store',
      headers: {'Content-Type': 'application/json', 'X-RGB-Control-Token': info.control_token},
      body: JSON.stringify(body)});
  } catch (_) {}
  update();
}
document.querySelectorAll('[data-action]').forEach(button => button.onclick = () => {
  const action = button.dataset.action;
  if (action === 'back') control({action: 'step', delta: -1});
  else if (action === 'forward') control({action: 'step', delta: 1});
  else control({action: action});
});
play.onclick = () => control({action: 'toggle'});
function constrain() {
  // scene has no target block: only the placement check. Scenarios are for pick up.
  const scene = taskSelect.value === 'scene';
  for (const option of modeSelect.options) option.disabled = scene && option.value !== 'view';
  if (scene) modeSelect.value = 'view';
  scenarioSelect.disabled = modeSelect.value !== 'pickup';
  if (scenarioSelect.disabled) scenarioSelect.value = 'none';
}
[taskSelect, modeSelect, scenarioSelect].forEach(select => select.onchange = () => {
  formEdited = true; constrain();
});
seedInput.oninput = () => { formEdited = true; };
document.getElementById('load').onclick = () => {
  const seed = Number(seedInput.value);
  if (!Number.isInteger(seed) || seed < 0) return;
  formEdited = false;
  control({action: 'load', task: taskSelect.value, mode: modeSelect.value,
           scenario: scenarioSelect.value, seed: seed});
};
document.getElementById('next').onclick = () => { formEdited = false; control({action: 'next'}); };
auto.onchange = () => control({action: 'auto', on: auto.checked});
timeline.onpointerdown = () => { dragging = true; };
timeline.onpointerup = () => { dragging = false; };
timeline.oninput = () => control({action: 'seek', index: Number(timeline.value)});
document.addEventListener('keydown', event => {
  if (controls.hidden || ['INPUT', 'SELECT'].includes(event.target.tagName)) return;
  if (event.code === 'Space') { event.preventDefault(); control({action: 'toggle'}); }
  else if (event.key === 'ArrowLeft') control({action: 'step', delta: -1});
  else if (event.key === 'ArrowRight') control({action: 'step', delta: 1});
});

const MODE_NAMES = {view: '배치 확인', pickup: 'Pick up', reach: '손 뻗기'};
function episodeText(info) {
  const last = info.last_result;
  const atEnd = info.cursor >= info.frames - 1;
  const state = info.paused ? '일시정지' : !atEnd ? '다시보기' : info.episode_done ? '끝 · 다음 seed 대기' : 'LIVE';
  return state + ' · ' + info.task + ' · ' + MODE_NAMES[info.mode]
    + (info.scenario !== 'none' ? ' · ' + info.scenario : '')
    + ' · episode ' + info.episode + ' (seed ' + info.seed + ') · '
    + info.phase + ' · step ' + info.step + ' · goal ' + info.goal
    + (info.mode === 'view' ? (info.placement_ok ? ' · 배치 정상' : ' · 배치 확인 필요') : '')
    + ' · ' + info.fps.toFixed(1) + ' FPS'
    + (info.frame_age_seconds > 3 ? ' · 화면 갱신 지연' : '')
    + '\\n성공 ' + info.successes + ' / ' + info.completed
    + (last ? ' · 직전 seed ' + last.seed + ': ' + (last.success
        ? '성공 (' + last.summary + ')' : '실패 · ' + last.reason) : '');
}

async function update() {
  try {
    const response = await fetch('/status', {cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    info = await response.json();
    instruction.textContent = info.task === 'scene' ? 'RGB 블록 초기 배치'
      : MODE_NAMES[info.mode] + ' · ' + info.instruction
        + (info.mode === 'reach' ? ' (손끝이 Mirobot 기준 작업대 위 30 mm에서 멈춤)' : '');
    video.style.display = '';
    controls.hidden = false;
    play.textContent = info.paused ? '▶ 재생' : '⏸ 일시정지';
    timeline.max = Math.max(0, info.frames - 1);
    if (!dragging) timeline.value = Math.max(0, info.cursor);
    position.textContent = (info.frames ? info.cursor + 1 : 0) + ' / ' + info.frames;
    auto.checked = info.auto_advance;
    if (!formEdited && !['INPUT', 'SELECT'].includes(document.activeElement.tagName)) {
      taskSelect.value = info.task; modeSelect.value = info.mode;
      scenarioSelect.value = info.scenario; seedInput.value = info.seed;
      constrain();
    }
    if (info.error) status.textContent = '오류: ' + info.error;
    else if (info.loading) status.textContent = '불러오는 중… ' + info.task + ' (task를 바꾸면 약 1초)';
    else if (info.state === 'running') status.textContent = episodeText(info);
    else status.textContent = info.state === 'stopped' ? '종료' : '시뮬레이터 준비 중…';
  } catch (_) {
    status.textContent = '연결 끊김';
    video.style.display = 'none';
  }
  clearTimeout(timer);
  timer = setTimeout(update, 250);
}
update();
</script>
</html>
""".encode("utf-8")


def checked_config(config):
    """Validate a task/mode/scenario/seed combination. Raises ValueError."""
    task, mode = config.get("task"), config.get("mode")
    scenario, seed = config.get("scenario"), config.get("seed")
    if task not in TASK_NAMES:
        raise ValueError("task must be one of {}".format(", ".join(TASK_NAMES)))
    if mode not in MODES:
        raise ValueError("mode must be one of {}".format(", ".join(MODES)))
    if mode != "view" and not task_spec(task)["pickup_implemented"]:
        raise ValueError("{} needs task red, green or blue".format(mode))
    if scenario not in SCENARIO_NAMES:
        raise ValueError("scenario must be one of {}".format(", ".join(SCENARIO_NAMES)))
    if scenario != "none" and mode != "pickup":
        raise ValueError("scenario needs mode pickup")
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise ValueError("seed must be an integer in 0..{}".format(MAX_SEED))
    return {"task": task, "mode": mode, "scenario": scenario, "seed": seed}


class LiveSimulation:
    """Own MuJoCo and its GL context in one thread; share only JPEG bytes.

    One configuration — task (BDDL), mode, scenario, seed — runs one episode. Every frame
    of the current episode stays in memory for playback. The browser loads another
    configuration through `control`; only a task change rebuilds the environment.
    """

    def __init__(self, resolution=CAMERA_SIZE, seed=SEED, fps=FPS, task="scene", pickup=False,
                 scenario="none", mode=None):
        self.resolution = resolution
        self.fps = fps
        if mode is None:
            mode = "pickup" if pickup else "view"
        self.config = checked_config({"task": task, "mode": mode,
                                            "scenario": scenario, "seed": seed})
        self.stop_event = threading.Event()
        self.condition = threading.Condition()
        self.thread = None
        self.jpeg = None
        self.frame_time = None
        # Every displayed-frame change bumps the version; the MJPEG stream waits on it.
        self.version = 0
        # Playback: frames of the current episode, the displayed index and controls.
        self.frames = []
        self.cursor = -1
        self.paused = False
        self.auto_advance = False
        self.episode_done = False
        self.step_once = False
        self.request = None
        self.status = {"viewer_id": VIEWER_ID, "state": "starting", "step": 0, "goal": None,
                       "block_size_mm": None, "fps": 0.0, "error": None, "saved_files": False,
                       "placement_ok": None, "phase": None, "episode": 0, "completed": 0,
                       "successes": 0, "last_result": None, "cursor": -1, "frames": 0,
                       "paused": False, "auto_advance": False, "episode_done": False,
                       "loading": True}
        self._describe(self.config)

    def _describe(self, config):
        """Copy the configuration into the status (call with the condition held or before start)."""
        spec = task_spec(config["task"])
        self.status.update(task=config["task"], mode=config["mode"], scenario=config["scenario"],
                           seed=config["seed"], instruction=spec["language"],
                           target_object=spec["target_object"],
                           pickup_implemented=spec["pickup_implemented"],
                           goal_kind=spec["goal_kind"], pickup=config["mode"] == "pickup",
                           zero_actions_only=config["mode"] == "view")

    def start(self):
        self.thread = threading.Thread(target=self._run, name="rgb-simulation", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=10)

    def get_status(self):
        with self.condition:
            result = dict(self.status)
            result["frame_age_seconds"] = (
                None if self.frame_time is None else time.monotonic() - self.frame_time
            )
            return result

    def wait_for_frame(self, previous_version, timeout=1.0):
        with self.condition:
            self.condition.wait_for(
                lambda: self.stop_event.is_set() or self.status["error"] is not None
                or (self.jpeg is not None and self.version != previous_version),
                timeout=timeout,
            )
            if self.jpeg is None or self.version == previous_version:
                return None
            return self.jpeg, self.version

    # ── playback (call with self.condition held) ────────────────────
    def _show_frame(self, index):
        frame = self.frames[index]
        self.cursor = index
        self.jpeg = frame["jpeg"]
        self.version += 1
        self.frame_time = time.monotonic()
        self.status.update(state="running", step=frame["step"], phase=frame["phase"],
                           goal=frame["goal"], cursor=index, frames=len(self.frames))
        self.condition.notify_all()

    def _append_frame(self, jpeg, step, phase, goal):
        """Store a new simulation frame; show it only if the display was at the newest one."""
        follow = self.cursor == len(self.frames) - 1
        self.frames.append({"jpeg": jpeg, "step": step, "phase": phase, "goal": goal})
        self.status["frames"] = len(self.frames)
        if follow:
            self._show_frame(len(self.frames) - 1)
        else:
            self.condition.notify_all()

    def control(self, command):
        """Apply one browser control. Raises ValueError for a bad command."""
        action = command.get("action")
        with self.condition:
            last = len(self.frames) - 1
            if action == "pause":
                self.paused = True
            elif action == "play":
                self.paused = False
            elif action == "toggle":
                self.paused = not self.paused
            elif action == "step":
                delta = command.get("delta")
                if type(delta) is not int or delta not in (-1, 1):
                    raise ValueError("step needs delta -1 or 1")
                self.paused = True
                target = self.cursor + delta
                if 0 <= target <= last:
                    self._show_frame(target)
                elif delta > 0 and last >= 0 and not self.episode_done:
                    # At the newest frame: let the paused simulation compute one more step.
                    self.step_once = True
            elif action in ("seek", "first", "last"):
                index = {"first": 0, "last": last}.get(action, command.get("index"))
                if type(index) is not int:
                    raise ValueError("seek needs an integer index")
                if last >= 0:
                    self._show_frame(min(max(index, 0), last))
            elif action in ("run_seed", "next"):
                seed = command.get("seed") if action == "run_seed" else self.config["seed"] + 1
                self.request = checked_config(dict(self.config, seed=seed))
            elif action == "load":
                self.request = checked_config(
                    {key: command.get(key) for key in ("task", "mode", "scenario", "seed")})
            elif action == "auto":
                on = command.get("on")
                if type(on) is not bool:
                    raise ValueError("auto needs on true/false")
                self.auto_advance = on
            else:
                raise ValueError("unknown action")
            self.status.update(paused=self.paused, auto_advance=self.auto_advance)
            self.condition.notify_all()
            return {"ok": True, "cursor": self.cursor, "frames": len(self.frames),
                    "paused": self.paused}

    def _wait_turn(self, clock, compute=True):
        """Pace the display; return when the simulation may compute its next frame.

        While playing behind the newest frame, buffered frames are replayed first.
        Paused (or, with compute=False, an ended episode) only waits for controls.
        Raises _Stopped or _Restart.
        """
        interval = 1.0 / self.fps
        with self.condition:
            while True:
                if self.stop_event.is_set():
                    raise _Stopped
                if self.request is not None:
                    raise _Restart
                now = time.monotonic()
                last = len(self.frames) - 1
                if compute and self.step_once:
                    self.step_once = False
                    clock["last"] = now
                    return
                if self.paused or (not compute and self.cursor >= last):
                    if not compute and not self.paused and self.auto_advance:
                        self.request = dict(self.config, seed=min(self.config["seed"] + 1, MAX_SEED))
                        continue
                    # Alive but idle: keep frame_age small so the page does not report a stall.
                    self.frame_time = now
                    self.status["fps"] = 0.0
                    self.condition.wait(0.25)
                    continue
                remaining = clock["last"] + interval - now
                if remaining > 0:
                    self.condition.wait(remaining)
                    continue
                self.status["fps"] = 1.0 / max(now - clock["last"], 0.000001)
                clock["last"] = now
                if self.cursor < last:
                    self._show_frame(self.cursor + 1)
                    continue
                return

    def _run_episode(self, env, config, episode, tools):
        """Run one configuration, keep its frames, then wait. Leaves only by raising."""
        cv2, np, frame_from, scene_state, block_size_mm = (
            tools["cv2"], tools["np"], tools["frame_from"], tools["scene_state"],
            tools["block_size_mm"])
        task, mode, scenario, seed = (config["task"], config["mode"], config["scenario"],
                                      config["seed"])
        target = task_spec(task)["target_object"]
        clock = {"last": time.monotonic()}
        label = "{} {}{}".format(task, mode, "" if scenario == "none" else " " + scenario)

        def show(obs, step, goal, phase):
            self._wait_turn(clock)
            caption = "{} | seed {} | {} | step {} | goal={}".format(label, seed, phase, step, goal)
            ok, encoded = cv2.imencode(".jpg", frame_from(obs, step, goal, caption=caption),
                                       [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                raise RuntimeError("OpenCV could not encode the simulation frame.")
            with self.condition:
                self._append_frame(encoded.tobytes(), step, phase, goal)

        with self.condition:
            self.frames, self.cursor = [], -1
            self.paused = self.episode_done = self.step_once = False
            self.request = None
            self._describe(config)
            self.status.update(episode=episode, phase="reset", step=0, goal=None, cursor=-1,
                               frames=0, paused=False, episode_done=False, loading=False,
                               block_size_mm=block_size_mm)
        env.seed(seed)
        obs = env.reset()
        scene_info = scene_state(env)
        scenario_error = None
        if mode == "pickup":
            # Scenario layouts move neighbours once after the BDDL placement check.
            try:
                tools["apply_scenario"](env, scenario, target)
            except RuntimeError as error:   # e.g. no free side: report it as this episode's result
                scenario_error = str(error)
        with self.condition:
            self.status.update(scene_info)
        show(env.env._get_observations(force_update=True), 0, bool(env.check_success()), "reset")
        held = None
        try:
            if scenario_error:
                raise RuntimeError(scenario_error)
            if mode == "view":
                zero = np.zeros(7, dtype=np.float32)
                for step in range(1, VIEW_STEPS + 1):
                    obs, _, _, _ = env.step(zero)
                    placement = scene_state(env, require_contact=step >= 20)
                    with self.condition:
                        self.status.update(placement_ok=placement["placement_ok"])
                    show(obs, step, bool(env.check_success()), "view")
                outcome = {"success": True, "steps": VIEW_STEPS,
                           "summary": "{} step 동안 배치 유지".format(VIEW_STEPS)}
            elif mode == "pickup":
                obs, result = tools["run_pickup"](
                    env, obs, target, on_step=lambda o, s, p, g: show(o, s, g, p),
                    check_regions=scenario == "none")
                held = result["still_grasped"]
                outcome = {"success": tools["pickup_success"](result), "steps": result["steps"],
                           "summary": "{} step, {} m 상승".format(result["steps"],
                                                                result["lift_height_m"])}
            else:
                obs, result = tools["run_reach"](
                    env, obs, target, on_step=lambda o, s, p, g: show(o, s, g, p))
                held = False
                outcome = {"success": tools["reach_success"](result), "steps": result["steps"],
                           "summary": "{} step, 수평 오차 {:.1f} mm, 손끝 Mirobot {} mm".format(
                               result["steps"], result["hover_xy_error_m"] * 1000,
                               result["hover_tip_on_mirobot_mm"])}
            outcome["reason"] = None if outcome["success"] else "판정 조건 불충족"
        except RuntimeError as error:
            outcome = {"success": False, "steps": None, "summary": None, "reason": str(error)}
        outcome["seed"] = seed
        print("{} seed {}: {}".format(label, seed, json.dumps(outcome, ensure_ascii=False)), flush=True)
        with self.condition:
            self.status["completed"] += 1
            self.status["successes"] += int(outcome["success"])
            self.status["last_result"] = outcome
        if held is not None:
            # A short hold shows whether the result is stable: zero OSC delta, gripper as it ended.
            hold = np.zeros(7, dtype=np.float32)
            hold[6] = 1.0 if held else -1.0
            phase = "result " + ("success" if outcome["success"] else "fail")
            for step in range(1, int(RESULT_HOLD_SECONDS * self.fps) + 1):
                obs, _, _, _ = env.step(hold)
                show(obs, step, bool(env.check_success()), phase)
        with self.condition:
            self.episode_done = True
            self.status["episode_done"] = True
        self._wait_turn(clock, compute=False)   # returns only by raising

    def _run(self):
        env = None
        try:
            import cv2
            import numpy as np
            if __package__:
                from .test_rgb_blocks import BLOCK_SIZE_MM, frame_from, make_env, scene_state
                from .pickup import pickup_success, reach_success, run_pickup, run_reach
                from .scenarios import apply_scenario
            else:
                from test_rgb_blocks import BLOCK_SIZE_MM, frame_from, make_env, scene_state
                from pickup import pickup_success, reach_success, run_pickup, run_reach
                from scenarios import apply_scenario
            tools = {"cv2": cv2, "np": np, "frame_from": frame_from, "scene_state": scene_state,
                     "block_size_mm": BLOCK_SIZE_MM, "run_pickup": run_pickup,
                     "run_reach": run_reach, "pickup_success": pickup_success,
                     "reach_success": reach_success, "apply_scenario": apply_scenario}
            config, env_task, episode = dict(self.config), None, 0
            while True:
                if env_task != config["task"]:
                    # A new BDDL needs a new environment; build it in this (the GL) thread.
                    with self.condition:
                        self._describe(config)
                        self.status.update(state="starting", loading=True)
                        self.condition.notify_all()
                    if env is not None:
                        env.close()
                        env = None
                    env = make_env(seed=config["seed"], size=self.resolution, task=config["task"])
                    env_task = config["task"]
                    print("RGB simulation ready: task {}".format(env_task), flush=True)
                episode += 1
                try:
                    self._run_episode(env, config, episode, tools)
                except _Restart:
                    with self.condition:
                        new = self.request
                        if {k: v for k, v in new.items() if k != "seed"} != \
                                {k: v for k, v in config.items() if k != "seed"}:
                            # Counters describe one task/mode/scenario; start them again.
                            self.status.update(completed=0, successes=0, last_result=None)
                        config = self.config = dict(new)
                except _Stopped:
                    return
        except Exception as error:
            with self.condition:
                self.status.update(state="error", error="{}: {}".format(type(error).__name__, error))
                self.condition.notify_all()
            traceback.print_exc()
        finally:
            try:
                if env is not None:
                    env.close()
            finally:
                with self.condition:
                    if self.status["error"] is None:
                        self.status["state"] = "stopped"
                    self.condition.notify_all()


def make_server(simulation, port=PORT):
    """Serve frames and allow a terminal client to stop this specific instance.

    `/control` takes browser playback commands. It needs the per-instance control token
    from `/status`, a localhost Host, and a same-origin (or absent) Origin. The custom
    token header makes cross-site requests need a CORS preflight, which is never granted.
    """
    shutdown_token = secrets.token_urlsafe(32)
    control_token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, content_type, body):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/":
                    self.reply(200, "text/html; charset=utf-8", PAGE)
                elif path == "/status":
                    status = simulation.get_status()
                    status["shutdown_token"] = shutdown_token
                    status["control_token"] = control_token
                    self.reply(200, "application/json; charset=utf-8",
                               json.dumps(status).encode("utf-8"))
                elif path == "/stream.mjpg":
                    self.stream()
                else:
                    self.reply(404, "text/plain; charset=utf-8", b"Not found")
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def reply_json(self, code, payload):
            self.reply(code, "application/json; charset=utf-8",
                       json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def control(self):
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            token = self.headers.get("X-RGB-Control-Token", "")
            try:
                hostname = urlsplit("//" + host).hostname
            except ValueError:
                hostname = None
            if (hostname not in ("localhost", "127.0.0.1")
                    or (origin is not None and origin != "http://" + host)
                    or not token.isascii() or not secrets.compare_digest(token, control_token)):
                self.reply(403, "text/plain; charset=utf-8", b"Forbidden")
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self.reply_json(411, {"error": "Content-Length required"})
                return
            if not 0 <= length <= CONTROL_BODY_LIMIT:
                self.reply_json(413, {"error": "body too large"})
                return
            try:
                command = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, ValueError):
                self.reply_json(400, {"error": "invalid JSON"})
                return
            handler = getattr(simulation, "control", None)
            if not isinstance(command, dict) or handler is None:
                self.reply_json(400 if handler else 409,
                                {"error": "invalid command" if handler else "no controls"})
                return
            try:
                result = handler(command)
            except ValueError as error:
                self.reply_json(400, {"error": str(error)})
                return
            self.reply_json(200, result)

        def do_POST(self):
            if urlsplit(self.path).path == "/control":
                try:
                    self.control()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass
                return
            if urlsplit(self.path).path != "/shutdown":
                self.reply(404, "text/plain; charset=utf-8", b"Not found")
                return
            token = self.headers.get("X-RGB-Viewer-Token", "")
            if (self.headers.get("Origin") is not None or not token.isascii()
                    or not secrets.compare_digest(token, shutdown_token)):
                self.reply(403, "text/plain; charset=utf-8", b"Forbidden")
                return
            try:
                self.reply(202, "application/json", b'{"stopping":true}')
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            simulation.stop_event.set()
            with simulation.condition:
                simulation.condition.notify_all()
            self.server.shutdown()

        def stream(self):
            self.connection.settimeout(5)
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            previous = -1   # opaque token: the frame version (LiveSimulation) or step
            while not simulation.stop_event.is_set():
                frame = simulation.wait_for_frame(previous)
                if frame is None:
                    if simulation.get_status()["error"] is not None:
                        break
                    continue
                jpeg, previous = frame
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                 + str(len(jpeg)).encode("ascii") + b"\r\n\r\n" + jpeg + b"\r\n")
                self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.block_on_close = False
    return server


def probe_existing_viewer(port, timeout=2.0):
    """Recognize our viewer only; never stop or reuse an unrelated service."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", "/status")
        response = connection.getresponse()
        if response.status != 200:
            return None
        body = response.read(65537)
        if len(body) > 65536:
            return None
        status = json.loads(body.decode("utf-8"))
        required = {"state", "step", "goal", "block_size_mm", "fps", "error",
                    "zero_actions_only", "saved_files", "frame_age_seconds"}
        if not isinstance(status, dict) or not required.issubset(status):
            return None
        if (status["state"] not in ("starting", "running", "error", "stopped")
                or type(status["step"]) is not int or status["step"] < 0
                or type(status["zero_actions_only"]) is not bool
                or status["saved_files"] is not False):
            return None
        if status.get("viewer_id") == VIEWER_ID:
            return status
        if status.get("viewer_id") is not None:
            return None
        # A viewer started before this fix has no ID; require the exact page too.
        connection.request("GET", "/")
        response = connection.getresponse()
        if response.status == 200 and response.read(len(PAGE) + 1) == PAGE:
            return status
    except (OSError, http.client.HTTPException, UnicodeError, ValueError, RecursionError):
        return None
    finally:
        connection.close()
    return None


def print_viewer_address(port):
    print("http://localhost:{}".format(port), flush=True)


def request_shutdown(port, token, timeout=2.0):
    if not isinstance(token, str) or not token:
        return False
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("POST", "/shutdown", body=b"",
                           headers={"X-RGB-Viewer-Token": token})
        response = connection.getresponse()
        response.read(1024)
        return response.status == 202
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        return False
    finally:
        connection.close()


def wait_for_server_exit(port, timeout=15.0):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port),
                                          timeout=min(EXIT_PROBE_TIMEOUT, remaining)):
                pass
        except ConnectionRefusedError:
            return True
        except OSError:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.1, remaining))


def stop_existing_viewer(port, status=None):
    if status is None:
        status = probe_existing_viewer(port)
    if status is None:
        if wait_for_server_exit(port, timeout=EXIT_PROBE_TIMEOUT):
            print("서버가 종료되어 있습니다.", flush=True)
            return 0
        print("RGB 서버로 확인되지 않아 종료하지 않았습니다.", file=sys.stderr)
        return 1
    if not request_shutdown(port, status.get("shutdown_token")):
        print("서버 종료 요청에 실패했습니다.", file=sys.stderr)
        return 1
    if not wait_for_server_exit(port):
        print("서버 종료를 확인하지 못했습니다.", file=sys.stderr)
        return 1
    print("서버 종료", flush=True)
    return 0


def follow_existing_viewer(port, token):
    try:
        while True:
            time.sleep(0.5)
            current = probe_existing_viewer(port)
            if current is None:
                if wait_for_server_exit(port, timeout=EXIT_PROBE_TIMEOUT):
                    return 0
                continue
            if current.get("shutdown_token") != token:
                return 0
    except KeyboardInterrupt:
        return stop_existing_viewer(port, status={"shutdown_token": token})


def describe_config(task, mode, scenario):
    return "task {} · 동작 {}{}".format(task, mode, "" if scenario == "none" else " · 시나리오 " + scenario)


def reuse_existing_viewer(status, port, requested_task="scene", requested_pickup=False,
                          requested_scenario="none", requested_mode=None):
    """Report existing settings honestly; failed or stale workers are not LIVE.

    A healthy server is reused even with other settings: the browser switches them.
    """
    if status["error"] is not None or status["state"] not in ("starting", "running"):
        print("기존 RGB 서버가 있지만 정상 실행 상태가 아닙니다: {}. "
              "서버를 시작한 터미널에서 종료한 뒤 다시 실행하세요.".format(
                  status["error"] or status["state"]), file=sys.stderr)
        return 1
    age = status["frame_age_seconds"]
    if status["state"] == "running" and (
            type(age) not in (int, float) or not 0 <= age <= 5 or not math.isfinite(age)):
        print("기존 RGB 서버의 화면 갱신이 멈췄습니다. "
              "서버를 시작한 터미널에서 종료한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    token = status.get("shutdown_token")
    if not isinstance(token, str) or not token:
        print("이전 버전 서버입니다. 기존 실행 터미널에서 종료한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    print_viewer_address(port)
    print("기존 서버 연결 · Ctrl+C로 종료", flush=True)
    current_mode = status.get("mode") or ("pickup" if status.get("pickup") else "view")
    current = describe_config(status.get("task", "scene"), current_mode, status.get("scenario", "none"))
    requested = describe_config(requested_task,
                                requested_mode or ("pickup" if requested_pickup else "view"),
                                requested_scenario)
    if current != requested:
        print("지금 서버는 {}입니다. 요청한 {}(으)로는 브라우저 위쪽 설정에서 바꾼다.".format(
            current, requested), flush=True)
    return follow_existing_viewer(port, token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--size", type=int, default=CAMERA_SIZE, help="Camera resolution, not cube size.")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--task", choices=TASK_NAMES, default="scene",
                        help="Task (BDDL) shown first; the browser can switch it.")
    parser.add_argument("--mode", choices=MODES,
                        help="First mode: view (placement check), pickup or reach. Default view.")
    parser.add_argument("--pickup", action="store_true", help="Same as --mode pickup.")
    parser.add_argument("--scenario", choices=SCENARIO_NAMES, default="none",
                        help="With pickup: start with neighbours next to the target (scenarios.py).")
    parser.add_argument("--fps", type=float, default=FPS)
    parser.add_argument("--stop", action="store_true", help="Stop the RGB server on this port.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 128 <= args.size <= 2048:
        parser.error("port must be 1..65535 and size must be 128..2048")
    if not math.isfinite(args.fps) or not 0 < args.fps <= 60:
        parser.error("fps must be finite and in (0, 60]")
    if args.pickup and args.mode not in (None, "pickup"):
        parser.error("--pickup conflicts with --mode {}".format(args.mode))
    mode = "pickup" if args.pickup else (args.mode or "view")
    try:
        checked_config({"task": args.task, "mode": mode, "scenario": args.scenario, "seed": args.seed})
    except ValueError as error:
        parser.error(str(error))
    if args.stop:
        return stop_existing_viewer(args.port)
    simulation = LiveSimulation(resolution=args.size, seed=args.seed, fps=args.fps,
                                task=args.task, scenario=args.scenario, mode=mode)
    try:
        server = make_server(simulation, port=args.port)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            existing = probe_existing_viewer(args.port)
            if existing is not None:
                return reuse_existing_viewer(existing, args.port, requested_task=args.task,
                                             requested_scenario=args.scenario,
                                             requested_mode=mode)
        print("Cannot start localhost viewer: {}. Try --port with an unused port.".format(error),
              file=sys.stderr)
        return 1
    print_viewer_address(args.port)
    print("Ctrl+C로 종료", flush=True)
    try:
        simulation.start()
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        simulation.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
