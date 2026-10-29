"""Make a review MP4 from raw PNGs, keeping training frames free of overlays."""
import argparse
import re
import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np

from .prepare import read_jsonl
from .capture_storage import read_image


def create_review(episode, raw=False):
    episode = Path(episode)
    rows = read_jsonl(episode/'frames.jsonl')
    if len(rows) < 2:
        raise ValueError('Need at least two frames.')
    fps = 1/float(np.median(np.diff([r['t_s'] for r in rows])))
    image = read_image(episode/rows[0]['file'])
    if image is None:
        raise ValueError('First frame is unreadable.')
    h, w = image.shape[:2]
    from .color_calibration import apply_rgb, load_profile
    profile_path = episode/'color_profile.json'
    profile = load_profile(profile_path) if profile_path.is_file() and not raw else None
    stem = episode.name if re.fullmatch(r'영상[0-9]+', episode.name) else 'review'
    out = episode / f'{stem}{"_raw" if raw else ""}.mp4'
    if out.exists():
        raise FileExistsError(out)
    # Encode through an ASCII basename; OpenCV video backends may reject Korean paths.
    with tempfile.TemporaryDirectory(prefix='w9-review-') as work:
        encoded = Path(work) / 'review.mp4'
        writer = cv2.VideoWriter(str(encoded), cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
        try:
            if not writer.isOpened():
                raise RuntimeError('MP4 encoder could not open.')
            for row in rows:
                frame = read_image(episode/row['file'])
                if frame is None:
                    raise ValueError(f'Unreadable frame: {row["file"]}')
                if profile:
                    frame = cv2.cvtColor(apply_rgb(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), profile), cv2.COLOR_RGB2BGR)
                writer.write(frame)
        finally:
            writer.release()
        with out.open('xb') as target, encoded.open('rb') as source:
            shutil.copyfileobj(source, target)
    print(f'{out}: {len(rows)} frames, {fps:.2f} fps. Review only; timestamps remain in frames.jsonl.')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('episode', type=Path)
    p.add_argument('--raw', action='store_true', help='Show original RGB even if a colour profile was recorded')
    a = p.parse_args()
    create_review(a.episode, raw=a.raw)


if __name__ == '__main__':
    main()
