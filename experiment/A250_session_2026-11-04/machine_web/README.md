# A250 Machine Console

A small Flask web application for camera preview, printer status, and guarded
XYZ jog controls. The page uses the camera's existing MJPEG stream on port 8080
and reads Klipper through Moonraker on localhost port 7125.

## Run on the A250

Copy this directory to `/home/cps/A250/machine_web`, then install Flask in a
virtual environment and start the server:

```sh
cd /home/cps/A250/machine_web
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python server.py --host 0.0.0.0 --port 8766
```

Open `http://192.168.31.187:8766/` on a device on the same LAN. The server
prints a one-session motion token; enter it in the page before attempting a jog.
The camera stream is available at `http://192.168.31.187:8080/`.

This prototype uses Flask's threaded development server. Keep it on a trusted
LAN, leave debug mode off, and do not expose port 8766 to the public internet.
For a production deployment, run the Flask app behind a production WSGI server.

## Motion interlock

Jogging is locked unless **all** checks pass:

- `/home/cps/printer_data/config/machine_ui_safety.json` contains
  `{"motion_verified": true}`. Create this only after a qualified person has
  physically verified endstop operation, motor direction, and the motion path.
- The active `printer.cfg` no longer contains the three known unsafe bring-up
  warnings that this server checks.
- Klipper is ready, all XYZ axes are homed, the printer is idle, the position is
  within the configured 0–262 mm range, and the extruder temperature is 0–60 °C
  with target 0.

There is intentionally no home, extrusion, solenoid, or heater control. Jogging
is limited to 10 mm per press at 5 mm/s. Do not create the safety marker just to
unlock controls; first resolve the hardware/configuration warnings and verify
the machine physically.

## Network note

The interface is intended for the A250's trusted LAN. The page and live preview
are readable without authentication; jog requests additionally require the
server's per-session token.
