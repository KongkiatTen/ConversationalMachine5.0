"""Minimal /dev/fb0 writer (RGB565). Geometry read from sysfs so it follows
whatever mode the projector came up in (1024x768 or 1280x720)."""
import mmap
import os
import urllib.request

import cv2
import numpy as np

SYS = "/sys/class/graphics/fb0"
SNAP_URL = "http://127.0.0.1:8080/snapshot"


def _read(name):
    with open(f"{SYS}/{name}") as f:
        return f.read().strip()


class FB:
    def __init__(self, dev="/dev/fb0"):
        self.W, self.H = map(int, _read("virtual_size").split(","))
        self.stride = int(_read("stride"))
        assert int(_read("bits_per_pixel")) == 16, "expected RGB565"
        self.fd = os.open(dev, os.O_RDWR)
        self.mm = mmap.mmap(self.fd, self.stride * self.H, mmap.MAP_SHARED,
                            mmap.PROT_READ | mmap.PROT_WRITE)
        self.buf = np.frombuffer(self.mm, dtype="<u2").reshape(self.H, self.stride // 2)

    def blank(self):
        return np.zeros((self.H, self.W, 3), np.uint8)

    def show(self, bgr):
        a = bgr.astype(np.uint16)
        b, g, r = a[..., 0] >> 3, a[..., 1] >> 2, a[..., 2] >> 3
        self.buf[:, :self.W] = (r << 11) | (g << 5) | b
        self.mm.flush()


def snapshot_left(timeout=5):
    """Left eye (x 0-1279) of the 2560x720 stereo snapshot, BGR."""
    data = urllib.request.urlopen(SNAP_URL, timeout=timeout).read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return img[:, : img.shape[1] // 2]
