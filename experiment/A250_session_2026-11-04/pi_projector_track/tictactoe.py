"""Projected tic-tac-toe on the A250 bed.

Two players, X (magenta) and O (green), alternating; X starts.
Point a finger at an empty cell and hold still ~1 s to place the current mark,
then take the hand away. A bar under the board shows whose turn it is.
(Red is avoided: projected red on the dark sheet looks like skin to finger.py.)
Board is defined in camera (left eye) pixels and warped to the projector with
cam2proj.npy, so it lines up with what the camera sees at the viewing pose
X=0 Y=190 Z=260. Status is written to ttt_status.txt.
Stop: sudo systemctl stop tictactoe
"""
import os
import signal
import time

import cv2
import numpy as np

from fb import FB, snapshot_left
from finger import find_fingertip

HERE = os.path.dirname(os.path.abspath(__file__))
H = np.load(f"{HERE}/cam2proj.npy")
fb = FB()

# Board rectangle in camera pixels (on the dark bed sheet at the viewing pose).
BX0, BY0, BX1, BY1 = 360, 20, 1050, 440
CW, CH = (BX1 - BX0) / 3, (BY1 - BY0) / 3
HOLD_S = 1.0
GONE_S = 0.5  # hand must be gone this long before the next move
COL = {"X": (255, 0, 255), "O": (0, 255, 0)}
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

running = True


def stop(*_):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def status(msg):
    print(msg, flush=True)
    with open(f"{HERE}/ttt_status.txt", "w") as f:
        f.write(msg + "\n")


# ---------- game logic ----------
def winner(b):
    for a, c, d in LINES:
        if b[a] and b[a] == b[c] == b[d]:
            return b[a], (a, c, d)
    return (None, None) if None in b else ("draw", None)


def minimax(b, player):
    w, _ = winner(b)
    if w == "O":
        return 1, None
    if w == "X":
        return -1, None
    if w == "draw":
        return 0, None
    best = (-2, None) if player == "O" else (2, None)
    for i in range(9):
        if b[i] is None:
            b[i] = player
            s, _ = minimax(b, "X" if player == "O" else "O")
            b[i] = None
            if (player == "O" and s > best[0]) or (player == "X" and s < best[0]):
                best = (s, i)
    return best


def ai_move(b):
    # Prefer centre/corners on ties for a natural opening.
    order = [4, 0, 2, 6, 8, 1, 3, 5, 7]
    best_s, best_i = -2, None
    for i in order:
        if b[i] is None:
            b[i] = "O"
            s, _ = minimax(b, "X")
            b[i] = None
            if s > best_s:
                best_s, best_i = s, i
    return best_i


# ---------- vision ----------
def find_bracket(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
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
    return x + w / 2.0, y + h / 2.0


def cell_of(pt):
    if pt is None:
        return None
    cx, cy = pt
    if not (BX0 <= cx < BX1 and BY0 <= cy < BY1):
        return None
    return int((cy - BY0) // CH) * 3 + int((cx - BX0) // CW)


def cell_center(i):
    r, c = divmod(i, 3)
    return BX0 + (c + 0.5) * CW, BY0 + (r + 0.5) * CH


# ---------- drawing (camera space, then warp to projector) ----------
def render(board, win_line=None, flash=False, turn=None):
    cam = np.zeros((720, 1280, 3), np.uint8)
    grid = (200, 60, 0)  # blue-ish, dim enough not to look like the white bracket
    for k in (1, 2):
        x = int(BX0 + k * CW)
        y = int(BY0 + k * CH)
        cv2.line(cam, (x, BY0), (x, BY1), grid, 6)
        cv2.line(cam, (BX0, y), (BX1, y), grid, 6)
    s = int(min(CW, CH) * 0.32)
    for i, v in enumerate(board):
        cx, cy = map(int, cell_center(i))
        if v == "X":
            cv2.line(cam, (cx - s, cy - s), (cx + s, cy + s), COL["X"], 12)
            cv2.line(cam, (cx - s, cy + s), (cx + s, cy - s), COL["X"], 12)
        elif v == "O":
            cv2.circle(cam, (cx, cy), s, COL["O"], 12)
    if win_line and not flash:
        a, b = cell_center(win_line[0]), cell_center(win_line[2])
        cv2.line(cam, tuple(map(int, a)), tuple(map(int, b)), (0, 255, 255), 16)
    if turn:
        cv2.rectangle(cam, (BX0, BY1 + 8), (BX1, BY1 + 22), COL[turn], -1)
    out = cv2.warpPerspective(cam, H, (fb.W, fb.H), flags=cv2.INTER_LINEAR)
    fb.show(out)


def main():
    starter = "X"
    while running:
        board = [None] * 9
        turn = starter
        render(board, turn=turn)
        status(f"new game: {turn} to move - point at a cell and hold ~1 s")
        last_cell, since = None, time.time()
        gone_since = None
        armed = False  # becomes True once no hand has been seen for GONE_S
        result = None
        while running and result is None:
            try:
                tip, present = find_fingertip(snapshot_left())
            except Exception as e:
                status(f"camera error: {e}")
                time.sleep(0.5)
                continue
            now = time.time()
            if not present:
                gone_since = gone_since or now
                if now - gone_since >= GONE_S:
                    armed = True
                last_cell = None
                continue
            gone_since = None
            c = cell_of(tip)
            if c != last_cell:
                last_cell, since = c, now
                continue
            if not armed or c is None or board[c] is not None or now - since < HOLD_S:
                continue
            board[c] = turn
            armed = False
            w, line = winner(board)
            if w is not None:
                result = (w, line)
                render(board)
                status(f"{turn} in cell {c + 1}")
                break
            turn = "O" if turn == "X" else "X"
            render(board, turn=turn)
            status(f"{board[c]} in cell {c + 1} - {turn} to move")
        if not running:
            break
        w, line = result
        msg = {"X": "X wins!", "O": "O wins!", "draw": "draw"}[w]
        status(f"game over: {msg} - new game in 8 s")
        for k in range(8):
            render(board, line, flash=(k % 2 == 1))
            time.sleep(1.0)
        starter = "O" if starter == "X" else "X"  # loser-agnostic: just alternate who starts
    fb.show(fb.blank())
    status("stopped")


if __name__ == "__main__":
    main()
