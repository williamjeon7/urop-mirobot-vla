"""Rebuild W9 report figures and a timestamp-based, real-speed media preview.

Run from the repository root with cosmos-policy/.venv/bin/python -m
tools.w9_report_figures. Only docs/W9/images/data_collection_report is written.
All figures use recorded data; no model, simulator, or camera is started.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import h5py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
W9 = ROOT/'docs/W9'
OUT = W9/'images/data_collection_report'
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BLUE, TEAL, AMBER, INK = '#2864ba', '#16847b', '#c78215', '#1c2c40'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines() if s.strip()]


def save_figure(fig, name):
    fig.savefig(OUT/f'{name}.png', dpi=170, bbox_inches='tight', facecolor='white')
    fig.savefig(OUT/f'{name}.svg', bbox_inches='tight', facecolor='white')
    plt.close(fig)


def source_table():
    exports = read_json(W9/'data/hdf5/real_export_summary.json')
    table = []
    for number, exported in enumerate(exports, 1):
        report = read_json(W9/f'data/raw/영상{number}/alignment_report.json')
        table.append(dict(video=number, timesteps=exported['steps'],
                          control_duration_s=exported['steps']*.05,
                          camera_hz_median=report['camera_hz_median'],
                          max_frame_error_ms=report['max_frame_error_ms'],
                          repeated_timesteps=report['repeated_frames'],
                          max_robot_gap_ms=report['max_robot_gap_ms'],
                          max_follow_mm=exported['max_follow_mm'],
                          max_follow_deg=exported['max_follow_deg']))
    with (OUT/'episode_metrics.csv').open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    return table


def alignment_figure():
    episode = W9/'data/raw/영상1'
    frames = rows(episode/'frames.jsonl')
    states = [r for r in rows(episode/'robot.jsonl') if r['kind'] == 'state']
    with np.load(episode/'aligned.npz') as aligned:
        t0 = float(aligned['times'][0])
        grid = aligned['times'][:-1] - t0
        frame_indices = aligned['frame_indices']
    ft = np.array([r['t_s'] for r in frames]) - t0
    rt = np.array([r['t_s'] for r in states]) - t0
    lo, hi = .50, 1.05
    chosen = np.flatnonzero((grid >= lo-1e-6) & (grid <= hi+1e-6))
    fig, ax = plt.subplots(figsize=(13.8, 5.8))
    for y, name in [(3, '실제 PNG 수신'), (2, '20 Hz 관측 격자'), (1, '로봇 상태 수신'), (0, '다음 자세 목표')]:
        ax.axhline(y, color='#dce2e8', lw=1)
        ax.text(lo-.095, y, name, ha='right', va='center', fontsize=12, weight='bold')
    mask = (ft >= lo-.045) & (ft <= hi+.045)
    ax.scatter(ft[mask], np.full(mask.sum(), 3), s=70, color=BLUE, zorder=4, label='기록된 PNG')
    for index in np.flatnonzero(mask):
        ax.text(ft[index], 3.16, f'#{index}', fontsize=9, ha='center', color=BLUE)
    for k in chosen:
        index = int(frame_indices[k])
        duplicate = k > 0 and index == int(frame_indices[k-1])
        color = AMBER if duplicate else BLUE
        ax.plot([ft[index], grid[k]], [3, 2], color=color, alpha=.7, lw=1.4)
        ax.scatter(grid[k], 2, color=color, s=46, zorder=5)
        ax.plot([grid[k], grid[k]], [2, 1.08], color='#82919e', ls=':', lw=1)
        right = np.searchsorted(rt, grid[k])
        if 0 < right < len(rt):
            ax.plot([rt[right-1], grid[k], rt[right]], [1, .78, 1], color=TEAL, lw=.8, alpha=.55)
        if k+1 < len(grid):
            ax.annotate('', xy=(grid[k+1], 0), xytext=(grid[k], 0),
                        arrowprops=dict(arrowstyle='->', color=TEAL, lw=1.2))
    rmask = (rt >= lo-.10) & (rt <= hi+.10)
    ax.scatter(rt[rmask], np.full(rmask.sum(), 1), s=30, marker='s', color=TEAL, zorder=4)
    ax.scatter(grid[chosen]+.05, np.zeros(len(chosen)), marker='x', color=TEAL, s=42, zorder=4)
    ax.text(.755, 2.43, '가장 가까운 실제 PNG 선택 · 주황색은 직전과 같은 PNG', fontsize=10,
            ha='center', bbox=dict(facecolor='white', edgecolor='none', alpha=.9))
    ax.text(.755, .39, '위치: 선형 보간  /  자세: quaternion SLERP', fontsize=10, ha='center')
    ax.text(.755, -.42, 'action[k]의 자세 목표 = pose[k+1]  ·  간격 0.05초', fontsize=11, ha='center')
    ax.set_xlim(lo-.045, hi+.045)
    ax.set_ylim(-.68, 3.47)
    ax.set_yticks([])
    ax.set_xticks(np.arange(.5, 1.051, .05))
    ax.set_xlabel('영상1 정렬 시작 후 시간 (초)', labelpad=9)
    ax.set_title('그림 2. 서로 다른 수신 시각을 0.05초 타임스텝으로 연결', loc='left', fontsize=17, weight='bold', pad=16)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.text(.19, .015, '실제 기록 구간의 예시. 호스트 수신 시각 기준이며 노출·시리얼 지연은 미보정이다. 20 Hz 격자는 카메라 20 fps를 뜻하지 않는다.',
             fontsize=10, color=INK)
    fig.subplots_adjust(left=.19, bottom=.16)
    save_figure(fig, 'alignment_timeline')


def quality_figure(table):
    x = np.arange(1, 11)
    fig, axes = plt.subplots(3, 1, figsize=(13.8, 10), sharex=True)
    fields = [('timesteps', BLUE, '타임스텝 수', '.0f'),
              ('max_frame_error_ms', AMBER, '최대 PNG 시각 차이 (ms)', '.1f'),
              ('max_follow_mm', TEAL, '최대 추종 위치 오차 (mm)', '.2f')]
    for ax, (field, color, label, fmt) in zip(axes, fields):
        vals = [v[field] for v in table]
        ax.bar(x, vals, color=color, width=.64)
        ax.set_ylabel(label, fontsize=11)
        ax.spines[['top', 'right']].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis='y', alpha=.18)
        for index, value in enumerate(vals, 1):
            inside = field == 'max_frame_error_ms'
            ax.text(index, value-5 if inside else value+max(vals)*.025,
                    format(value, fmt), ha='center', fontsize=10, color='white' if inside else INK)
        ax.set_ylim(0, max(vals)*1.22)
    axes[0].set_title('그림 3. 영상별 학습 데이터 규모와 변환 품질', loc='left', fontsize=17, weight='bold', pad=15)
    axes[1].axhline(40, ls='--', color='#8b4a4a', lw=1.3, label='기본 40 ms')
    axes[1].axhline(70, ls='--', color='#383f48', lw=1.3, label='이번 배치 허용 70 ms')
    axes[1].legend(loc='lower right', ncol=2, fontsize=10)
    axes[2].axhline(5, ls='--', color='#8b4a4a', lw=1.3, label='잠정 기준 5 mm (10개 모두 미통과)')
    axes[2].legend(loc='lower right', fontsize=10)
    axes[-1].set_xticks(x, [f'영상{i}' for i in x])
    fig.text(.10, .012, '위치 오차는 시뮬레이터와 변환 자세의 차이에 실물 배율을 반영한 값이다. 블록 위치 오차나 실제 집기 성공률을 측정한 값은 아니다.', fontsize=10)
    fig.tight_layout(rect=(0, .045, 1, 1), h_pad=2.0)
    save_figure(fig, 'episode_quality')


def training_figure():
    report = read_json(W9/'data/hdf5/training_smoke.json')
    ranks = report['ranks']
    x = np.arange(len(ranks))
    fig, axes = plt.subplots(1, 2, figsize=(13.8, 5))
    loss = [r['loss_values'][0] for r in ranks]
    axes[0].bar(x, loss, color=BLUE, width=.55)
    for i, value in enumerate(loss):
        axes[0].text(i, value+.15, f'{value:.3f}', ha='center', fontsize=12)
    axes[0].set_ylim(0, max(loss)*1.22)
    axes[0].set_ylabel('1회 검증에서 관측한 loss')
    axes[0].set_title('각 rank의 유한 loss 확인', loc='left', fontsize=13, pad=12)
    allocated = [r['peak_allocated_cuda_bytes']/2**30 for r in ranks]
    reserved = [r['peak_reserved_cuda_bytes']/2**30 for r in ranks]
    axes[1].bar(x-.16, allocated, width=.30, color=TEAL, label='할당 peak')
    axes[1].bar(x+.16, reserved, width=.30, color='#9ba9b8', label='예약 peak')
    for i, (a, r) in enumerate(zip(allocated, reserved)):
        axes[1].text(i-.16, a+.12, f'{a:.2f}', ha='center', fontsize=10)
        axes[1].text(i+.16, r+.12, f'{r:.2f}', ha='center', fontsize=10)
    axes[1].set_ylim(0, 10)
    axes[1].set_ylabel('GPU 메모리 (GiB)')
    axes[1].set_title('native 학습 1회의 메모리', loc='left', fontsize=13, pad=12)
    axes[1].legend(loc='upper left', ncol=2, fontsize=10)
    for ax in axes:
        ax.set_xticks(x, [f'rank {i}' for i in x])
        ax.spines[['top', 'right']].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis='y', alpha=.18)
    fig.suptitle('그림 4. 공식 가중치로 실행한 4 GPU 학습 1회 검증', x=.04, y=1.03, ha='left', fontsize=17, weight='bold')
    fig.text(.05, .015, '모든 rank: 순전파·역전파·옵티마이저 갱신 1회. 이 막대는 학습 곡선이나 정책 성능 비교가 아니다.', fontsize=11)
    fig.tight_layout(rect=(0, .07, 1, 1))
    save_figure(fig, 'training_verification')


def wrist_figure():
    fig, axes = plt.subplots(3, 3, figsize=(11.5, 12))
    for row, number in enumerate((1, 5, 10)):
        path = W9/f'data/hdf5/mirobot_real/MIROBOT_video{number}_SCENE1_pick_up_the_blue_block_on_the_table_demo.hdf5'
        with h5py.File(path, 'r') as source:
            demo = source['data/demo_0']
            n = len(demo['actions'])
            indices = (0, n//2, n-1)
            t0 = demo['timestamps'][0]
            for col, (k, label) in enumerate(zip(indices, ('시작', '중간', '마지막'))):
                ax = axes[row, col]
                ax.imshow(demo['obs/eye_in_hand_rgb'][k])
                ax.set_title(f'영상{number} · {label}\nstep {k}, t={demo["timestamps"][k]-t0:.2f}초', fontsize=12, pad=9)
                ax.axis('off')
    fig.suptitle('그림 1. HDF5에 저장된 실제 D405 손목 영상', fontsize=17, weight='bold', y=.995)
    fig.text(.07, .014, '색 보정·중앙 crop·256×256 변환 결과. 시간은 각 영상의 정렬 시작 기준이며, 영상만으로 정량 집기 성능을 평가하지 않았다.', fontsize=10)
    fig.tight_layout(rect=(0, .04, 1, .97), h_pad=1.8)
    save_figure(fig, 'wrist_examples')


def timestamp_preview():
    """Preview original PNGs at their receipt-clock times, never model slots."""
    episode = W9/'data/raw/영상1'
    frames = rows(episode/'frames.jsonl')
    times = np.asarray([r['t_s'] for r in frames], dtype=float)
    relative = times-times[0]
    duration = float(relative[-1])
    fps = 20
    display_times = np.arange(int(np.ceil(duration*fps)))/fps
    right = np.searchsorted(relative, display_times).clip(0, len(relative)-1)
    left = (right-1).clip(0, len(relative)-1)
    indices = np.where(abs(relative[left]-display_times) <= abs(relative[right]-display_times), left, right)
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
               '-pix_fmt', 'rgb24', '-s', '480x360', '-r', str(fps), '-i', '-',
               '-an', '-c:v', 'libx264', '-crf', '22', '-preset', 'medium',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUT/'video1_review.mp4')]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    cache = {}
    gif_frames = []
    for k, (t, index) in enumerate(zip(display_times, indices)):
        index = int(index)
        if index not in cache:
            bgr = cv2.imread(str(episode/frames[index]['file']))
            if bgr is None:
                raise ValueError(f'Missing PNG: {frames[index]["file"]}')
            cache = {index: cv2.cvtColor(cv2.resize(bgr, (480, 360)), cv2.COLOR_BGR2RGB)}
        image = cache[index].copy()
        cv2.rectangle(image, (0, 0), (480, 42), (20, 25, 35), -1)
        text = f'Video 1 | 1x | t={t:05.2f}s | PNG #{index}'
        cv2.putText(image, text, (10, 27), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
        process.stdin.write(image.tobytes())
        if k % 4 == 0:
            gif_frames.append(Image.fromarray(cv2.resize(image, (320, 240))))
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError('ffmpeg failed to encode real-speed preview')
    # A common palette keeps GIF compression stable and prevents per-frame flashes.
    strip = Image.new('RGB', (320, 240*len(gif_frames)))
    for i, frame in enumerate(gif_frames):
        strip.paste(frame, (0, 240*i))
    palette = strip.resize((320, min(strip.height, 4000))).quantize(colors=128)
    quantized = [frame.quantize(palette=palette) for frame in gif_frames]
    durations = [200]*len(quantized)
    durations[-1] = int(round((len(display_times)/fps-(len(quantized)-1)/5)*1000/10))*10
    quantized[0].save(OUT/'video1_preview.gif', save_all=True, append_images=quantized[1:],
                      duration=durations, loop=0, optimize=True, disposal=2)
    return dict(source='raw/영상1/frames.jsonl and original PNGs',
                source_frames=len(frames), source_first_to_last_s=duration,
                preview_duration_s=len(display_times)/fps,
                mp4_display_fps=fps, gif_display_fps=5,
                note='1x receipt-clock playback, nearest original PNG at each display time; display fps is not capture fps. No synthesized frames. Original PNG colours, not calibrated HDF5 images.')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    font = FontProperties(fname=FONT).get_name()
    plt.rcParams.update({'font.family': font, 'font.size': 12, 'axes.unicode_minus': False,
                         'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': INK,
                         'ytick.color': INK, 'svg.fonttype': 'path'})
    table = source_table()
    alignment_figure()
    quality_figure(table)
    training_figure()
    wrist_figure()
    preview = timestamp_preview()
    assets = []
    for path in sorted(OUT.iterdir()):
        if path.name == 'manifest.json':
            continue
        assets.append(dict(file=path.name, bytes=path.stat().st_size,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest = dict(generator='tools/w9_report_figures.py', source_reports=[
        'docs/W9/data/hdf5/real_export_summary.json', 'docs/W9/data/hdf5/training_smoke.json',
        'docs/W9/data/raw/영상N/alignment_report.json'],
        total_timesteps=sum(r['timesteps'] for r in table), preview=preview, assets=assets)
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
