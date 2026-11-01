"""List robot serial ports and RealSense USB identities without moving hardware."""
from __future__ import annotations

import argparse
import json


def inspect_devices():
    report = dict(robot_serial_ports=[], realsense_cameras=[], errors=[])
    try:
        from serial.tools import list_ports
        for port in list_ports.comports():
            if (port.vid is not None or port.pid is not None or
                    port.device.upper().startswith('COM') or
                    port.device.startswith(('/dev/ttyUSB', '/dev/ttyACM'))):
                report['robot_serial_ports'].append({
                    key: getattr(port, key, None) for key in
                    ('device', 'description', 'hwid', 'vid', 'pid', 'serial_number', 'location')})
    except ImportError:
        report['errors'].append('pyserial is missing; use the W9 capture environment.')
    try:
        import pyrealsense2 as rs
        for device in rs.context().query_devices():
            row = {}
            for key in ('name', 'serial_number', 'physical_port', 'usb_type_descriptor'):
                info = getattr(rs.camera_info, key, None)
                row[key] = device.get_info(info) if info is not None and device.supports(info) else None
            report['realsense_cameras'].append(row)
    except ImportError:
        report['errors'].append('pyrealsense2 is missing; use the W9 capture environment.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-port', default='COM3')
    parser.add_argument('--camera-serial', default='262422272124')
    parser.add_argument('--check', action='store_true', help='Fail if the selected robot/camera is not connected')
    args = parser.parse_args()
    report = inspect_devices()
    report['selected_robot_port'] = args.robot_port
    report['selected_camera_serial'] = args.camera_serial
    report['robot_found'] = any(p['device'] == args.robot_port for p in report['robot_serial_ports'])
    report['camera_found'] = any(c['serial_number'] == args.camera_serial for c in report['realsense_cameras'])
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.check and not (report['robot_found'] and report['camera_found']):
        parser.exit(1, 'Run this on the Windows capture PC with both USB devices connected.\n')


if __name__ == '__main__':
    main()
