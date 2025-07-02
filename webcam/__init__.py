"""Expose webcam package API."""

import os
import subprocess
import threading

import cv2

from . import camera, service, web
from .web import Response, abort, render_template_string

# Re-export commonly used functions and objects for tests
configure_logging = camera.configure_logging
setup_camera = camera.setup_camera
cleanup_camera = camera.cleanup_camera
frame_reader = camera.frame_reader
monitor_ffmpeg_output = camera.monitor_ffmpeg_output
monitor_gphoto_output = camera.monitor_gphoto_output

kill_existing_processes = service.kill_existing_processes
install_service = service.install_service
uninstall_service = service.uninstall_service
auto_detect_camera_ids = service.auto_detect_camera_ids
start_webcam_service = service.start_webcam_service
main = service.main

app = web.app
index = web.index
image = web.image
status = web.status

# expose globals for unit tests
subprocess = subprocess
threading = threading
os = os
cv2 = cv2
Response = Response
abort = abort
render_template_string = render_template_string
