import sys
import types
import importlib.util
from unittest import mock

# Create stub modules for cv2 and flask
cv2_stub = types.SimpleNamespace(VideoCapture=lambda *a, **k: None,
                                 imencode=lambda *a, **k: (True, b""))
class FakeFlask:
    def __init__(self, *a, **k):
        pass
    def route(self, *a, **k):
        def decorator(f):
            return f
        return decorator
    def run(self, *a, **k):
        pass

def fake_response(*a, **k):
    return None

def fake_abort(*a, **k):
    return None

def fake_render_template_string(*a, **k):
    return ""

flask_stub = types.SimpleNamespace(Flask=FakeFlask,
                                   Response=fake_response,
                                   abort=fake_abort,
                                   render_template_string=fake_render_template_string)

sys.modules['cv2'] = cv2_stub
sys.modules['flask'] = flask_stub

spec = importlib.util.spec_from_file_location('webcam', 'webcam.py')
webcam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webcam)
import subprocess

def test_auto_detect_camera_ids_found():
    sample = "Bus 001 Device 004: ID 04a9:3270 Canon Camera"
    with mock.patch.object(webcam.subprocess, 'check_output', return_value=sample.encode()):
        vendor, product = webcam.auto_detect_camera_ids()
        assert vendor == '04a9'
        assert product == '3270'

def test_auto_detect_camera_ids_not_found():
    with mock.patch.object(webcam.subprocess, 'check_output', return_value=b""):
        vendor, product = webcam.auto_detect_camera_ids()
        assert vendor is None
        assert product is None

def test_kill_existing_processes():
    output = "proc 1234 listen\nproc2 5678 listen"
    with mock.patch.object(webcam.subprocess, 'check_output', return_value=output.encode()):
        with mock.patch.object(webcam.subprocess, 'run') as m_run:
            webcam.kill_existing_processes(8000)
            m_run.assert_any_call(['sudo', 'kill', '-9', '1234'])
            m_run.assert_any_call(['sudo', 'kill', '-9', '5678'])


def test_index_uses_template():
    with mock.patch.object(webcam, 'render_template_string', return_value="") as m_render:
        assert webcam.index() == ""
        assert m_render.called


def test_image_no_frame_calls_abort():
    webcam.frame_buffer = None
    webcam.frame_buffer_time = 0
    with mock.patch.object(webcam, 'abort') as m_abort:
        webcam.image()
        m_abort.assert_called_once_with(404)

