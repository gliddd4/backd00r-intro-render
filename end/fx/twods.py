import io
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

src, dst = sys.argv[1], sys.argv[2]
W, H = 1080, 2340
LOW, HIGH = (360, 780), (720, 1560)
probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "json", src], capture_output=True, check=True).stdout)
num, den = probe["streams"][0]["r_frame_rate"].split("/")
rate = float(num) / float(den)
grain_step = max(1, round(rate / 5))


def wander(seed, t, speeds):
    r = np.random.default_rng(seed)
    phases = r.uniform(0, math.tau, len(speeds))
    return sum(math.sin(t * s * math.tau + p) / (1 + k) for k, (s, p) in enumerate(zip(speeds, phases)))


def shake(t):
    dx = 7.0 * wander(11, t, [0.31, 0.83, 2.1, 4.7])
    dy = 6.0 * wander(12, t, [0.27, 0.71, 1.9, 5.3])
    turn = 0.006 * wander(13, t, [0.23, 0.9, 2.6])
    return dx, dy, turn


def place(img, dx, dy, turn):
    w, h = img.size
    c, s = math.cos(turn), math.sin(turn)
    cx, cy = w / 2, h / 2
    zoom = 1.03
    a, b = c / zoom, -s / zoom
    d, e = s / zoom, c / zoom
    return img.transform(img.size, Image.AFFINE, (a, b, cx - a * cx - b * cy - dx, d, e, cy - d * cx - e * cy - dy), Image.BILINEAR)


def gray_small(img):
    return np.asarray(img.convert("L").resize((90, 195), Image.BILINEAR)).astype(np.float32)


def drift(prev, cur):
    if prev is None:
        return 0.0
    a, b = prev - prev.mean(), cur - cur.mean()
    cross = np.fft.ifft2(np.fft.fft2(a) * np.conj(np.fft.fft2(b)))
    peak = np.unravel_index(np.argmax(np.abs(cross)), cross.shape)
    shift = peak[1] if peak[1] < a.shape[1] // 2 else peak[1] - a.shape[1]
    return float(shift) * W / a.shape[1]


def tone(a):
    a = a * 1.18 - 0.02
    a = np.clip(a, 0, 1)
    a = 0.06 + a * 0.94
    luma = a @ np.array([0.3, 0.59, 0.11], np.float32)
    a = luma[..., None] + (a - luma[..., None]) * 0.82
    shadow = np.clip(1 - luma / 0.45, 0, 1)[..., None]
    a = a + shadow * np.array([-0.012, 0.022, -0.004], np.float32)
    a[..., 1] = a[..., 1] ** (1 / 1.04)
    return np.clip(a, 0, 1)


def lean(a, amount):
    h = a.shape[0]
    rows = (np.arange(h) / h - 0.5) * amount
    out = np.empty_like(a)
    xs = np.arange(a.shape[1])
    for y in range(h):
        src_x = np.clip(xs - rows[y], 0, a.shape[1] - 1).astype(int)
        out[y] = a[y, src_x]
    return out


reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-vf", "scale=%d:%d" % (W, H), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H), "-r", "%g" % rate, "-i", "-", "-c:v", "libx264", "-crf", "24", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], stdin=subprocess.PIPE)
prev = None
n = 0
while True:
    raw = reader.stdout.read(W * H * 3)
    if len(raw) < W * H * 3:
        break
    t = n / rate
    frame = Image.frombuffer("RGB", (W, H), raw)
    small = gray_small(frame)
    pan = drift(prev, small)
    prev = small
    dx, dy, turn = shake(t)
    ndx, ndy, _ = shake(t + 1 / 20.0)
    vx, vy = ndx - dx, ndy - dy
    size = LOW
    work = frame.resize(size, Image.BILINEAR)
    k = size[0] / W
    taps = 5
    acc = np.zeros((size[1], size[0], 3), np.float32)
    for i in range(taps):
        f = i / (taps - 1) - 0.5
        moved = place(work, (dx + vx * f * 1.6) * k, (dy + vy * f * 1.6) * k, turn)
        acc += np.asarray(moved).astype(np.float32)
    a = acc / (taps * 255.0)
    a = lean(a, -(pan * rate / 20.0 + vx) * k * 0.35)
    a = tone(a)
    step = n // grain_step
    g = np.random.default_rng(1000 + step)
    a = np.clip(a + g.uniform(-14, 14, (size[1], size[0], 1)).astype(np.float32) / 255, 0, 1)
    img = Image.fromarray((a * 255).astype(np.uint8))
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=160, threshold=1))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=45, subsampling=2)
    small_out = np.asarray(Image.open(buf).convert("RGB")).copy()
    img = Image.fromarray(small_out).resize((W, H), Image.BILINEAR)
    kh = HIGH[0] / W
    sharp = tone(np.asarray(place(frame.resize(HIGH, Image.BILINEAR), dx * kh, dy * kh, turn)).astype(np.float32) / 255.0)
    sharp = np.asarray(Image.fromarray((sharp * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)).astype(np.float32)
    img = Image.fromarray((np.asarray(img).astype(np.float32) * 0.95 + sharp * 0.05).astype(np.uint8))
    writer.stdin.write(img.tobytes())
    n += 1
writer.stdin.close()
writer.wait()
print(dst, n)
