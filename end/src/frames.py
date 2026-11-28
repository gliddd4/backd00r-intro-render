import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx"))
from vintage import look, save

work, out = sys.argv[1], sys.argv[2]
count = int(sys.argv[3])
first = int(sys.argv[4]) if len(sys.argv) > 4 else 0
only = [int(v) for v in sys.argv[5].split(",")] if len(sys.argv) > 5 and sys.argv[5] else None
loop = int(sys.argv[6]) if len(sys.argv) > 6 else 0
FPS = int(os.environ.get("RATE") or 20)
STEP = max(1, FPS // 5)
SIZE = (1080, 2340)
FOCUS = (520, 1060)


os.makedirs(out, exist_ok=True)
QUICK = bool(os.environ.get("QUICK"))
LOOP = 8.0


def wobble(t):
    w = 2 * math.pi / LOOP
    dx = 3.0 * math.sin(w * t + 0.3) + 1.6 * math.sin(3 * w * t + 1.1) + 0.7 * math.sin(7 * w * t + 2.0)
    dy = 2.4 * math.sin(2 * w * t + 0.9) + 1.2 * math.sin(5 * w * t + 0.2) + 0.5 * math.sin(9 * w * t + 1.4)
    turn = math.radians(0.22 * math.sin(2 * w * t + 0.5) + 0.1 * math.sin(3 * w * t + 2.2))
    return dx, dy, turn


def shoot(plate, box, t):
    x0, y0, x1, y1 = box
    dx, dy, turn = wobble(t)
    sx, sy = (x1 - x0) / SIZE[0], (y1 - y0) / SIZE[1]
    c, s = math.cos(turn), math.sin(turn)
    mx, my = SIZE[0] / 2, SIZE[1] / 2
    cx, cy = (x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy
    return plate.transform(SIZE, Image.AFFINE, (sx * c, -sy * s, cx - sx * c * mx + sy * s * my, sx * s, sy * c, cy - sx * s * mx - sy * c * my), Image.BICUBIC)


def finish(a, seed, name):
    if QUICK:
        Image.fromarray((a * 255).clip(0, 255).astype(np.uint8)).save(name)
    else:
        save(look(a, seed, grain_size=1.0), name)


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def plate_at(t, seed, start=None):
    ppm = os.path.join(work, "frame.ppm")
    extra = ["%.4f" % (-1 if start is None else start)]
    subprocess.run([os.path.join(work, "ending"), ppm, "ladder.rgba", "%.4f" % t, str(seed)] + extra, cwd=work, check=True)
    return Image.open(ppm).convert("RGB")


for k in only if only is not None else range(count):
    t = k / FPS
    plate = plate_at(t, (first + k) // STEP)
    w, h = plate.size
    u = k / max(1, count - 1)
    zoom = 1.0 + 0.085 * ease(u * 1.1)
    rise = (1 - ease(k / (FPS * 1.4))) * 0.07 * h
    cw, ch = w / zoom, h / zoom
    cx = w / 2 + (FOCUS[0] - w / 2) * (zoom - 1) / 0.085 * 0.5
    cy = h / 2 + (FOCUS[1] - h / 2) * (zoom - 1) / 0.085 * 0.5 + rise
    cy = min(h - ch / 2, max(ch / 2, cy))
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    frame = shoot(plate, box, t)
    fog = 1 - ease(k / (FPS * 0.9))
    if fog > 0:
        frame = frame.filter(ImageFilter.GaussianBlur(14 * fog))
    a = np.asarray(frame).astype(np.float32) / 255.0
    if fog > 0:
        mist = np.array([0.88, 0.89, 0.93], np.float32)
        a = a * (1 - fog) + mist * fog
    finish(a, (first + k) // STEP, os.path.join(out, "f%04d.jpg" % (first + k)))
    print("end frame", first + k, flush=True)
    if k == count - 1:
        part, parts = (int(v) for v in (os.environ.get("LOOP_PART") or "0/1").split("/"))
        for n in range(int(os.environ.get("LOOP_FROM") or 0) + part, loop, parts):
            held = shoot(plate_at(t + n / FPS, 100000 + n // STEP, t), box, t + n / FPS)
            finish(np.asarray(held).astype(np.float32) / 255.0, 100000 + n // STEP, os.path.join(out, "loop%03d.jpg" % n))
            print("loop frame", n, flush=True)
        print("idle loop frames", loop, flush=True)
