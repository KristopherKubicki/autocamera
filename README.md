# Autocamera

Autocamera exposes a DSLR or other supported camera as a virtual webcam.
It relies on **gphoto2** and **ffmpeg** to capture video frames and on
`v4l2loopback` to create the virtual device. A small Flask application
provides a status page and endpoints to fetch the latest image.

## Features

- Stream frames from gphoto2 into a virtual webcam device
- Simple web interface for current frame and status information
- Install/uninstall helper for udev rules
- Lightweight logging with automatic rotation

## Requirements

- Python 3
- gphoto2
- ffmpeg
- v4l2loopback
- OpenCV (`cv2`)
- Flask

Install Python dependencies with:

```bash
pip install -r requirements.txt
```

Dependencies are version-pinned for reproducible installs.

## Usage

System packages may require your distribution's package manager, for
example on Debian/Ubuntu:

```bash
sudo apt install gphoto2 ffmpeg v4l2loopback-dkms
```

## Usage

Run the script without arguments to start streaming:

```bash
python3 webcam
```

The script accepts several options:

```bash
python3 webcam [--port PORT] [--start|--stop|--install|--uninstall]
                  [--vendor VENDOR_ID] [--product PRODUCT_ID]
                  [--vendor-pattern REGEX]
                  [--log-file PATH] [--gphoto2 PATH] [--ffmpeg PATH]
```

Most operations require interaction with system modules and may need
root privileges. Use `sudo` when necessary.

### Service management

Install the webcam service so that it starts automatically when the
camera is plugged in:

```bash
sudo python3 webcam --install --vendor <VENDOR_ID> --product <PRODUCT_ID>
```

To stop the service or remove the udev rule use `--stop` and
`--uninstall` respectively.

### Web interface

Visit `http://localhost:9007/` after starting for a simple status page.
The endpoint `/image` returns the latest frame as a JPEG and `/status`
returns JSON with basic information.

## Development

Run the unit tests with:

```bash
pytest
```

The tests stub out system dependencies so they can run without a camera
attached.

## License

This project is licensed under the MIT License.
