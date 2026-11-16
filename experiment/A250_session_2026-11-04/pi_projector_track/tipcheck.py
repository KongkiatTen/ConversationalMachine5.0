"""Find the green needle tip and the right-most round bracket hole in the left
eye of a stereo snapshot; print both pixels and the gap. Saves tipcheck_<tag>.jpg."""
import sys

import cv2
import numpy as np

from fb import snapshot_left

tag = sys.argv[1] if len(sys.argv) > 1 else "x"
img = snapshot_left(timeout=15)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Needle tip: green blob (hue ~30-60 in OpenCV units, saturated).
g = cv2.inRange(hsv, (28, 80, 80), (65, 255, 255))
g = cv2.morphologyEx(g, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
n, lab, st, ce = cv2.connectedComponentsWithStats(g)
tip = None
if n > 1:
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    ys, xs = np.where(lab == k)
    # Tip = the green pixel farthest from the syringe body. Body sits to the
    # right/down of the tip in this view, so take the left-most green points.
    sel = xs <= xs.min() + 4
    tip = (float(xs[sel].mean()), float(ys[sel].mean()))

# Holes: dark, round blobs fully inside a white region.
white = ((hsv[..., 2] > 150) & (hsv[..., 1] < 90)).astype(np.uint8) * 255
white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
dark = ((gray < 110) & (white > 0)).astype(np.uint8) * 255
cnts, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
holes = []
for c in cnts:
    a = cv2.contourArea(c)
    per = cv2.arcLength(c, True)
    if a < 30 or per == 0:
        continue
    bx, by, bw, bh = cv2.boundingRect(c)
    if 4 * np.pi * a / per ** 2 < 0.65 or max(bw, bh) / max(1, min(bw, bh)) > 1.5:
        continue
    m = cv2.moments(c)
    holes.append((m["m10"] / m["m00"], m["m01"] / m["m00"], a))
holes.sort()
hole = holes[-1] if holes else None

vis = img.copy()
if tip:
    cv2.drawMarker(vis, (int(tip[0]), int(tip[1])), (255, 0, 255), cv2.MARKER_CROSS, 25, 2)
for h in holes:
    cv2.circle(vis, (int(h[0]), int(h[1])), 12, (0, 255, 0) if h is hole else (0, 160, 0), 2)
cv2.imwrite(f"tipcheck_{tag}.jpg", vis)
print("tip", None if tip is None else tuple(round(v, 1) for v in tip),
      "holes", [(round(h[0], 1), round(h[1], 1), int(h[2])) for h in holes],
      "gap", None if not (tip and hole) else (round(hole[0] - tip[0], 1), round(hole[1] - tip[1], 1)))
