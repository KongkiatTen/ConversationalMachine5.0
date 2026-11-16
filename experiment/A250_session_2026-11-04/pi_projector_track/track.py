"""Track the white bracket in the camera (left eye) and keep a red dot projected
on its center. cam2proj.npy (from calib.py) gives the open-loop mapping; the
projected dot is also found in the camera each frame and a small projector-space
offset is integrated so the dot lands on target even off the calibrated plane.
Stop: sudo systemctl stop bracket-track  (or Ctrl-C)."""
import os
import signal
import time

import cv2
import numpy as np

from fb import FB, snapshot_left

HERE = os.path.dirname(os.path.abspath(__file__))
DOT_R = 14
GAIN = 0.4
MAX_OFF = 120.0

H = np.load(f"{HERE}/cam2proj.npy")
fb = FB()
running = True


def stop(*_):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def to_proj(pt):
    return cv2.perspectiveTransform(np.float32([[pt]]), H)[0, 0]


def find_bracket(img):
    """Largest bright, unsaturated blob that sits on the dark sheet (wall is
    excluded because its surroundings are not dark). Returns (cx, cy, box)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Use max(R,G,B)-ish brightness so the red dot on the bracket stays "bright".
    mask = ((hsv[..., 2] > 150) & (hsv[..., 1] < 90)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    best = None
    for k in range(1, n):
        x, y, w, h, a = stats[k]
        if not (2000 < a < 80000) or w > 450 or h > 300:
            continue
        x0, y0 = max(0, x - 25), max(0, y - 25)
        x1, y1 = min(img.shape[1], x + w + 25), min(img.shape[0], y + h + 25)
        ring = gray[y0:y1, x0:x1][lab[y0:y1, x0:x1] != k]
        if ring.size == 0 or np.median(ring) > 100:
            continue
        if best is None or a > best[4]:
            best = (x, y, w, h, a)
    if best is None:
        return None
    x, y, w, h, _ = best
    return (x + w / 2.0, y + h / 2.0, (x, y, w, h))


def find_holes(img, box):
    """The two round holes in the bracket: dark, near-circular blobs inside its
    bbox (the elongated slot fails the circularity/aspect test). Sorted by x."""
    x, y, w, h = box
    gray = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    holes = []
    for c in cnts:
        a = cv2.contourArea(c)
        per = cv2.arcLength(c, True)
        if not (30 < a < 3000) or per == 0:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        if bx == 0 or by == 0 or bx + bw >= w or by + bh >= h:
            continue  # touches bbox edge = background, not a hole
        circ = 4 * np.pi * a / per ** 2
        if circ < 0.65 or max(bw, bh) / min(bw, bh) > 1.5:
            continue
        mo = cv2.moments(c)
        holes.append((a, mo["m10"] / mo["m00"] + x, mo["m01"] / mo["m00"] + y))
    holes = sorted(holes, reverse=True)[:2]
    if len(holes) < 2:
        return None
    return sorted([np.float32(h[1:]) for h in holes], key=lambda p: p[0])


def find_red_dot(img, near, radius=120):
    b, g, r = [c.astype(np.int16) for c in cv2.split(img)]
    red = np.clip(r - np.maximum(g, b), 0, 255).astype(np.uint8)
    x, y = int(near[0]), int(near[1])
    x0, y0 = max(0, x - radius), max(0, y - radius)
    roi = red[y0:y + radius, x0:x + radius]
    # Dot washes out pink on the white bracket, so red excess is small (~20).
    if roi.size == 0 or roi.max() < 15:
        return None
    m = (roi > roi.max() * 0.5).astype(np.uint8)
    n, _, stats, cents = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (cents[k][0] + x0, cents[k][1] + y0)


SETTLE = 0.35      # s for projector + camera latency
MEASURE_EVERY = 2.0  # s between feedback measurements


def grab_settled():
    time.sleep(SETTLE)
    snapshot_left()  # drop possibly stale frame
    return snapshot_left()


def show_dots(ps):
    frame = fb.blank()
    for p in ps or []:
        cv2.circle(frame, (int(p[0]), int(p[1])), DOT_R, (0, 0, 255), -1)
    fb.show(frame)


def measure_dot(on_img, off_img, near, radius=30):
    """Projected dot = brightest blob in (dot on) - (dot off) near target."""
    diff = np.clip(on_img.astype(np.int16) - off_img.astype(np.int16), 0, 255).max(axis=2)
    diff = cv2.GaussianBlur(diff.astype(np.uint8), (7, 7), 0)
    x, y = int(near[0]), int(near[1])
    x0, y0 = max(0, x - radius), max(0, y - radius)
    roi = diff[y0:y + radius, x0:x + radius]
    if roi.size == 0 or roi.max() < 25:
        return None
    m = (roi > roi.max() * 0.5).astype(np.uint8)
    n, _, stats, cents = cv2.connectedComponentsWithStats(m)
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (cents[k][0] + x0, cents[k][1] + y0)


def main():
    offs = [np.zeros(2, np.float32), np.zeros(2, np.float32)]  # one per hole
    rel = None  # hole positions relative to bracket bbox center, from last ref frame
    last_measure = 0.0
    while running:
        try:
            if time.time() - last_measure >= MEASURE_EVERY:
                # Feedback step: dots off -> reference (find bracket + holes), dots on -> measure.
                last_measure = time.time()
                show_dots(None)
                ref = grab_settled()
                br = find_bracket(ref)
                holes = find_holes(ref, br[2]) if br is not None else None
                if holes is None:
                    print("bracket/holes not found", flush=True)
                    rel = None
                    continue
                c = np.float32(br[:2])
                rel = [h - c for h in holes]
                ps = [to_proj(h) + o for h, o in zip(holes, offs)]
                show_dots(ps)
                on = grab_settled()
                # Tight radius keeps the two dots apart; if a dot drifted far (e.g. a big Z
                # change moved the bed off the calibrated plane), search wider for it.
                dots = [measure_dot(on, ref, h) or measure_dot(on, ref, h, radius=200) for h in holes]
                if dots[0] is not None and dots[0] == dots[1]:
                    dots = [None, None]  # wide search found the same blob for both
                msg = []
                for i, (h, d) in enumerate(zip(holes, dots)):
                    if d is not None:
                        offs[i] = np.clip(offs[i] + GAIN * (to_proj(h) - to_proj(d)), -MAX_OFF, MAX_OFF)
                        msg.append(f"hole{i} ({h[0]:.0f},{h[1]:.0f}) err {np.hypot(*(np.float32(d) - h)):.1f}px")
                    else:
                        msg.append(f"hole{i} ({h[0]:.0f},{h[1]:.0f}) dot none")
                show_dots([to_proj(h) + o for h, o in zip(holes, offs)])
                print(" | ".join(msg), flush=True)
                vis = on.copy()
                x, y, w, h = br[2]
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
                for hp, d in zip(holes, dots):
                    cv2.drawMarker(vis, (int(hp[0]), int(hp[1])), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
                    if d is not None:
                        cv2.circle(vis, (int(d[0]), int(d[1])), 8, (255, 0, 255), 2)
                cv2.imwrite(f"{HERE}/track_debug.jpg", vis)
            elif rel is not None:
                # Between measurements: follow bracket motion; holes ride along with its bbox.
                br = find_bracket(snapshot_left())
                if br is not None:
                    c = np.float32(br[:2])
                    show_dots([to_proj(c + r) + o for r, o in zip(rel, offs)])
            else:
                time.sleep(0.1)
        except Exception as e:
            print("error:", e, flush=True)
            time.sleep(0.5)
    fb.show(fb.blank())
    print("stopped", flush=True)


if __name__ == "__main__":
    main()
