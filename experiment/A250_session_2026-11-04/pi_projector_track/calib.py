"""Camera(left eye) -> projector homography.
Projects one white dot at a time on black, finds it in the camera by
differencing against an all-black frame, fits H with RANSAC.
Saves cam2proj.npy + debug images in this folder."""
import os
import time

import cv2
import numpy as np

from fb import FB, snapshot_left

HERE = os.path.dirname(os.path.abspath(__file__))
SETTLE = 0.8  # s for projector + camera to catch up


def grab(fb, frame):
    fb.show(frame)
    time.sleep(SETTLE)
    snapshot_left()  # discard possibly stale frame
    return snapshot_left()


def main():
    fb = FB()
    W, H = fb.W, fb.H
    print("fb", W, H)
    dark = cv2.GaussianBlur(grab(fb, fb.blank()), (5, 5), 0).astype(np.int16)
    cv2.imwrite(f"{HERE}/calib_dark.jpg", dark.astype(np.uint8))

    pts_p, pts_c = [], []
    cols, rows = 5, 4
    for j in range(rows):
        for i in range(cols):
            px = int(W * (0.1 + 0.8 * i / (cols - 1)))
            py = int(H * (0.1 + 0.8 * j / (rows - 1)))
            f = fb.blank()
            cv2.circle(f, (px, py), 18, (255, 255, 255), -1)
            cam = cv2.GaussianBlur(grab(fb, f), (5, 5), 0).astype(np.int16)
            diff = np.clip(cam - dark, 0, 255).astype(np.uint8).max(axis=2)
            peak = int(diff.max())
            if peak < 40:
                print(f"proj ({px},{py}): not seen (peak {peak})")
                continue
            _, m = cv2.threshold(diff, peak * 0.5, 255, cv2.THRESH_BINARY)
            n, lab, stats, cents = cv2.connectedComponentsWithStats(m)
            k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            cx, cy = cents[k]
            print(f"proj ({px},{py}) -> cam ({cx:.1f},{cy:.1f}) peak {peak} area {stats[k, 4]}")
            pts_p.append((px, py))
            pts_c.append((cx, cy))
            if i == 0 and j == 0:
                cv2.imwrite(f"{HERE}/calib_diff0.jpg", diff)

    fb.show(fb.blank())
    print("found", len(pts_c), "of", cols * rows)
    if len(pts_c) < 4:
        print("FAIL: projector light not visible in camera view")
        return
    Hm, inl = cv2.findHomography(np.float32(pts_c), np.float32(pts_p), cv2.RANSAC, 6.0)
    inl = inl.ravel().astype(bool)
    proj = cv2.perspectiveTransform(np.float32(pts_c)[None], Hm)[0]
    err = np.linalg.norm(proj - np.float32(pts_p), axis=1)
    print(f"inliers {inl.sum()}/{len(inl)}  reproj err mean {err[inl].mean():.2f}px max {err[inl].max():.2f}px")
    np.save(f"{HERE}/cam2proj.npy", Hm)
    vis = dark.astype(np.uint8).copy()
    for c, ok in zip(pts_c, inl):
        cv2.circle(vis, (int(c[0]), int(c[1])), 8, (0, 255, 0) if ok else (0, 0, 255), 2)
    cv2.imwrite(f"{HERE}/calib_points.jpg", vis)
    print("saved cam2proj.npy")


if __name__ == "__main__":
    main()
