"""Numbered episode folders and Unicode-safe OpenCV image paths on Windows."""
from pathlib import Path
import re


def resolve_blue_episode(root, number):
    """Resolve the ten renamed historical blue recordings on local/server copies."""
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 10:
        raise ValueError('Historical blue episode number must be 1..10.')
    root = Path(root)
    renamed = root/f'layoutblue{number}'
    return renamed if renamed.is_dir() else root/f'영상{number}'


def reserve_episode(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for child in root.iterdir()
               if (m := re.fullmatch(r'(?:영상|layoutblue)([0-9]+)', child.name))]
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
