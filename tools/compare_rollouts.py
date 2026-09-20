#!/usr/bin/env python3
"""두 롤아웃 영상을 waypoint 기준으로 맞춰 나란히 붙인다. (서버)

스텝 수가 서로 달라도 **같은 waypoint 구간이 같은 시간에 보이도록** 구간마다 길이를 맞춘다.
프레임은 기존 MP4 에서 읽고, 구간 경계는 각 실행의 jsonl 에서 읽는다.

    python -m tools.compare_rollouts \
      --left  rollouts/2026_09_17/compound/10_44_39--compound.mp4 --left-log  data/compound/2026_09_17-10_44_39.jsonl \
      --right rollouts/2026_09_20/follow/11_32_28--follow.mp4     --right-log data/follow/2026_09_20-11_32_28.jsonl \
      --left-title "9/17 Panda 원본" --right-title "9/20 Mirobot 보고값 추종"

영상은 2×2 격자라 카메라 하나만 잘라 쓴다 (`--camera`). 격자 순서는 agentview·frontview / sideview·birdview.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import imageio
import numpy as np
from PIL import Image, ImageDraw

CAMERA_TILE = {"agentview": (0, 0), "frontview": (0, 1), "sideview": (1, 0), "birdview": (1, 1)}
FPS = 20  # 시뮬 20Hz — 20fps 가 실시간이다


def waypoint_spans(log: Path, n_frames: int) -> list[tuple[str, int, int]]:
    """(waypoint 이름, 시작 프레임, 끝 프레임). jsonl 의 waypoint 표시로 구간을 나눈다.

    롤아웃 기록은 스텝마다 한 줄이고 `waypoint` 가 도착 지점에만 붙는다.
    추종 기록은 waypoint 루프 동안만 남기므로, 앞쪽 settle 프레임 수만큼 밀어서 맞춘다.
    """
    rows = [json.loads(line) for line in log.open()]
    rows = [r for r in rows if "meta" not in r]
    offset = n_frames - len(rows)  # 기록에 없는 앞부분(settle) 프레임 수
    spans, start = [], 0
    for i, row in enumerate(rows):
        name = row.get("waypoint")
        if not name:
            continue
        if spans and spans[-1][0] == name:  # 추종 기록은 같은 이름이 연속으로 나온다
            spans[-1] = (name, spans[-1][1], offset + i)
            continue
        spans.append((name, offset + start, offset + i))
        start = i + 1
    return [(name, a, b) for name, a, b in spans if b >= a]


def tile(frame: np.ndarray, camera: str) -> np.ndarray:
    row, col = CAMERA_TILE[camera]
    h, w = frame.shape[0] // 2, frame.shape[1] // 2
    return frame[row * h:(row + 1) * h, col * w:(col + 1) * w]


def pad_to(indices: list[int], length: int) -> list[int]:
    """모자라면 **마지막 프레임을 반복**해 length 개로.

    늘려 맞추면(프레임 복제) 구간 내내 움직임이 툭툭 끊겨 보인다. 먼저 끝난 쪽이 그 자리에서
    기다리게 하면 구간 안에서는 두 영상 모두 제 속도로 흐르고 구간 끝에서 다시 만난다.
    """
    return indices + [indices[-1]] * (length - len(indices)) if indices else []


def stack(a: np.ndarray, b: np.ndarray, args, note: str, note_l: str = "", note_r: str = "") -> np.ndarray:
    """두 장면을 나란히 붙이고 제목·설명 줄을 얹는다."""
    pair = np.hstack([a, np.zeros((a.shape[0], 6, 3), np.uint8), b])
    im = Image.new("RGB", (pair.shape[1], pair.shape[0] + 34), (0, 0, 0))
    im.paste(Image.fromarray(pair), (0, 34))
    d = ImageDraw.Draw(im)
    d.text((6, 4), args.left_title + note_l, fill=(255, 255, 0))
    d.text((pair.shape[1] // 2 + 12, 4), args.right_title + note_r, fill=(255, 255, 0))
    d.text((6, 20), f"{note}   {args.camera}", fill=(200, 200, 200))
    return np.array(im)


def write(frames, keyframes, args) -> None:
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{time.strftime('%H_%M_%S')}--compare-{args.camera}-{args.align}"
    imageio.mimwrite(f"{stem}.mp4", frames, fps=args.fps)
    Image.fromarray(np.vstack(keyframes)).save(f"{stem}--keyframes.png")
    print(f"\nsaved {stem}.mp4  ({len(frames)} frames, {len(frames) / args.fps:.1f}s @ {args.fps}fps)")
    print(f"saved {stem}--keyframes.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--left-log", type=Path, help="--align waypoint 일 때 필요")
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--right-log", type=Path, help="--align waypoint 일 때 필요")
    parser.add_argument("--left-title", default="left")
    parser.add_argument("--right-title", default="right")
    parser.add_argument("--camera", default="frontview", choices=sorted(CAMERA_TILE))
    parser.add_argument("--align", choices=("waypoint", "none"), default="waypoint",
                        help="waypoint: 구간마다 길이를 맞춰 같은 순간에 같은 자세가 보이게 한다. "
                             "none: 각자 제 속도로 재생하고 짧은 쪽은 마지막 장면으로 채운다")
    parser.add_argument("--hold", type=int, default=6, help="waypoint 끝에서 멈춰 보여줄 프레임 수")
    parser.add_argument("--fps", type=int, default=FPS, help="20 이 실시간 (시뮬 20Hz)")
    parser.add_argument("--out", type=Path, default=Path("rollouts") / time.strftime("%Y_%m_%d") / "compare")
    args = parser.parse_args()

    left = [tile(f, args.camera) for f in imageio.mimread(args.left, memtest=False)]
    right = [tile(f, args.camera) for f in imageio.mimread(args.right, memtest=False)]

    if args.align == "none":
        print(f"왼쪽 {len(left)}프레임 / 오른쪽 {len(right)}프레임 — 각자 제 속도로, 짧은 쪽은 마지막 장면으로 채운다")
        frames = []
        for k in range(max(len(left), len(right))):
            a, b = left[min(k, len(left) - 1)], right[min(k, len(right) - 1)]
            note_l = "" if k < len(left) else " (끝)"
            note_r = "" if k < len(right) else " (끝)"
            frames.append(stack(a, b, args, f"{k / args.fps:5.1f}s", note_l, note_r))
        write(frames, [frames[-1]], args)
        return

    l_spans = waypoint_spans(args.left_log, len(left))
    r_spans = waypoint_spans(args.right_log, len(right))
    names = [n for n, _, _ in l_spans]
    if names != [n for n, _, _ in r_spans]:
        raise SystemExit(f"waypoint 목록이 다르다:\n  {names}\n  {[n for n, _, _ in r_spans]}")
    print(f"왼쪽 {len(left)}프레임 / 오른쪽 {len(right)}프레임, waypoint {len(names)}개")

    frames, keyframes = [], []
    for (name, la, lb), (_, ra, rb) in zip(l_spans, r_spans):
        li, ri = list(range(la, lb + 1)), list(range(ra, rb + 1))
        length = max(len(li), len(ri)) + args.hold
        li, ri = pad_to(li, length), pad_to(ri, length)
        print(f"  {name:12} 왼쪽 {lb - la + 1:3d}프레임  오른쪽 {rb - ra + 1:3d}프레임"
              f"  → {length}프레임 (먼저 끝난 쪽은 그 자리에서 기다린다)")
        for a, b in zip(li, ri):
            frames.append(stack(left[a], right[b], args, name))
        keyframes.append(frames[-1])

    write(frames, keyframes, args)


if __name__ == "__main__":
    main()
