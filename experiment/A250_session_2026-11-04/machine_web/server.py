#!/usr/bin/env python3
"""Small, LAN-only A250 camera and guarded jog interface.

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MOONRAKER = "http://127.0.0.1:7125"
CAMERA = "http://127.0.0.1:8080"
KNOWN_UNSAFE = (
    "HOMING WILL NOT PHYSICALLY WORK YET",
    "Motor DIR and endstop polarity are UNVERIFIED",
    "Machine is NOT in a safe-to-move state right now",
)
AXES = {"x": (0.0, 262.0), "y": (0.0, 262.0), "z": (0.0, 262.0)}


def get_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, body: dict, timeout: float = 3.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


class A250Handler(BaseHTTPRequestHandler):
    server_version = "A250MachineUI/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def send_json(self, code: int, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 4096:
            raise ValueError("Request body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            data = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/status":
            try:
                self.send_json(200, self.status_data())
            except Exception as exc:  # report connection failure to the UI
                self.send_json(503, {"connected": False, "error": str(exc)})
        elif path == "/api/camera-check":
            try:
                request = urllib.request.Request(CAMERA + "/snapshot", method="GET")
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.send_json(200, {"available": response.status == 200,
                                         "bytes": response.headers.get("Content-Length")})
            except Exception as exc:
                self.send_json(503, {"available": False, "error": str(exc)})
        else:
            self.send_json(404, {"error": "Not found"})

    def status_data(self) -> dict:
        info = get_json(MOONRAKER + "/printer/info")["result"]
        query = urllib.parse.quote(
            "toolhead=position,homed_axes&gcode_move=position&"
            "extruder=temperature,target&heater_bed=temperature,target&print_stats=state",
            safe="=,&",
        )
        state = get_json(MOONRAKER + "/printer/objects/query?" + query)["result"]["status"]
        toolhead = state.get("toolhead", {})
        pos = toolhead.get("position", [None, None, None])
        pos = {axis: pos[i] if len(pos) > i else None for i, axis in enumerate("xyz")}
        extruder = state.get("extruder", {})
        temp = extruder.get("temperature")
        target = extruder.get("target")
        homed = toolhead.get("homed_axes", "")
        print_state = state.get("print_stats", {}).get("state", "unknown")

        reasons: list[str] = []
        marker = self.server.safety_marker
        try:
            marker_data = json.loads(marker.read_text())
            if marker_data.get("motion_verified") is not True:
                reasons.append("Local motion safety marker is not verified")
        except (OSError, json.JSONDecodeError):
            reasons.append("Local motion safety marker is missing")
        try:
            cfg = self.server.config_path.read_text(errors="replace")
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

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path != "/api/jog":
            self.send_json(404, {"error": "Not found"})
            return
        if self.headers.get("Authorization") != "Bearer " + self.server.motion_token:
            self.send_json(401, {"error": "Enter the session token shown in the server console"})
            return
        try:
            body = self.read_body()
            axis = str(body.get("axis", "")).lower()
            delta = float(body.get("delta", 0))
            if axis not in AXES or not 0 < abs(delta) <= 10:
                raise ValueError("Choose X/Y/Z and a jog distance up to 10 mm")
            status = self.status_data()
            if not status["motion_enabled"]:
                self.send_json(423, {"error": "Motion locked", "reasons": status["motion_lock_reasons"]})
                return
            target = float(status["position"][axis]) + delta
            low, high = AXES[axis]
            if not low <= target <= high:
                raise ValueError(f"Target {axis.upper()} would exceed {low:g}–{high:g} mm travel")
            # Absolute endpoint calculated from fresh Klipper state; no E/solenoid commands.
            script = f"G90\nG1 {axis.upper()}{target:.3f} F300"
            post_json(MOONRAKER + "/printer/gcode/script", {"script": script})
            self.send_json(200, {"accepted": True, "axis": axis.upper(), "target": target})
        except (ValueError, TypeError, KeyError, urllib.error.URLError) as exc:
            self.send_json(400, {"error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a guarded A250 camera/jog page")
    parser.add_argument("--host", default="127.0.0.1", help="bind address; use 0.0.0.0 for LAN access")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--config", type=Path, default=Path("/home/cps/printer_data/config/printer.cfg"))
    parser.add_argument("--safety-marker", type=Path,
                        default=Path("/home/cps/printer_data/config/machine_ui_safety.json"))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), A250Handler)
    server.config_path = args.config
    server.safety_marker = args.safety_marker
    server.motion_token = secrets.token_urlsafe(24)
    print(f"A250 UI at http://{args.host}:{args.port}/", flush=True)
    print(f"Motion session token: {server.motion_token}", flush=True)
    print("Motion remains locked until local safety checks and marker are satisfied.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
