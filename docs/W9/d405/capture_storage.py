"""Numbered episode folders and Unicode-safe OpenCV image paths on Windows."""
from pathlib import Path
import re


def reserve_episode(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for child in root.iterdir()
               if (m := re.fullmatch(r'영상([0-9]+)', child.name))]
    number = max(numbers, default=0) + 1
    while True:
        episode = root / f'영상{number}'
        try:
            episode.mkdir()  # Atomic reservation; another recorder cannot overwrite it.
            return episode
        except FileExistsError:
            number += 1


def read_image(path):
    import cv2
    import numpy as np
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def write_image(path, image):
    import cv2
    ok, encoded = cv2.imencode(Path(path).suffix, image)
    if not ok:
        raise OSError(f'Image encoding failed: {path}')
    encoded.tofile(path)
