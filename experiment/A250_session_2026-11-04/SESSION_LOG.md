# A250 session log — 2026-11-04

Pi 5 `A250` at 192.168.31.187 (user `cps`): Klipper + Moonraker (:7125), uStreamer stereo webcam (:8080, 2560x720, left eye = x 0-1279), projector on HDMI, paint-server (:8765).

## What was done (in order)

1. **Connected over SSH** and listed the services. Klipper, Moonraker, nginx, webcam, webcam-power and paint-server were running. paint-display was crash-looping.
2. **Webcam**: the stream worked, but the frames were black because the camera was covered. It showed the bed once uncovered.
3. **Projector fault**:
   - `fb_paint_display.py` hardcoded 1280x720 (stride 2560).
   - The projector was on HDMI-A-2. That port has no forced mode and the projector's EDID is all zeroes, so it came up at 1024x768.
   - The script mmapped too much memory and caused a kernel oops in `fb_mmap`. A D-state process then blocked `/dev/fb0`.
   - Fix part 1: patched the script to read the fb geometry from sysfs (backup `fb_paint_display.py.bak`), disabled `paint-display`, and rebooted.
   - Fix part 2: the projector still showed nothing at 1024x768. The user moved the cable to HDMI-A-1, which `cmdline.txt` forces to 1280x720. After a reboot the projector worked.
4. **YouTube on the projector**: not done. Installing yt-dlp was blocked by the permission policy, and VLC's youtube.lua is outdated.
5. **Camera-to-projector calibration** (`calib.py`): projected 20 dots and found them in the camera. Fit a homography with 8 inliers on the bed plane, mean error 1.37 px. Saved as `cam2proj.npy`.
6. **Bracket tracking** (`track.py`, unit `bracket-track`):
   - First version: one red dot on the bracket.
   - Then two dots, one on each round hole.
   - Feedback: dot-off and dot-on frames are differenced to measure each dot, and a per-dot offset is corrected every 2 s. Error about 1 px.
   - The tracker stayed on target through Y sweeps and Z changes. It failed when the toolhead (X 50-100) blocked the projector beam.
7. **Axes worked out**:
   - X: toolhead; higher X moves toward the image left. X=0 and X=260 are out of view.
   - Y: bed; higher Y moves toward the image top.
   - Z: gantry carrying the toolhead and camera; lower Z zooms in.
   - Home/viewing pose: X0 Y190 Z260.
8. **Bed touch**: the needle touches the bed sheet at **Z=13**, at X30 Y200 (user confirmed).
9. **Needle into the right bracket hole**:
   - The camera calibration put the hole at X59.2 Y156.5. I hovered at Z19.
   - The user said to correct by -Y 20 mm, which gives Y136.5.
   - The descent was interrupted by the user, then the printer went home.
   - Rule from the user: always lift Z before any XY move.
10. **Tic-tac-toe** (`tictactoe.py`, unit `tictactoe`):
    - First version: single player using the bracket as the piece, against a minimax AI.
    - Then two players with fingertip input (`finger.py`, skin mask). X is magenta and O is green; red is avoided because it looks like skin.
11. **Object outline** (`outline.py`, unit `outline`):
    - Segments objects on the dark sheet and projects a cyan outline onto them live, with a blank-and-capture cycle about once a second.
    - Then froze it (`outline.py once`; contours in `outline_frozen.npy`), then cleared the projector.

## State at end

- Printer at X0 Y190 Z260 and homed. The projector is blank.
- `paint-display` is still **disabled**. Re-enable it with `sudo systemctl enable --now paint-display`.
- Scripts on the Pi are in `~/A250/projector_track/`. Run them with `~/A250/camera_mapping/.venv/bin/python`.

## Folder contents

- `snapshots/`: webcam frames and debug images taken during the session.
- `pi_projector_track/`: full copy of `~/A250/projector_track` from the Pi (scripts, calibration, debug images).
- `scripts/`: local copies of the scripts.
- `logs/pi_journal_today.log`: today's journal for bracket-track, tictactoe, outline, paint-display, paint-server, webcam, klipper, moonraker, plus the kernel HDMI/DRM/oops lines.
- `logs/klippy_tail.log`, `logs/moonraker_tail.log`: the last part of the Klipper and Moonraker logs.
