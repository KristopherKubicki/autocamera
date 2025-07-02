import importlib.util
import subprocess
import sys
import time
import types
from unittest import mock

# Create stub modules for cv2 and flask
cv2_stub = types.SimpleNamespace(
    VideoCapture=lambda *a, **k: None, imencode=lambda *a, **k: (True, b"")
)


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


flask_stub = types.SimpleNamespace(
    Flask=FakeFlask,
    Response=fake_response,
    abort=fake_abort,
    render_template_string=fake_render_template_string,
)

sys.modules["cv2"] = cv2_stub
sys.modules["flask"] = flask_stub


spec = importlib.util.spec_from_file_location("webcam", "webcam.py")
webcam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webcam)


def test_auto_detect_camera_ids_found():
    sample = "Bus 001 Device 004: ID 04a9:3270 Canon Camera"
    with mock.patch.object(
        webcam.subprocess, "check_output", return_value=sample.encode()
    ):
        vendor, product = webcam.auto_detect_camera_ids()
        assert vendor == "04a9"
        assert product == "3270"


def test_auto_detect_camera_ids_not_found():
    with mock.patch.object(webcam.subprocess, "check_output", return_value=b""):
        vendor, product = webcam.auto_detect_camera_ids()
        assert vendor is None
        assert product is None


def test_auto_detect_camera_ids_different_vendor():
    sample = "Bus 001 Device 005: ID 04b0:1234 Nikon Camera"
    with mock.patch.object(
        webcam.subprocess, "check_output", return_value=sample.encode()
    ):
        vendor, product = webcam.auto_detect_camera_ids(vendor_pattern="Nikon")
        assert vendor == "04b0"
        assert product == "1234"


def test_kill_existing_processes():
    output = "proc 1234 LISTEN\nproc2 5678 LISTEN"
    with mock.patch.object(
        webcam.subprocess, "check_output", return_value=output.encode()
    ) as m_co:
        with mock.patch.object(webcam.subprocess, "run") as m_run:
            webcam.kill_existing_processes(8000)
            m_co.assert_called_once_with(["lsof", "-i", ":8000"])
            m_run.assert_any_call(["sudo", "kill", "-9", "1234"])
            m_run.assert_any_call(["sudo", "kill", "-9", "5678"])


def test_index_uses_template():
    with mock.patch.object(
        webcam, "render_template_string", return_value=""
    ) as m_render:
        assert webcam.index() == ""
        assert m_render.called


def test_image_no_frame_calls_abort():
    webcam.frame_buffer = None
    webcam.frame_buffer_time = 0
    with mock.patch.object(webcam, "abort") as m_abort:
        webcam.image()
        m_abort.assert_called_once_with(404)


def test_image_returns_response_with_jpeg_mimetype():
    webcam.frame_buffer = object()
    webcam.frame_buffer_time = time.time()
    dummy_buffer = types.SimpleNamespace(tobytes=lambda: b"data")
    with mock.patch.object(
        webcam.cv2, "imencode", return_value=(True, dummy_buffer)
    ) as _, mock.patch.object(
        webcam, "Response", return_value="resp"
    ) as m_resp, mock.patch.object(
        webcam, "abort"
    ) as m_abort:
        result = webcam.image()
        assert result == "resp"
        m_resp.assert_called_once()
        args, kwargs = m_resp.call_args
        assert kwargs.get("mimetype") == "image/jpeg"
        assert m_abort.call_count == 0


def test_setup_camera_uses_config_paths():
    gphoto_mock = mock.Mock(stdout="out", stderr=mock.Mock())
    ffmpeg_mock = mock.Mock(stderr=mock.Mock())
    with mock.patch.object(webcam.subprocess, "run"):
        with mock.patch.object(
            webcam.subprocess, "Popen"
        ) as m_popen, mock.patch.object(webcam.threading, "Thread"):
            m_popen.side_effect = [gphoto_mock, ffmpeg_mock]
            webcam.GPHOTO2_PATH = "/opt/gphoto2"
            webcam.FFMPEG_PATH = "/opt/ffmpeg"
            webcam.setup_camera()
            m_popen.assert_any_call(
                ["/opt/gphoto2", "--stdout", "--capture-movie"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            m_popen.assert_any_call(
                [
                    "/opt/ffmpeg",
                    "-i",
                    "-",
                    "-pix_fmt",
                    "yuv420p",
                    "-f",
                    "v4l2",
                    "/dev/video0",
                ],
                stdin=gphoto_mock.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )


def test_install_service_prints_messages():
    with mock.patch("builtins.open", mock.mock_open()), mock.patch.object(
        webcam.subprocess, "run"
    ), mock.patch("builtins.print") as m_print:
        webcam.install_service("/script", "1", "2")
        m_print.assert_any_call("Install complete: /etc/udev/rules.d/99-webcam.rules")
        m_print.assert_any_call("Udev rules reloaded")


def test_uninstall_service_prints_messages():
    with mock.patch.object(
        webcam.os.path, "exists", return_value=True
    ), mock.patch.object(webcam.os, "remove"), mock.patch.object(
        webcam.subprocess, "run"
    ), mock.patch(
        "builtins.print"
    ) as m_print:
        webcam.uninstall_service()
        m_print.assert_any_call(
            "Uninstall complete: /etc/udev/rules.d/99-webcam.rules removed"
        )
        m_print.assert_any_call("Udev rules reloaded")


def test_status_reports_frame_availability():
    webcam.start_time = time.time() - 5
    webcam.frame_buffer = object()
    webcam.frame_buffer_time = time.time()
    result = webcam.status()
    assert isinstance(result, dict)
    assert result["frame_available"]
