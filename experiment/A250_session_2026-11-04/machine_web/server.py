#!/usr/bin/env python3
"""LAN-only A250 camera and guarded jog interface, served with Flask.

Motion stays locked unless a local safety marker exists, active Klipper
configuration no longer contains the known bring-up warnings, all axes are
homed, the printer is idle, and temperature/position checks pass.
"""
from __future__ import annotations

import argparse
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, Response, current_app, jsonify, request

ROOT = Path(__file__).resolve().parent
MOONRAKER = "http://127.0.0.1:7125"
CAMERA = "http://127.0.0.1:8080"
KNOWN_UNSAFE = (
    "HOMING WILL NOT PHYSICALLY WORK YET",
    "Motor DIR and endstop polarity are UNVERIFIED",
    "Machine is NOT in a safe-to-move state right now",
)
AXES = {"x": (0.0, 262.0), "y": (0.0, 262.0), "z": (0.0, 262.0)}

app = Flask(__name__, static_folder=None)
app.config.update(
    MAX_CONTENT_LENGTH=4096,
    CONFIG_PATH=Path.home() / "printer_data" / "config" / "printer.cfg",
    SAFETY_MARKER=Path.home() / "printer_data" / "config" / "machine_ui_safety.json",
    MOTION_TOKEN="",
)


def get_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, body: dict, timeout: float = 3.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def status_data() -> dict:
    info = get_json(MOONRAKER + "/printer/info")["result"]
    query = urllib.parse.quote(
        "toolhead=position,homed_axes&gcode_move=position&"
        "extruder=temperature,target&heater_bed=temperature,target&print_stats=state",
        safe="=,&",
    )
    state = get_json(MOONRAKER + "/printer/objects/query?" + query)["result"]["status"]
    toolhead = state.get("toolhead", {})
    raw_pos = toolhead.get("position", [None, None, None])
    pos = {axis: raw_pos[i] if len(raw_pos) > i else None
           for i, axis in enumerate("xyz")}
    extruder = state.get("extruder", {})
    temp = extruder.get("temperature")
    target = extruder.get("target")
    homed = toolhead.get("homed_axes", "")
    print_state = state.get("print_stats", {}).get("state", "unknown")

    reasons: list[str] = []
    marker = current_app.config["SAFETY_MARKER"]
    try:
        marker_data = json.loads(marker.read_text())
        if marker_data.get("motion_verified") is not True:
            reasons.append("Local motion safety marker is not verified")
    except (OSError, json.JSONDecodeError):
        reasons.append("Local motion safety marker is missing")
    try:
        cfg = current_app.config["CONFIG_PATH"].read_text(errors="replace")
        reasons.extend(f"Printer config still flags: {warning}" for warning in KNOWN_UNSAFE
                       if warning in cfg)
    except OSError:
        reasons.append("Could not read active printer configuration")
    if info.get("state") != "ready":
        reasons.append("Klipper is not ready")
    if not all(axis in homed for axis in "xyz"):
        reasons.append("All XYZ axes must be homed")
    if print_state not in ("standby", "complete", "cancelled"):
        reasons.append(f"Printer is not idle (state: {print_state})")
    if temp is None or temp < 0 or temp > 60 or (target or 0) != 0:
        reasons.append("Extruder temperature/sensor must be verified and cool (0–60 °C, target 0)")
    for axis, value in pos.items():
        low, high = AXES[axis]
        if value is None or not low <= value <= high:
            reasons.append(f"{axis.upper()} position is outside the configured travel range")

    return {
        "connected": info.get("state") == "ready",
        "hostname": info.get("hostname", "A250"),
        "printer_state": info.get("state"),
        "print_state": print_state,
        "position": pos,
        "homed_axes": homed,
        "extruder_temperature": temp,
        "extruder_target": target,
        "bed_temperature": state.get("heater_bed", {}).get("temperature"),
        "motion_enabled": not reasons,
        "motion_lock_reasons": reasons,
        "camera_stream_path": "/?action=stream",
    }


@app.after_request
def disable_caching(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(404)
def not_found(_error: Exception):
    return jsonify(error="Not found"), 404


@app.errorhandler(413)
def request_too_large(_error: Exception):
    return jsonify(error="Request body too large"), 413


@app.get("/")
def index() -> Response:
    return Response((ROOT / "index.html").read_bytes(), mimetype="text/html")


@app.get("/api/status")
def api_status():
    try:
        return jsonify(status_data())
    except Exception as exc:  # report a connection failure to the UI
        return jsonify(connected=False, error=str(exc)), 503


@app.get("/api/camera-check")
def api_camera_check():
    try:
        req = urllib.request.Request(CAMERA + "/snapshot", method="GET")
        with urllib.request.urlopen(req, timeout=3) as response:
            return jsonify(
                available=response.status == 200,
                bytes=response.headers.get("Content-Length"),
            )
    except Exception as exc:
        return jsonify(available=False, error=str(exc)), 503


@app.post("/api/jog")
def api_jog():
    if request.headers.get("Authorization") != "Bearer " + current_app.config["MOTION_TOKEN"]:
        return jsonify(error="Enter the session token shown in the server console"), 401

    try:
        raw_body = request.get_data(cache=False)
        body = json.loads(raw_body or b"{}")
        axis = str(body.get("axis", "")).lower()
        delta = float(body.get("delta", 0))
        if axis not in AXES or not 0 < abs(delta) <= 10:
            raise ValueError("Choose X/Y/Z and a jog distance up to 10 mm")
        status = status_data()
        if not status["motion_enabled"]:
            return jsonify(error="Motion locked", reasons=status["motion_lock_reasons"]), 423
        target = float(status["position"][axis]) + delta
        low, high = AXES[axis]
        if not low <= target <= high:
            raise ValueError(f"Target {axis.upper()} would exceed {low:g}–{high:g} mm travel")
        # Use a fresh Klipper position; never issue E-axis or solenoid commands.
        script = f"G90\nG1 {axis.upper()}{target:.3f} F300"
        post_json(MOONRAKER + "/printer/gcode/script", {"script": script})
        return jsonify(accepted=True, axis=axis.upper(), target=target)
    except (ValueError, TypeError, KeyError, urllib.error.URLError) as exc:
        return jsonify(error=str(exc)), 400


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a guarded A250 camera/jog page with Flask")
    parser.add_argument("--host", default="127.0.0.1", help="bind address; use 0.0.0.0 for LAN access")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--config", type=Path, default=app.config["CONFIG_PATH"])
    parser.add_argument("--safety-marker", type=Path, default=app.config["SAFETY_MARKER"])
    args = parser.parse_args()

    app.config.update(
        CONFIG_PATH=args.config,
        SAFETY_MARKER=args.safety_marker,
        MOTION_TOKEN=secrets.token_urlsafe(24),
    )
    print(f"A250 UI at http://{args.host}:{args.port}/", flush=True)
    print(f"Motion session token: {app.config['MOTION_TOKEN']}", flush=True)
    print("Motion remains locked until local safety checks and marker are satisfied.", flush=True)
    # Flask's threaded development server is intended for this trusted-LAN prototype.
    # Keep debug and the reloader disabled; never expose this port to the public internet.
    try:
        app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
