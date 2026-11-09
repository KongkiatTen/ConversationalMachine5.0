"""Fingertip finder: skin-colour blob inside the board ROI; tip = blob pixel
farthest from where the blob crosses the ROI border (where the arm comes in)."""
import cv2
import numpy as np

# ROI in left-eye camera pixels: board plus margin, still on the dark sheet.
RX0, RY0, RX1, RY1 = 300, 0, 1110, 480
MIN_AREA = 2500


def skin_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # Skin: red-orange hue, moderate saturation (projected red X is far more saturated).
    m = (((h <= 25) | (h >= 170)) & (s >= 35) & (s <= 175) & (v >= 70)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    return m


def find_fingertip(img):
    """Returns ((x, y) or None, hand_present: bool)."""
    roi = img[RY0:RY1, RX0:RX1]
    m = skin_mask(roi)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None, False
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[k, cv2.CC_STAT_AREA] < MIN_AREA:
        return None, False
    ys, xs = np.where(lab == k)
    h, w = m.shape
    edge = (xs <= 1) | (xs >= w - 2) | (ys <= 1) | (ys >= h - 2)
    if edge.any():
        ex, ey = xs[edge].mean(), ys[edge].mean()
    else:  # whole hand inside ROI: assume arm comes from the bottom-right (front of machine)
        ex, ey = w, h
    d = (xs - ex) ** 2 + (ys - ey) ** 2
    far = d >= np.percentile(d, 99.7)  # average the farthest few pixels for stability
    return (float(xs[far].mean()) + RX0, float(ys[far].mean()) + RY0), True


if __name__ == "__main__":
    import sys
    img = cv2.imread(sys.argv[1])
    if img.shape[1] > 1280:
        img = img[:, :1280]
    tip, present = find_fingertip(img)
    print("present", present, "tip", tip, "skin px in ROI", int((skin_mask(img[RY0:RY1, RX0:RX1]) > 0).sum()))
    vis = img.copy()
    cv2.rectangle(vis, (RX0, RY0), (RX1, RY1), (255, 255, 0), 2)
    if tip:
        cv2.drawMarker(vis, (int(tip[0]), int(tip[1])), (255, 0, 255), cv2.MARKER_CROSS, 40, 3)
    cv2.imwrite(sys.argv[2] if len(sys.argv) > 2 else "finger_vis.jpg", vis)
