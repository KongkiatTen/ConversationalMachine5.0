# Conveyor5.0 — A250 Mechatronics Project

This project uses a Snapmaker A250 as a programmable mechatronics platform. A Raspberry Pi 5 runs the Python vision and experiment software, a stereo USB camera observes the work area, and an HDMI projector displays feedback on the bed. Klipper/Moonraker and a custom STM32H723/STM32G431 controller connect the software to the machine electronics.

The course brief calls for a small system combining mechanics, interface electronics, a Raspberry Pi Pico, and Python. This implementation uses a Raspberry Pi 5 rather than a Pico; that platform difference should be addressed in the final report.

## Main components

- **Snapmaker A250:** provides the XYZ motion platform and work area.
- **Raspberry Pi 5:** runs the Python experiments, vision processing, and local web console.
- **Stereo USB camera:** captures the work area for calibration, object detection, and tracking.
- **HDMI projector:** displays calibration patterns, markers, outlines, and interactive graphics on the bed.
- **Custom dual-MCU controller:** STM32H723 handles motion signals while STM32G431 provides the gateway path to the machine interface.
- **Klipper and Moonraker:** provide the machine-control software interface used by the Pi.

## Project work

- Calibrate camera-to-projector alignment and map image coordinates to the work area.
- Detect and track objects, including a machine bracket, and project markers or object outlines.
- Demonstrate fingertip-controlled projected tic-tac-toe.
- Label components in images and estimate their dimensions.
- Provide a local web page for camera preview and machine status, with guarded XYZ jog controls.

Past experiments reported 8 homography inliers and 1.37 px mean calibration error, and about 1 px bracket-tracking alignment error. These are historical measurements, not current motion-safety certification.

## System wiring overview

![A250 wiring diagram](experiment/A250_session_2026-11-04/wiring/A250_wiring_diagram.svg)

This is a system-level diagram based on available notes. Dashed connections are unverified; power distribution, connector-level harness details, and some component models remain undocumented. See the [A250 experiment notes](experiment/A250_session_2026-11-04/A250_REPORT_NOTES.md).

## Course brief and report checklist

The source assignment brief is included at [`docs/Term Project - 2570.pdf`](docs/Term%20Project%20-%202570.pdf). It requests:

- Project rationale and background/related work.
- An overall diagram showing the mechanical system, processor, and interface circuits.
- Commented Python program(s).
- A clip demonstrating the technical features.

The brief also asks for four technical requirements selected from its list. Evidence in this project maps to 3D-printing hardware, the OpenCV and NumPy Python packages, quantitative calibration/tracking results, and Raspberry Pi computing. The final report should identify these four choices explicitly and support each with project evidence. The local web console uses Python's standard library; it does not use Flask/SocketIO. The assignment mentions a Pico, while the project platform is a Pi 5.

## Repository contents

- [`experiment/A250_session_2026-11-04/`](experiment/A250_session_2026-11-04/): experiment code, notes, logs, evidence, web console, and wiring diagram.
- [`experiment/A250_session_2026-11-04/SESSION_LOG.md`](experiment/A250_session_2026-11-04/SESSION_LOG.md): experiment sequence and observations.
- [`experiment/A250_session_2026-11-04/A250_REPORT_NOTES.md`](experiment/A250_session_2026-11-04/A250_REPORT_NOTES.md): hardware inventory, wiring notes, references, and report source material.
- [`docs/Term Project - 2570.pdf`](docs/Term%20Project%20-%202570.pdf): original assignment brief.

## Safety status

Machine movement remains locked pending verification of endstop reporting, motor direction, and the temperature sensor. The last recorded state had unhomed axes and an implausible extruder temperature reading. Do not treat historical coordinates or experiment results as evidence that motion is currently safe.
