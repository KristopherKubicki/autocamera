import logging
import subprocess
import threading
import time
from logging.handlers import RotatingFileHandler

import cv2

# Runtime configured paths
LOG_PATH: str | None = None
GPHOTO2_PATH = "/usr/bin/gphoto2"
FFMPEG_PATH = "/usr/bin/ffmpeg"

app_logger = logging.getLogger(__name__)

gphoto2_process: subprocess.Popen | None = None
ffmpeg_process: subprocess.Popen | None = None
frame_buffer = None
frame_buffer_time: float | None = None


def configure_logging(path: str) -> None:
    """Configure rotating file logging."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def setup_camera() -> None:
    """Set up camera modules and dependencies."""
    global gphoto2_process, ffmpeg_process
    subprocess.run(["sudo", "pkill", "-9", "gphoto2"], check=False)
    subprocess.run(["sudo", "rmmod", "v4l2loopback"], check=False)
    subprocess.run(
        ["sudo", "modprobe", "v4l2loopback", "devices=1", "exclusive_caps=1"],
        check=True,
    )

    try:
        gphoto2_process = subprocess.Popen(
            [GPHOTO2_PATH, "--stdout", "--capture-movie"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        app_logger.info("gphoto2 process started")

        ffmpeg_process = subprocess.Popen(
            [
                FFMPEG_PATH,
                "-i",
                "-",
                "-pix_fmt",
                "yuv420p",
                "-f",
                "v4l2",
                "/dev/video0",
            ],
            stdin=gphoto2_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        app_logger.info("ffmpeg process started")

        threading.Thread(target=monitor_ffmpeg_output, daemon=True).start()
        threading.Thread(target=monitor_gphoto_output, daemon=True).start()
    except Exception as exc:  # pragma: no cover - defensive
        app_logger.error("Error in starting camera: %s", exc)
        cleanup_camera()


def cleanup_camera() -> None:
    """Clean up camera processes and resources."""
    global gphoto2_process, ffmpeg_process
    try:
        if gphoto2_process:
            gphoto2_process.terminate()
    except Exception as exc:  # pragma: no cover - defensive
        app_logger.error("Error terminating gphoto2 process: %s", exc)
    try:
        if ffmpeg_process:
            ffmpeg_process.terminate()
    except Exception as exc:  # pragma: no cover - defensive
        app_logger.error("Error terminating ffmpeg process: %s", exc)
    try:
        subprocess.run(["sudo", "pkill", "-9", "gphoto2"], check=False)
        app_logger.info("gphoto2 cleaned up")
    except Exception as exc:  # pragma: no cover - defensive
        app_logger.error("Error running pkill on gphoto2: %s", exc)
    try:
        subprocess.run(["sudo", "rmmod", "v4l2loopback"], check=False)
        app_logger.info("v4l2loopback cleaned up")
    except Exception as exc:  # pragma: no cover - defensive
        app_logger.error("Error cleaning up camera: %s", exc)


def frame_reader() -> None:
    """Read frames from the camera."""
    global frame_buffer, frame_buffer_time
    cap = cv2.VideoCapture("/dev/video0")
    retries = 0
    while True:
        try:
            if not cap.isOpened():
                app_logger.warning("Camera connection lost, retrying...")
                retries += 1
                if retries > 5:
                    app_logger.error(
                        "Failed to reconnect to the camera after multiple attempts."
                    )
                    break
                time.sleep(2)
                cap = cv2.VideoCapture("/dev/video0")
                continue

            ret, frame = cap.read()
            if ret:
                frame_buffer = frame
                frame_buffer_time = time.time()
                retries = 0
                time.sleep(0.1)
            else:
                app_logger.warning("Failed to read frame, camera may be disconnected.")
                retries += 1
                if retries > 500:
                    app_logger.error("Camera read failure, terminating frame reader.")
                    break
                time.sleep(0.1)
        except Exception as exc:  # pragma: no cover - defensive
            app_logger.error("Unexpected error in frame reader: %s", exc)
            break

    cap.release()
    cleanup_camera()


def monitor_ffmpeg_output() -> None:
    """Monitor FFmpeg stderr for errors and shut down if needed."""
    global ffmpeg_process
    while True:
        ffmpeg_output = ffmpeg_process.stderr.readline().decode("utf-8")
        if not ffmpeg_output:
            break
        if (
            "Invalid data found" in ffmpeg_output
            or "Could not find the requested device" in ffmpeg_output
        ):
            app_logger.error("FFmpeg output: %s", ffmpeg_output.strip())
            app_logger.error("FFmpeg encountered a critical error. Shutting down.")
            cleanup_camera()
            break
        else:
            app_logger.info("FFmpeg output: %s", ffmpeg_output.strip())


def monitor_gphoto_output() -> None:
    """Monitor gphoto2 stderr for errors and shut down if needed."""
    global gphoto2_process
    while True:
        gphoto_output = gphoto2_process.stderr.readline().decode("utf-8")
        if not gphoto_output:
            break
        if (
            "Invalid data found" in gphoto_output
            or "Could not find the requested device" in gphoto_output
        ):
            app_logger.error("Gphoto output: %s", gphoto_output.strip())
            app_logger.error("Gphoto encountered a critical error. Shutting down.")
            cleanup_camera()
            break
        else:
            app_logger.info("Gphoto output: %s", gphoto_output.strip())
