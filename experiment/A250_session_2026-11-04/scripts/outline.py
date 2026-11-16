"""Find objects on the dark bed sheet (left eye) and project their outlines back
onto them via cam2proj.npy. Each cycle blanks the projector, grabs a clean
frame, segments, then shows outlines for HOLD seconds (so the projected light
never feeds back into the segmentation).
Usage: outline.py            -> live loop (stop: sudo systemctl stop outline)
       outline.py test IMG   -> segment a saved image, write outline_test.jpg"""
import os
import signal
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# Dark sheet area at the viewing pose, below the printed logo/icons strip.
RX0, RY0, RX1, RY1 = 330, 60, 1080, 660
MIN_AREA = 600
HOLD = 1.0
SETTLE = 0.35
LINE_COL = (255, 255, 0)  # cyan
LINE_W = 4


def segment(img):
    roi = img[RY0:RY1, RX0:RX1]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.int16)
    # Local background (sheet) brightness; objects stand out from it.
    bg = cv2.medianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), 41).astype(np.int16)
    bright = (gray - bg) > 35
    colored = (s > 45) & (v > 70)
    m = (bright | colored).astype(np.uint8) * 255
    # Grid lines are 1-3 px thin and unsaturated: an opening removes them.
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((4, 4), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cnts:
        if cv2.contourArea(c) < MIN_AREA:
            continue
        x, y, w, hh = cv2.boundingRect(c)
        # Skip blobs hugging the ROI edge (frame/rails, not objects on the sheet).
        if x <= 1 or y <= 1 or x + w >= m.shape[1] - 1 or y + hh >= m.shape[0] - 1:
            continue
        out.append(c + np.array([[RX0, RY0]]))
    return out, m


def draw(img, cnts):
    vis = img.copy()
    cv2.rectangle(vis, (RX0, RY0), (RX1, RY1), (120, 120, 120), 1)
    cv2.drawContours(vis, cnts, -1, LINE_COL, 2)
    return vis


def live():
    from fb import FB, snapshot_left
    H = np.load(f"{HERE}/cam2proj.npy")
    fb = FB()
    run = [True]
    signal.signal(signal.SIGTERM, lambda *_: run.__setitem__(0, False))
    signal.signal(signal.SIGINT, lambda *_: run.__setitem__(0, False))
    n = 0
    while run[0]:
        try:
            fb.show(fb.blank())
            time.sleep(SETTLE)
            snapshot_left()
            img = snapshot_left()
            cnts, _ = segment(img)
            cam = np.zeros((720, 1280, 3), np.uint8)
            cv2.drawContours(cam, cnts, -1, LINE_COL, LINE_W)
            fb.show(cv2.warpPerspective(cam, H, (fb.W, fb.H)))
            if n % 5 == 0:
                print(f"{len(cnts)} object(s), areas {[int(cv2.contourArea(c)) for c in cnts]}", flush=True)
                cv2.imwrite(f"{HERE}/outline_debug.jpg", draw(img, cnts))
            n += 1
            time.sleep(HOLD)
        except Exception as e:
            print("error:", e, flush=True)
            time.sleep(0.5)
    fb.show(fb.blank())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # Freeze: one clean capture, project outlines, exit leaving them on screen.
        from fb import FB, snapshot_left
        H = np.load(f"{HERE}/cam2proj.npy")
        fb = FB()
        fb.show(fb.blank())
        time.sleep(SETTLE)
        snapshot_left()
        img = snapshot_left()
        cnts, _ = segment(img)
        cam = np.zeros((720, 1280, 3), np.uint8)
        cv2.drawContours(cam, cnts, -1, LINE_COL, LINE_W)
        fb.show(cv2.warpPerspective(cam, H, (fb.W, fb.H)))
        cv2.imwrite(f"{HERE}/outline_frozen.jpg", draw(img, cnts))
        np.save(f"{HERE}/outline_frozen.npy", np.array([c.reshape(-1, 2) for c in cnts], dtype=object), allow_pickle=True)
        print(f"frozen: {len(cnts)} object(s), areas {[int(cv2.contourArea(c)) for c in cnts]}")
    elif len(sys.argv) > 2 and sys.argv[1] == "test":
        img = cv2.imread(sys.argv[2])
        img = img[:, :1280] if img.shape[1] > 1280 else img
        cnts, m = segment(img)
        print(len(cnts), "object(s), areas", [int(cv2.contourArea(c)) for c in cnts])
        cv2.imwrite("outline_test.jpg", draw(img, cnts))
        cv2.imwrite("outline_mask.jpg", m)
    else:
        live()
