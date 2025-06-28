#!/usr/bin/python3

import os
import subprocess
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import cv2
from flask import Flask, Response, abort, render_template_string
import argparse
import signal
import sys
import re

app = Flask(__name__)
gphoto2_process = None
ffmpeg_process = None
frame_buffer = None
frame_buffer_time = None

# Path to the log file. This will be configured in ``main`` based on
# command-line arguments or environment variables.
LOG_PATH = None


def configure_logging(path):
    """Configure rotating file logging."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def setup_camera():
    """Set up camera module and other dependencies."""
    global gphoto2_process, ffmpeg_process

    # Clean up any existing camera processes
    subprocess.run(['sudo', 'pkill', '-9', 'gphoto2'], check=False)
    subprocess.run(['sudo', 'rmmod', 'v4l2loopback'], check=False)
    subprocess.run(['sudo', 'modprobe', 'v4l2loopback', 'devices=1', 'exclusive_caps=1'], check=True)

    try:
        # Start gphoto2 process
        gphoto2_process = subprocess.Popen(
            ['/usr/bin/gphoto2', '--stdout', '--capture-movie'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logging.info('gphoto2 process started')

        # Start ffmpeg process
        ffmpeg_process = subprocess.Popen(
            ['/usr/bin/ffmpeg', 
                #'-reconnect', '1', '-reconnect_at_eof', '1',
                #'-reconnect_streamed', '1', '-reconnect_delay_max', '2',
                #'-fflags', 'nobuffer',
                '-i', '-', 
                '-pix_fmt', 'yuv420p',
                '-f', 'v4l2', '/dev/video0'],
            stdin=gphoto2_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        logging.info('ffmpeg process started')

        # Start a thread to monitor FFmpeg for errors
        threading.Thread(target=monitor_ffmpeg_output, daemon=True).start()
        threading.Thread(target=monitor_gphoto_output, daemon=True).start()

    except Exception as e:
        logging.error(f'Error in starting camera: {e}')
        cleanup_camera()

def cleanup_camera():
    """Clean up camera processes and resources."""
    global gphoto2_process, ffmpeg_process

    try:
        if gphoto2_process:
            gphoto2_process.terminate()
    except Exception as e:
        logging.error(f'Error terminating gphoto2 process: {e}')
    try:
        if ffmpeg_process:
            ffmpeg_process.terminate()
    except Exception as e:
        logging.error(f'Error terminating ffmpeg process: {e}')

    try:
        subprocess.run(['sudo', 'pkill', '-9', 'gphoto2'], check=False)
        logging.info('gphoto2 cleaned up')
    except Exception as e:
        logging.error(f'Error running pkill on gphoto2: {e}')
    try:
        subprocess.run(['sudo', 'rmmod', 'v4l2loopback'], check=False)
        logging.info('v4l2loopback cleaned up')
    except Exception as e:
        logging.error(f'Error cleaning up camera: {e}')

def frame_reader():
    """Read frames from the camera."""
    global frame_buffer, frame_buffer_time
    cap = cv2.VideoCapture('/dev/video0')
    retries = 0

    while True:
        try:
            if not cap.isOpened():
                logging.warning("Camera connection lost, retrying...")
                retries += 1
                if retries > 5:
                    logging.error("Failed to reconnect to the camera after multiple attempts.")
                    break
                time.sleep(2)
                cap = cv2.VideoCapture('/dev/video0')
                continue

            ret, frame = cap.read()
            if ret:
                frame_buffer = frame
                frame_buffer_time = time.time()
                retries = 0
                time.sleep(0.1)  # Control frame reading rate
            else:
                logging.warning("Failed to read frame, camera may be disconnected.")
                retries += 1
                if retries > 500:
                    logging.error("Camera read failure, terminating frame reader.")
                    break
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"Unexpected error in frame reader: {e}")
            break

    cap.release()
    cleanup_camera()

@app.route('/')
def index():
    """Provide useful information at the root endpoint."""
    global LOG_PATH
    info = {
        'Status': 'Running',
        'Image Endpoint': '/image',
        'Logs': LOG_PATH or 'unknown'
    }
    template = '''
    <h1>Webcam Service</h1>
    <ul>
        {% for key, value in info.items() %}
        <li><strong>{{ key }}:</strong> {{ value }}</li>
        {% endfor %}
    </ul>
    <p><a href="/image">View Current Image</a></p>

    <h2>Live Image</h2>
    <img id="liveImage" src="/image" alt="Live Image" width="720">

    <script>
        function refreshImage() {
            var img = document.getElementById('liveImage');
            img.src = '/image?' + new Date().getTime(); // Add timestamp to avoid caching
        }
        setInterval(refreshImage, 100); // Refresh every 100 ms
    </script>
    '''
    return render_template_string(template, info=info)


@app.route('/image')
def image():
    """Serve the current frame as an image."""
    global frame_buffer, frame_buffer_time
    if frame_buffer is not None and frame_buffer_time > time.time() - 5:  # five-second timeout
        ret, buffer = cv2.imencode('.jpg', frame_buffer)
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    abort(404)


def monitor_ffmpeg_output():
    """Monitor FFmpeg stderr for errors and shut down if necessary."""
    global ffmpeg_process
    while True:
        ffmpeg_output = ffmpeg_process.stderr.readline().decode('utf-8')
        if not ffmpeg_output:
            break
        if "Invalid data found" in ffmpeg_output or "Could not find the requested device" in ffmpeg_output:
            logging.error(f"FFmpeg output: {ffmpeg_output.strip()}")
            logging.error("FFmpeg encountered a critical error. Shutting down.")
            cleanup_camera()
            break
        else:
            logging.info(f"FFmpeg output: {ffmpeg_output.strip()}")

def monitor_gphoto_output():
    """Monitor Gphoto stderr for errors and shut down if necessary."""
    global gphoto2_process
    while True:
        gphoto_output = gphoto2_process.stderr.readline().decode('utf-8')
        if not gphoto_output:
            break
        if "Invalid data found" in gphoto_output or "Could not find the requested device" in gphoto_output:
            logging.error(f"Gphoto output: {gphoto_output.strip()}")
            logging.error("Gphoto encountered a critical error. Shutting down.")
            cleanup_camera()
            break
        else:
            logging.info(f"Gphoto output: {gphoto_output.strip()}")

def signal_handler(sig, frame):
    """Handle incoming signals (such as SIGINT for Ctrl+C)."""
    logging.info("Received signal to stop. Cleaning up...")
    cleanup_camera()
    sys.exit(0)

def start_webcam_service(port):
    """Start the webcam service."""
    try:
        setup_camera()

        # Kill any process listening on the port
        kill_existing_processes(port)

        threading.Thread(target=frame_reader, daemon=True).start()
        app.run(host='0.0.0.0', port=port)
    except OSError as e:
        logging.error(f'Error starting webcam service: {e}')

def kill_existing_processes(port):
    """Kill any process listening on the specified port."""
    try:
        result = subprocess.check_output(f"lsof -i :{port} | grep LISTEN", shell=True).decode('utf-8').strip()
        if result:
            lines = result.split('\n')
            for line in lines:
                pid = line.split()[1]
                subprocess.run(['sudo', 'kill', '-9', pid])
                logging.info(f"Killed process {pid} on port {port}")
    except subprocess.CalledProcessError:
        logging.info(f"No process found on port {port}")

def install_service(script_path, vendor_id, product_id):
    """Install the webcam service to autostart when the camera is connected."""
    logging.info("Installing webcam service...")

    udev_rule = (
        f'SUBSYSTEM=="usb", ATTR{{idVendor}}=="{vendor_id}", ATTR{{idProduct}}=="{product_id}", ACTION=="add", RUN+="{script_path} --start"\n'
        f'SUBSYSTEM=="usb", ATTR{{idVendor}}=="{vendor_id}", ATTR{{idProduct}}=="{product_id}", ACTION=="remove", RUN+="{script_path} --stop"'
    )
    udev_file = '/etc/udev/rules.d/99-webcam.rules'

    try:
        # Write the udev rule
        with open(udev_file, 'w') as f:
            f.write(udev_rule + '\n')
        logging.info(f"Udev rule written to {udev_file}")

        # Reload udev rules
        subprocess.run(['sudo', 'udevadm', 'control', '--reload'])
        subprocess.run(['sudo', 'udevadm', 'trigger'])
        logging.info("Udev rules reloaded")

    except Exception as e:
        logging.error(f"Error installing udev rule: {e}")

def uninstall_service():
    """Uninstall the webcam service."""
    logging.info("Uninstalling webcam service...")
    cleanup_camera()

    udev_file = '/etc/udev/rules.d/99-webcam.rules'

    try:
        # Remove udev rule
        if os.path.exists(udev_file):
            os.remove(udev_file)
            logging.info(f"Removed udev rule {udev_file}")

            # Reload udev rules
            subprocess.run(['sudo', 'udevadm', 'control', '--reload'])
            subprocess.run(['sudo', 'udevadm', 'trigger'])
            logging.info("Udev rules reloaded")
        else:
            logging.warning("Udev rule not found; nothing to uninstall.")
    except Exception as e:
        logging.error(f"Error during uninstall: {e}")

def auto_detect_camera_ids():
    """Attempt to auto-detect camera vendor and product IDs using lsusb."""
    try:
        lsusb_output = subprocess.check_output(['lsusb']).decode('utf-8')
        camera_devices = re.findall(r'Bus \d+ Device \d+: ID (\w+):(\w+) .*Canon.*', lsusb_output)
        if camera_devices:
            vendor_id, product_id = camera_devices[0]
            logging.info(f"Auto-detected vendor ID: {vendor_id}, product ID: {product_id}")
            return vendor_id, product_id
        else:
            logging.warning("No Canon camera found via lsusb.")
    except Exception as e:
        logging.error(f"Error auto-detecting camera IDs: {e}")
    return None, None

def main():
    parser = argparse.ArgumentParser(description="Webcam service")
    parser.add_argument('--port', type=int, default=9007, help='Port to run the webcam service')
    parser.add_argument('--install', action='store_true', help='Install the webcam service')
    parser.add_argument('--start', action='store_true', help='Start the webcam service')
    parser.add_argument('--stop', action='store_true', help='Stop the webcam service')
    parser.add_argument('--uninstall', action='store_true', help='Uninstall the webcam service')
    parser.add_argument('--vendor', type=str, help='USB Vendor ID of the camera')
    parser.add_argument('--product', type=str, help='USB Product ID of the camera')
    parser.add_argument('--log-file', type=str, help='Path to log file')

    args = parser.parse_args()

    global LOG_PATH
    LOG_PATH = args.log_file or os.environ.get('WEBCAM_LOG_PATH') or './webcam.log'
    configure_logging(LOG_PATH)
    logging.info('Webcam script started')

    # Determine vendor and product IDs
    vendor_id = args.vendor
    product_id = args.product

    if args.install:
        if not vendor_id or not product_id:
            vendor_id, product_id = auto_detect_camera_ids()
            if not vendor_id or not product_id:
                logging.error("Vendor ID and Product ID are required for installation.")
                print(" >>> enable camera first")
                sys.exit(1)
        script_path = os.path.abspath(__file__)
        install_service(script_path, vendor_id, product_id)
        logging.info("Webcam service installed.")
    elif args.uninstall:
        kill_existing_processes(args.port)
        uninstall_service()
        logging.info("Webcam service uninstalled.")
    elif args.start or len(sys.argv) == 1:
        logging.info("Starting webcam service...")
        kill_existing_processes(args.port)
        start_webcam_service(args.port)
    elif args.stop:
        logging.info("Stopping webcam service...")
        kill_existing_processes(args.port)
        cleanup_camera()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()
