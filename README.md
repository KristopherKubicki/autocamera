# Autocamera

`webcam.py` exposes a DSLR or other camera as a virtual webcam device and
provides a small Flask server to show the current frame. It relies on gphoto2,
ffmpeg, v4l2loopback, OpenCV, and Flask.

## Requirements

- Python 3
- gphoto2
- ffmpeg
- v4l2loopback
- OpenCV (`cv2`)
- Flask

Python dependencies can be installed with:

```bash
pip install -r requirements.txt
```

After installing the dependencies, set up Git hooks with:

```bash
pre-commit install
```

## Usage

```bash
python3 webcam.py [--port PORT] [--start|--stop|--install|--uninstall]
                  [--vendor VENDOR_ID] [--product PRODUCT_ID]
                  [--vendor-pattern REGEX]
                  [--log-file PATH]
                  [--log-file PATH] [--gphoto2 PATH] [--ffmpeg PATH]
```

Most operations interact with system modules and may require root privileges.
Use `sudo` when necessary.

Running the script without arguments is the same as `--start`.
Default port: **9007**.

### Start the service

```bash
python3 webcam.py --start
```

### Install as a service

```bash
sudo python3 webcam.py --install --vendor <VENDOR_ID> --product <PRODUCT_ID>
```

Installing the service writes udev rules and therefore requires root
permissions. If vendor and product IDs are not provided, the script attempts to
detect them with `lsusb`, matching the vendor name with the regular expression
specified by `--vendor-pattern` (default: `Canon`).
On success the script prints the path of the new rule and confirms that
`udevadm` reloaded. You can verify the rule with:

```bash
cat /etc/udev/rules.d/99-webcam.rules
```

If the file contains the rule, reconnecting the camera should automatically
start the service.

### Stop the service

```bash
python3 webcam.py --stop
```

### Uninstall

```bash
sudo python3 webcam.py --uninstall
```

When uninstallation succeeds the script reports the rule removal. Check that
`/etc/udev/rules.d/99-webcam.rules` no longer exists and reconnecting the camera
does not start the service.

## Web Interface

After starting, visit `http://localhost:9007/` for a small status page.
The endpoint `/image` returns the latest frame as a JPEG.
The endpoint `/status` returns a JSON object with uptime and frame info.

## Logging

By default logs are written to `./webcam.log`. You can change the location with
the `--log-file` command-line option or the `WEBCAM_LOG_PATH` environment
variable. Logs rotate automatically when they reach about 1&nbsp;MB.

## Executable Paths

If `gphoto2` or `ffmpeg` are not installed in standard locations, provide their
paths with the `--gphoto2` and `--ffmpeg` options. The environment variables
`GPHOTO2_PATH` and `FFMPEG_PATH` can also be used to override the defaults.

## License

This project is licensed under the MIT License.
