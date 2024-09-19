#!/usr/bin/python3


import subprocess
import signal
import sys
from flask import Flask, Response, abort
import cv2
import threading
import time
import logging

frame_buffer = None
frame_buffer_time = None
buffer_lock = threading.Lock()

app = Flask(__name__)
gphoto2_process = None  # Global variable to keep track of the gphoto2 process


logging.basicConfig(filename='/var/log/webcam.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')
logging.info('Webcam script started')


def setup_camera():
    """Set up camera module and other dependencies."""
    subprocess.run(['sudo', 'pkill', '-9', 'gphoto2'], check=False)
    subprocess.run(['sudo', 'rmmod', 'v4l2loopback'], check=False)
    subprocess.run(['sudo', 'modprobe', 'v4l2loopback', 'devices=1'], check=False)
    # Start gphoto2 process

    # Start the gphoto2 process
    gphoto2_process = subprocess.Popen(
        ['gphoto2', '--stdout', '--capture-movie'],
        stdout=subprocess.PIPE  # Pipe the stdout to a Python pipe
    )
    logging.info('Webcam gphoto2 process started')

    # Start the ffmpeg process, taking the stdout of gphoto2 as its input
    ffmpeg_process = subprocess.Popen(
        #['ffmpeg', '-i', '-', '-listen', '1', '-vcodec', 'rawvideo', '-pix_fmt', 'yuv420p', '-threads', '0', '-f', 'v4l2', '/dev/video0', '-pix_fmt', 'yuv420p', '-threads', '0', '-f', 'v4l2', '/dev/video1'],
        ['ffmpeg', '-i', '-', '-listen', '1', '-vcodec', 'rawvideo', '-pix_fmt', 'yuv420p', '-threads', '0', '-f', 'v4l2', '/dev/video0'],
        stdin=gphoto2_process.stdout  # Use the output of gphoto2 as input
    )


    logging.info('Webcam camera thread complete')


def cleanup_camera():
    """Clean up and release camera module and other resources."""
    subprocess.run(['sudo', 'pkill', '-9', 'gphoto2'], check=False)
    subprocess.run(['sudo', 'rmmod', 'v4l2loopback'], check=False)
    logging.info('Webcam gphoto2 cleaned up')

def signal_handler(sig, frame):
    """Handle incoming signals (such as SIGINT for Ctrl+C)."""
    cleanup_camera()
    sys.exit(0)


def frame_reader():
    global frame_buffer, frame_buffer_time
    cap = cv2.VideoCapture('/dev/video0')
    while True:
        try:
            ret, frame = cap.read()
            if ret is True:
                with buffer_lock:
                    frame_buffer = frame
                    frame_buffer_time = time.time()
                time.sleep(1)  # Read frames every 50ms
            else:
                # the show is over
                break
        except Exception as e:
            print(" warning!  time to shut down...", e)
    logging.info('Webcam finishing')
    cleanup_camera()
    sys.exit(0)

@app.route('/image')
def image2():
    with buffer_lock:
        if frame_buffer is not None and frame_buffer_time > time.time() - 5: # five second timeout
            ret, buffer = cv2.imencode('.jpg', frame_buffer)
            if ret:
                return Response(buffer.tobytes(), mimetype='image/jpeg')
        abort(404)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    setup_camera()
    threading.Thread(target=frame_reader, daemon=True).start()

    try:
        app.run(host='0.0.0.0', port=9007)
    except OSError as e:
        print("Port 9007 is already in use or unavailable: ", e)
        logging.error('Webcam startup error')

