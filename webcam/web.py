from __future__ import annotations

import time

from flask import Flask, Response, abort, render_template_string

from . import camera, service

app = Flask(__name__)


def index() -> str:
    """Render status information."""
    info = {
        "Status": "Running",
        "Image Endpoint": "/image",
        "Logs": camera.LOG_PATH or "unknown",
    }
    template = """
    <h1>Webcam Service</h1>
    <ul>
        {% for key, value in info.items() %}
        <li><strong>{{ key }}:</strong> {{ value }}</li>
        {% endfor %}
    </ul>
    <p><a href=\"/image\">View Current Image</a></p>

    <h2>Live Image</h2>
    <img id=\"liveImage\" src=\"/image\" alt=\"Live Image\" width=\"720\">

    <script>
        function refreshImage() {
            var img = document.getElementById('liveImage');
            img.src = '/image?' + new Date().getTime();
        }
        setInterval(refreshImage, 100);
    </script>
    """
    return render_template_string(template, info=info)


@app.route("/image")
def image():
    """Serve the current frame as a JPEG image."""
    if (
        camera.frame_buffer is not None
        and camera.frame_buffer_time
        and camera.frame_buffer_time > time.time() - 5
    ):
        ret, buffer = camera.cv2.imencode(".jpg", camera.frame_buffer)
        if ret:
            return Response(buffer.tobytes(), mimetype="image/jpeg")
    abort(404)


@app.route("/status")
def status() -> dict:
    """Return JSON-friendly status information."""
    age = (
        time.time() - camera.frame_buffer_time
        if camera.frame_buffer_time is not None
        else None
    )
    return {
        "uptime": time.time() - service.start_time,
        "frame_age": age,
        "frame_available": camera.frame_buffer is not None,
    }
