"""Reproduce local checks/alignment; run from repository root. Never moves the robot."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from docs.W9.d405.capture_storage import read_image, write_image
from docs.W9.d405.prepare import input_hashes, prepare, read_jsonl
from docs.W9.d405.color_calibration import apply_rgb, load_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-frame-ms', type=float, default=40)
    parser.add_argument('--real-success-reviewed', action='store_true')
    args = parser.parse_args()
    if args.max_frame_ms <= 0:
        parser.error('Positive frame tolerance required.')
    cv2.setNumThreads(2)
    root = Path('docs/W9/data/raw')
    out = Path('docs/W9/data/postprocess')
    out.mkdir(parents=True, exist_ok=True)
    reports = []
    for number in range(1, 11):
        episode = root / ('\uC601\uC0C1' + str(number))
        report = {'episode': episode.name, 'status': 'failed'}
        try:
            meta_path = episode / 'metadata.json'
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            frames = read_jsonl(episode / 'frames.jsonl')
            profile = load_profile(episode / 'color_profile.json')
            samples = set(np.linspace(0, len(frames)-1, 6).astype(int).tolist())
            views = []
            for index, frame in enumerate(frames):
                image = read_image(episode / frame['file'])
                if image is None or image.shape != (meta['height'], meta['width'], 3):
                    raise ValueError(f'Invalid source PNG: {frame["file"]}')
                if index in samples:
                    rgb = apply_rgb(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), profile)
                    view = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (320, 240))
                    view = cv2.copyMakeBorder(view, 0, 24, 0, 0, cv2.BORDER_CONSTANT)
                    cv2.putText(view, f'#{index} t={frame["t_s"]:.3f}s', (5, 257),
                                cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
                    views.append(view)
            write_image(out / f'video{number}_review.jpg', np.concatenate(views, axis=1))
            video = episode / (episode.name + '.mp4')
            cap = cv2.VideoCapture(str(video))
            decoded = 0
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                decoded += 1
            cap.release()
            if decoded != len(frames):
                raise ValueError(f'MP4 has {decoded} decoded frames; PNG log has {len(frames)}.')
            if args.real_success_reviewed:
                meta['real_success'] = True
                meta['real_success_review'] = {
                    'source': 'user explicitly confirmed successful gripper pickup for all ten recordings',
                    'date': '2026-10-29',
                    'layout_reference_match': 'not independently confirmed',
                }
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
            aligned, alignment = prepare(episode, max_frame_ms=args.max_frame_ms)
            ft = np.array([frame['t_s'] for frame in frames])
            dt = np.diff(ft)
            default_exceeded = int(np.count_nonzero(abs(aligned['frame_error_s']) > .04))
            alignment.update(
                accepted_max_frame_ms=args.max_frame_ms,
                accepted_max_state_gap_ms=150,
                default_max_frame_ms=40,
                default_frame_limit_passed=default_exceeded == 0,
                steps_exceeding_default_frame_limit=default_exceeded,
                camera_hz_median=float(1/np.median(dt)),
                max_camera_gap_ms=float(dt.max()*1000),
                camera_note='Nearest existing PNG; repeated frames are retained, no synthesized frames. '
                            '20 Hz is the alignment grid, not the measured camera acquisition rate.',
            )
            np.savez_compressed(episode / 'aligned.npz', **aligned)
            (episode / 'alignment_report.json').write_text(json.dumps(alignment, indent=2), encoding='utf-8')
            with np.load(episode / 'aligned.npz', allow_pickle=False) as saved:
                assert len(saved['times']) == alignment['steps'] + 1
                assert len(saved['frame_indices']) == alignment['steps']
                assert len(saved['gripper_actions']) == alignment['steps']
                assert saved['robot_states'].shape == (alignment['steps'] + 1, 9)
                assert np.allclose(np.diff(saved['times']), .05)
                assert np.allclose(np.linalg.norm(saved['quaternions_wxyz'], axis=1), 1)
                assert all(np.isfinite(saved[key]).all() for key in saved.files)
            assert alignment['input_sha256'] == input_hashes(episode)
            report.update(status='aligned', source_pngs_checked=len(frames),
                          mp4_frames_decoded=decoded, real_success=meta.get('real_success'),
                          layout_reference_match='unconfirmed', **alignment)
            print(f'video{number}: {alignment["steps"]} actions, '
                  f'{alignment["max_frame_error_ms"]:.1f} ms max frame error, '
                  f'{default_exceeded} steps exceed default 40 ms', flush=True)
        except Exception as error:
            report['error'] = f'{type(error).__name__}: {error}'
            print(f'video{number}: FAILED: {error}', flush=True)
        reports.append(report)
        (episode / 'postprocess_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        summary = dict(date='2026-10-29', episodes=reports,
                       accepted_max_frame_ms=args.max_frame_ms,
                       timing_quality='See per-episode default_frame_limit_passed; no 30 fps claim.',
                       hdf5_exported=False, layout_reference_match='unconfirmed')
        (out / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    if any(report['status'] != 'aligned' for report in reports):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
