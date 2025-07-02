from __future__ import annotations

import argparse
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time

from . import camera, web

start_time = time.time()
logger = logging.getLogger(__name__)


def start_webcam_service(port: int) -> None:
    """Start the webcam HTTP service."""
    try:
        camera.setup_camera()
        kill_existing_processes(port)
        threading.Thread(target=camera.frame_reader, daemon=True).start()
        web.app.run(host="0.0.0.0", port=port)
    except OSError as exc:  # pragma: no cover - network env
        logger.error("Error starting webcam service: %s", exc)


def kill_existing_processes(port: int) -> None:
    """Kill any process currently listening on the port."""
    try:
        output = subprocess.check_output(["lsof", "-i", f":{port}"])
        lines = output.decode("utf-8").strip().split("\n")
        for line in lines:
            if "LISTEN" in line:
                pid = line.split()[1]
                subprocess.run(["sudo", "kill", "-9", pid])
                logger.info("Killed process %s on port %s", pid, port)
    except subprocess.CalledProcessError:
        logger.info("No process found on port %s", port)


def install_service(script_path: str, vendor_id: str, product_id: str) -> None:
    """Install the webcam service."""
    logger.info("Installing webcam service...")
    udev_rule = (
        f'SUBSYSTEM=="usb", ATTR{{idVendor}}=="{vendor_id}", '
        f'ATTR{{idProduct}}=="{product_id}", ACTION=="add", '
        f'RUN+="{script_path} --start"\n'
        f'SUBSYSTEM=="usb", ATTR{{idVendor}}=="{vendor_id}", '
        f'ATTR{{idProduct}}=="{product_id}", ACTION=="remove", '
        f'RUN+="{script_path} --stop"'
    )
    udev_file = "/etc/udev/rules.d/99-webcam.rules"
    try:
        with open(udev_file, "w") as f:
            f.write(udev_rule + "\n")
        logger.info("Udev rule written to %s", udev_file)
        print(f"Install complete: {udev_file}")
        subprocess.run(["sudo", "udevadm", "control", "--reload"])
        subprocess.run(["sudo", "udevadm", "trigger"])
        logger.info("Udev rules reloaded")
        print("Udev rules reloaded")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error installing udev rule: %s", exc)


def uninstall_service() -> None:
    """Remove the webcam service."""
    logger.info("Uninstalling webcam service...")
    camera.cleanup_camera()
    udev_file = "/etc/udev/rules.d/99-webcam.rules"
    try:
        if os.path.exists(udev_file):
            os.remove(udev_file)
            logger.info("Removed udev rule %s", udev_file)
            print(f"Uninstall complete: {udev_file} removed")
            subprocess.run(["sudo", "udevadm", "control", "--reload"])
            subprocess.run(["sudo", "udevadm", "trigger"])
            logger.info("Udev rules reloaded")
            print("Udev rules reloaded")
        else:
            logger.warning("Udev rule not found; nothing to uninstall.")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error during uninstall: %s", exc)


def auto_detect_camera_ids(
    vendor_pattern: str = "Canon",
) -> tuple[str | None, str | None]:
    """Attempt to auto-detect camera vendor and product IDs."""
    try:
        lsusb_output = subprocess.check_output(["lsusb"]).decode("utf-8")
        pattern = rf"Bus \d+ Device \d+: ID (\w+):(\w+) .*({vendor_pattern}).*"
        camera_devices = re.findall(pattern, lsusb_output, re.IGNORECASE)
        if camera_devices:
            vendor_id, product_id, _ = camera_devices[0]
            logger.info(
                "Auto-detected vendor ID: %s, product ID: %s", vendor_id, product_id
            )
            return vendor_id, product_id
        logger.warning(
            "No camera matching pattern '%s' found via lsusb.", vendor_pattern
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error auto-detecting camera IDs: %s", exc)
    return None, None


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and execute the requested action."""
    parser = argparse.ArgumentParser(description="Webcam service")
    parser.add_argument(
        "--port", type=int, default=9007, help="Port to run the webcam service"
    )
    parser.add_argument(
        "--install", action="store_true", help="Install the webcam service"
    )
    parser.add_argument("--start", action="store_true", help="Start the webcam service")
    parser.add_argument("--stop", action="store_true", help="Stop the webcam service")
    parser.add_argument(
        "--uninstall", action="store_true", help="Uninstall the webcam service"
    )
    parser.add_argument("--vendor", type=str, help="USB Vendor ID of the camera")
    parser.add_argument("--product", type=str, help="USB Product ID of the camera")
    parser.add_argument(
        "--vendor-pattern",
        type=str,
        default="Canon",
        help="Regex pattern for vendor name when auto-detecting IDs",
    )
    parser.add_argument("--log-file", type=str, help="Path to log file")
    parser.add_argument("--gphoto2", type=str, help="Path to gphoto2 executable")
    parser.add_argument("--ffmpeg", type=str, help="Path to ffmpeg executable")

    args = parser.parse_args(argv)

    camera.LOG_PATH = (
        args.log_file or os.environ.get("WEBCAM_LOG_PATH") or "./webcam.log"
    )
    camera.GPHOTO2_PATH = (
        args.gphoto2 or os.environ.get("GPHOTO2_PATH") or camera.GPHOTO2_PATH
    )
    camera.FFMPEG_PATH = (
        args.ffmpeg or os.environ.get("FFMPEG_PATH") or camera.FFMPEG_PATH
    )
    camera.configure_logging(camera.LOG_PATH)
    logger.info("Webcam script started")

    vendor_id = args.vendor
    product_id = args.product
    vendor_pattern = args.vendor_pattern

    if args.install:
        if not vendor_id or not product_id:
            vendor_id, product_id = auto_detect_camera_ids(vendor_pattern)
            if not vendor_id or not product_id:
                logger.error("Vendor ID and Product ID are required for installation.")
                print(" >>> enable camera first")
                sys.exit(1)
        script_path = os.path.abspath(__file__)
        install_service(script_path, vendor_id, product_id)
        logger.info("Webcam service installed.")
    elif args.uninstall:
        kill_existing_processes(args.port)
        uninstall_service()
        logger.info("Webcam service uninstalled.")
    elif args.start or (argv is None and len(sys.argv) == 1):
        logger.info("Starting webcam service...")
        kill_existing_processes(args.port)
        start_webcam_service(args.port)
    elif args.stop:
        logger.info("Stopping webcam service...")
        kill_existing_processes(args.port)
        camera.cleanup_camera()


# SIGINT handler for CLI execution
signal.signal(signal.SIGINT, lambda _s, _f: camera.cleanup_camera())
