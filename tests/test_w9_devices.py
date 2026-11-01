from types import SimpleNamespace
from unittest.mock import patch

from docs.W9.d405.devices import inspect_devices


def test_device_lookup_distinguishes_robot_com_and_realsense_usb():
    robot = SimpleNamespace(device='COM3', description='Mirobot USB serial', hwid='USB test',
                            vid=1, pid=2, serial_number='ROBOT', location='USBROOT(0)#USB(1)')
    virtual = SimpleNamespace(device='/dev/ttyS0', vid=None, pid=None)
    info = SimpleNamespace(name='name', serial_number='serial_number',
                           physical_port='physical_port', usb_type_descriptor='usb_type_descriptor')
    values = dict(name='Intel RealSense D405', serial_number='262422272124',
                  physical_port='USBROOT(0)#USB(2)', usb_type_descriptor='3.2')
    camera = SimpleNamespace(supports=lambda key: key in values, get_info=values.__getitem__)
    modules = {
        'serial': SimpleNamespace(),
        'serial.tools': SimpleNamespace(list_ports=SimpleNamespace(comports=lambda: [robot, virtual])),
        'pyrealsense2': SimpleNamespace(camera_info=info,
            context=lambda: SimpleNamespace(query_devices=lambda: [camera])),
    }
    with patch.dict('sys.modules', modules):
        report = inspect_devices()
    assert not report['errors']
    assert [p['device'] for p in report['robot_serial_ports']] == ['COM3']
    assert report['robot_serial_ports'][0]['location'] == 'USBROOT(0)#USB(1)'
    assert report['realsense_cameras'][0] == values
    assert 'device' not in report['realsense_cameras'][0]
