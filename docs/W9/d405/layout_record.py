"""Record user-measured paper coordinates and reviewed pickup outcomes.

This module never opens a camera or serial port, moves a robot, or edits capture
metadata, robot/frame logs, or HDF5. The paper-to-robot transform stays unknown.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


COLORS = ('red', 'green', 'blue')
PAPER_FRAME = {
    'name': 'paper_printed_zero',
    'origin': 'intersection of the paper top boundary and the centre line through printed 0',
    'axes': {
        'x': 'toward the top of the fixed initial reference image, out of the paper work area',
        'y': 'toward the left of the fixed initial reference image',
        'z': 'normal to the paper, upward; right-handed',
    },
    'axes_fixed_to': 'paper, not the moving wrist-camera image',
    'grid_spacing_cm': 1.0,
    'point': 'block bottom-face centre projected onto the paper plane',
    'robot_base_registration': None,
    'robot_base_registration_status': 'not_measured',
}


def validate_coordinates(coordinates):
    if not isinstance(coordinates, dict) or set(coordinates) != set(COLORS):
        raise ValueError('Need X,Y coordinates for red, green and blue.')
    result = {}
    for color in COLORS:
        point = coordinates[color]
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f'{color}: need exactly X,Y in cm.')
        if any(isinstance(value, bool) for value in point):
            raise ValueError(f'{color}: coordinates must be finite numbers, not booleans.')
        try:
            values = [float(value) for value in point]
        except (TypeError, ValueError) as error:
            raise ValueError(f'{color}: coordinates must be finite numbers.') from error
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f'{color}: coordinates must be finite numbers.')
        result[color] = values
    return result


def _target(episode, target=None):
    metadata = json.loads((Path(episode)/'metadata.json').read_text(encoding='utf-8'))
    recorded = metadata.get('color')
    if recorded not in COLORS:
        raise ValueError('Capture metadata.color must be red, green or blue.')
    if target is not None and target != recorded:
        raise ValueError(f'Layout/review target {target!r} differs from metadata.color {recorded!r}. '
                         'Do not silently relabel an existing capture.')
    return recorded


def validate_photo(photo):
    """Return verified image bytes and their actual '.png' or '.jpg' extension."""
    photo = Path(photo)
    data = photo.read_bytes()
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        extension = '.png'
    elif data.startswith(b'\xff\xd8\xff'):
        extension = '.jpg'
    else:
        raise ValueError('Layout photo must contain a PNG or JPEG image.')
    # Verify image data rather than trusting a filename or signature alone.
    import cv2
    import numpy as np
    if cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR) is None:
        raise ValueError('Layout photo image is unreadable.')
    return data, extension


def load_capture_layout(template, target, photo_override=None):
    """Preflight a manual layout template before any camera or robot operation.

    A minimal template has target, unit='cm' and blocks={red:[X,Y],...}.
    A photo override is relative to the process working directory; the optional
    template 'photo' is relative to the template file. This loader performs no
    writes and does not convert image estimates into manual measurements.
    """
    template = Path(template)
    document = json.loads(template.read_text(encoding='utf-8'))
    if not isinstance(document, dict):
        raise ValueError('Layout template must be a JSON object.')
    if target not in COLORS or document.get('target') != target:
        raise ValueError('Layout template target must match the requested capture color.')
    if document.get('unit') != 'cm':
        raise ValueError('Layout template coordinates must use cm.')
    if document.get('estimated') is True:
        raise ValueError('Image-estimated layouts cannot be submitted as manual measurements.')
    provenance = document.get('coordinate_source')
    if provenance is not None and provenance not in (
            'manual', 'manual_grid_measurement', 'user_reported_manual_grid_measurement'):
        raise ValueError('Layout template must contain manual measurements, not image estimates.')
    source = document.get('source', '')
    if isinstance(source, str) and any(word in source.lower() for word in ('estimated', 'reconstruct')):
        raise ValueError('Image-estimated layouts cannot be submitted as manual measurements.')
    if 'coordinate_frame' in document and document['coordinate_frame'] != PAPER_FRAME:
        raise ValueError('Layout template coordinate frame differs from the printed-zero paper frame.')
    coordinates = validate_coordinates(document.get('blocks'))
    if photo_override is not None:
        photo = Path(photo_override)
    else:
        supplied = document.get('photo')
        if not isinstance(supplied, str) or not supplied:
            raise ValueError('Supply --layout-photo or a photo path in the layout template.')
        photo = Path(supplied)
        if not photo.is_absolute():
            photo = template.parent/photo
    validate_photo(photo)
    return coordinates, photo


def create_layout(episode, coordinates, photo, target=None):
    """Copy a supplied initial-layout photo and save measured coordinates once."""
    episode = Path(episode)
    target = _target(episode, target)
    blocks = validate_coordinates(coordinates)
    data, extension = validate_photo(photo)
    destination = episode/('layout'+extension)
    layout_path = episode/'layout.json'
    if layout_path.exists() or any((episode/('layout'+suffix)).exists() for suffix in ('.png', '.jpg', '.jpeg')):
        raise FileExistsError('Layout or photo already exists; existing records are preserved.')
    document = {
        'format': 'w9-layout/1', 'target': target, 'unit': 'cm', 'blocks': blocks,
        'photo': destination.name, 'coordinate_frame': PAPER_FRAME,
        'coordinate_source': 'user_reported_manual_grid_measurement',
        'independent_measurement_verified': False,
        'photo_provenance': {
            'source': str(Path(photo)), 'sha256': hashlib.sha256(data).hexdigest(),
            'view': 'user_supplied; overhead view not verified by this tool',
            'timing': 'user asserts this photo and coordinates describe the initial layout',
        },
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    # Exclusive creation of both outputs; retain all pre-existing files.
    with destination.open('xb') as output:
        output.write(data)
    try:
        with layout_path.open('x', encoding='utf-8') as output:
            json.dump(document, output, indent=2, ensure_ascii=False, allow_nan=False)
            output.write('\n')
    except BaseException:
        destination.unlink()  # Only the new photo created by this invocation.
        raise
    return layout_path


def record_outcome(episode, success, target=None):
    """Save a human-reviewed outcome separately from immutable capture metadata."""
    if not isinstance(success, bool):
        raise ValueError('Reviewed success must be a boolean.')
    episode = Path(episode)
    document = {
        'format': 'w9-review/1', 'target': _target(episode, target),
        'real_success': success, 'source': 'user_reviewed_target_pickup',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
    }
    path = episode/'review.json'
    with path.open('x', encoding='utf-8') as output:
        json.dump(document, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write('\n')
    return path


def copy_layout_template(episode, template, target=None):
    """Copy an existing manual layout into a new episode, checking target/frame."""
    template = Path(template)
    document = json.loads(template.read_text(encoding='utf-8'))
    if document.get('unit') != 'cm' or document.get('coordinate_frame') != PAPER_FRAME:
        raise ValueError('Template must use the recorded paper_printed_zero frame in cm.')
    if document.get('coordinate_source') != 'user_reported_manual_grid_measurement':
        raise ValueError('Template must contain user-reported manual measurements, not image estimates.')
    _target(episode, target)
    # For paired same-layout recordings, the reviewed target may change while
    # positions/photo stay the same. Destination metadata supplies the new target.
    photo = Path(document['photo'])
    if photo.is_absolute() or '..' in photo.parts:
        raise ValueError('Template photo must be a relative path inside its folder.')
    return create_layout(episode, document['blocks'], template.parent/photo, target=target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    layout = commands.add_parser('layout', help='Record manually measured initial block centres')
    layout.add_argument('episode', type=Path)
    for color in COLORS:
        layout.add_argument('--'+color, nargs=2, type=float, required=True, metavar=('X', 'Y'))
    layout.add_argument('--photo', type=Path, required=True, help='Initial overhead photo supplied by the user')
    layout.add_argument('--target', choices=COLORS, help='Must match capture metadata.color')
    outcome = commands.add_parser('outcome', help='Record reviewed real pickup success')
    outcome.add_argument('episode', type=Path)
    outcome.add_argument('--success', choices=('yes', 'no'), required=True)
    outcome.add_argument('--target', choices=COLORS)
    args = parser.parse_args()
    if args.command == 'layout':
        result = create_layout(args.episode, {color: getattr(args, color) for color in COLORS},
                               args.photo, args.target)
    else:
        result = record_outcome(args.episode, args.success == 'yes', args.target)
    print('Saved:', result)


if __name__ == '__main__':
    main()
