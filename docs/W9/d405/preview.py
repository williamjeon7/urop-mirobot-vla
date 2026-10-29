"""Make a review MP4 from raw PNGs, keeping training frames free of overlays."""
import argparse
from pathlib import Path

import cv2
import numpy as np

from .prepare import read_jsonl


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('episode', type=Path)
    p.add_argument('--raw', action='store_true', help='Show original RGB even if a colour profile was recorded')
    a = p.parse_args()
    rows = read_jsonl(a.episode/'frames.jsonl')
    if len(rows) < 2:
        p.error('Need at least two frames.')
    fps = 1/float(np.median(np.diff([r['t_s'] for r in rows])))
    image = cv2.imread(str(a.episode/rows[0]['file']))
    if image is None:
        raise ValueError('First frame is unreadable.')
    h, w = image.shape[:2]
    from .color_calibration import apply_rgb, load_profile
    profile_path = a.episode/'color_profile.json'
    profile = load_profile(profile_path) if profile_path.is_file() and not a.raw else None
    out = a.episode/('review_raw.mp4' if a.raw else 'review.mp4')
    if out.exists():
        raise FileExistsError(out)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError('MP4 encoder could not open.')
    try:
        for row in rows:
            frame = cv2.imread(str(a.episode/row['file']))
            if frame is None:
                raise ValueError(f'Unreadable frame: {row["file"]}')
            if profile:
                frame = cv2.cvtColor(apply_rgb(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), profile), cv2.COLOR_RGB2BGR)
            writer.write(frame)
    finally:
        writer.release()
    print(f'{out}: {len(rows)} frames, {fps:.2f} fps. Review only; timestamps remain in frames.jsonl.')


if __name__ == '__main__':
    main()
