# A250 report notes and machine handoff

Prepared 2026-11-16 (Asia/Bangkok) from the A250 experiment folder, Pi inspection, project files, and user-provided photos. This is a working source note for a later report, not a final technical validation.

## Machine identity and current state

- Hostname: `A250`; private LAN address observed: `192.168.31.187` (`wlan0`). SSH account used: `cps`. **Credentials are intentionally not stored here.**
- Host platform in machine notes: Seeed reComputer AI R2140-12 with Raspberry Pi 5 16 GB and Hailo-8 accelerator.
- Klipper and Moonraker services were active; printer info reported Klipper `ready`, print state `standby`.
- Webcam/uStreamer active on port 8080, 2560×720 at 30 fps; snapshot endpoint returned HTTP 200. Browser preview: `http://192.168.31.187:8080/`.
- Projector was initially disconnected, then later detected on HDMI-A-1 at 1280×720 around 59.97 Hz. HDMI-A-2 remained disconnected. `/dev/fb0` was present when it was detected.
- Tic-tac-toe was started briefly, then stopped at user request. Its status file read `stopped`; its stop handler clears the framebuffer.
- `paint-display` remains disabled/inactive; `paint-server` remains active.
- A LAN machine console was installed at `/home/cps/A250/machine_web`, port 8766. URL: `http://192.168.31.187:8766/`. It serves live camera, status, and guarded jog UI. Server process was started with `nohup` (PID 2097 at last check). GET `/` returned HTTP 200; `/api/camera-check` reported available; API status returned connected.
- The web UI reports motion locked. It requires a local safety marker, cleared configuration warnings, all axes homed, idle state, valid cool temperature, and positions within travel limits before enabling jog. No token or credentials were saved in this note.
- No XYZ movement was made during this session. Fresh Klipper query reported `homed_axes` empty, coordinate values all zero (untrusted while unhomed), print `standby`, and extruder reading about 260 °C with target 0 °C. Bed sensor returned null.
- Current active `printer.cfg` comments say homing endstop signals may not work until the G431 emulates Snapmaker CAN limits, motor direction/endstop polarity are unverified, and the machine is not safe to move. Sensor configuration is also marked TODO/unverified. Do not home, jog, set a false kinematic position, or use extrusion/solenoids until these issues are resolved and verified at the machine.

## Controller and wiring notes

Machine docs: `/home/cps/A250/klipper/A250_MACHINE.md`, `/home/cps/A250/PINMAP_H723.md`, `/home/cps/printer_data/config/printer.cfg`, `/home/cps/A250/SNAPMAKER_CAN.md`.

- CrossTechControllerV1 custom dual-MCU board: STM32H723 motion MCU and STM32G431 gateway MCU.
- X step/dir/enable: `PD3` / `PD4` / `PD6`.
- Y shared step/dir/enable: `PA8` / `PA15` / `PD1`, driving both Y modules.
- Z shared step/dir/enable: `PE3` / `PE2` / `PE0`, driving both Z modules.
- Limit signal pins: X `PC1`, Y `PC3`, Z `PC0`; machine notes say G431/CAN-derived endstop reporting was not functioning/verified.
- Notes call out 74LVC245 logic buffers and MCP2542FD CAN transceiver; CAN uses PB8/PB9 and is configured for 500 kbps.
- Five Snapmaker linear modules: one X, two Y, two Z. Notes/config say X/Y lead 20 mm, Z lead 8 mm, TMC2209 drivers; each Y and Z pair shares signals.
- Config coordinate range is 0–262 mm; axes home at max when working, with a 2 mm backoff. This describes configuration, not a verified safe move.
- Older config references RP2040 CAN hardware; current config references RP2350 12-channel solenoid board on USB serial. Current USB inventory did not establish the RP2350 board as connected.
- Config documents syringe pump end-effector, not a filament extruder. Heater sensor type is marked unverified.

## Camera, projector, and photo observations

- Camera USB ID observed: `0bda:9732`, enumerated as “USB Camera”; photos look like a dual-optic camera assembly. Exact retail/model datasheet could not be identified.
- Experiment code uses 2560×720 stereo frames and takes the left half (1280×720) as the left camera view.
- Projector code writes to `/dev/fb0`; projector model is unknown.
- Four latest Downloads photos reviewed: `IMG_0351.jpg` shows an underside green PCB and connector/cable row, markings blurred; `IMG_0350.jpg` shows machine frame/module detail with a fine strand/wire end visible near a yellow lead, needs physical inspection with power off; `IMG_0349.jpg` appears to show the dual-optic camera with USB-C but no readable label; `IMG_0348.jpg` is a broad setup view without readable part numbers.

## Experiment on 2026-11-04

Local session record: `SESSION_LOG.md`.

- Camera stream verified; initial frames were black until the camera was uncovered.
- Projector framebuffer crash issue: old display script assumed 1280×720 while HDMI-A-2 ran 1024×768, mmap was too large and caused a kernel oops. Script was changed to read framebuffer geometry. Projector worked after moving cable to HDMI-A-1, forced to 1280×720. `paint-display` was subsequently disabled.
- Camera/projector calibration fit 8 homography inliers, mean error 1.37 px; matrix saved as `cam2proj.npy`.
- Bracket tracking used two projected dots with feedback, about 1 px reported error; occlusion by toolhead could block projector beam.
- Documented viewing pose was X0 Y190 Z260; bed touch at Z13 was user-confirmed then. This is historical and does not establish current homing/position.
- Tic-tac-toe code supports two-player fingertip input; X magenta, O green. Earlier single-player minimax version was replaced.
- `outline.py` segments objects on the dark bed sheet and projects cyan contours; contours were also frozen to `outline_frozen.npy`.

## Python package inventory

Read/parsed 28 Python source files under `/home/cps/A250`, excluding virtual environments. This does not include Python sources in separate vendor trees such as `/home/cps/klipper` or `/home/cps/moonraker`.

Third-party or target-runtime modules referenced:

- `cv2` — OpenCV (typically installed as `opencv-python`); camera vision, calibration, tracking, labels.
- `numpy` — image arrays, matrix/calibration math, framebuffer conversion.
- `PIL` — Pillow; framebuffer drawing.
- `websockets` — projector paint display websocket client.
- `serial` — pyserial; Klipper endstop/solenoid helpers.
- `requests` — rangefinder helper.
- `CAN` — MicroPython CAN module used by the archived RP2040 firmware; not a normal Pi pip dependency.
- `machine`, `rp2` — MicroPython built-ins for RP2040.
- `mcu`, `pins` — Klipper internal modules; `fb`, `finger`, `calibration`, `DCMotorDriver`, and `GP2Y0E02B` are project-local modules.
- `machine_web/server.py` uses Flask for the web routes and Python standard-library modules for Moonraker requests and safety checks. Flask is declared in `machine_web/requirements.txt`.

Newest pre-existing experiment script inspected: `/home/cps/A250/projector_track/parts.py`. It labels an archived board photo with components and estimated dimensions, and by default can project the labels. Use `noproject` to avoid touching projector output.

## Datasheet and reference links

- Seeed reComputer AI R2140-12: https://files.seeedstudio.com/Bazaar/product_pdf/114993627.pdf
- Raspberry Pi 5 product brief: https://pip-assets.raspberrypi.com/categories/892-raspberry-pi-5/documents/RP-008348-DS-10-raspberry-pi-5-product-brief.pdf
- STM32H723 datasheet: https://www.st.com/resource/en/datasheet/stm32h723vg.pdf
- STM32G431 datasheet: https://www.st.com/resource/en/datasheet/stm32g431cb.pdf
- MCP2542FD datasheet: https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP2542FD-MCP2542WFD-4WFD-Data-Sheet-DS20005514C.pdf
- SN74LVC245A family reference (buffer suffix/manufacturer unverified): https://www.ti.com/lit/ds/symlink/sn74lvc245a.pdf
- TMC2209 datasheet: https://www.analog.com/media/en/technical-documentation/data-sheets/TMC2209_datasheet_rev1.09.pdf
- Snapmaker linear module information: https://shop.snapmaker.com/products/linear-module-with-tmc2209-a350t-f350
- RP2350 documentation: https://pip.raspberrypi.com/categories/1214-rp2350
- Snapmaker A250 manual: https://wiki.snapmaker.com/en/Snapmaker_2/manual

Custom controller boards and exact camera/projector part models have no identified public datasheets. See the machine docs listed above for board-specific pin references.

## Term Project – 2570 brief

File: `~/Downloads/Term Project - 2570.pdf`. One-page brief; assignment date Monday, September 7, 2026; individual project; due “a final week.” Design a small mechatronics system combining a mechanical system, interface electronics, Raspberry Pi Pico, and Python program.

Report section [40 marks]: rationale 2.5; background/related work 2.5; overall system diagram 10; commented Python program 10; parts/specifications/prices 5; demonstration clip 10. The source has duplicated/misaligned numbering around the first two points.

Technical requirements [60 marks]: select FOUR of TWELVE: OS (Home Automation, 3D Printing, “Clea,” Digital Signage); Codex/ChatGPT or Claude; link to Google/Amazon/Azure/ThingSpeak/Netpie; simulation/digital twin/Simscape; select two Python package choices (ROS, VisionWorks/OpenCV/Mediapipe, TensorFlow, Flask/SocketIO, MongoDB/SQLAlchemy, “Ask for approval”); user-friendly/mobile/automatic; robustness/reliability/precision; MQTT/REST API/IoT; multiple threads/FreeRTOS; developed with PIO on Pico; scientific result; Raspberry Pi only. Preserve “Clea” and “Ask for approval” as transcribed; wording appears unusual in source.
