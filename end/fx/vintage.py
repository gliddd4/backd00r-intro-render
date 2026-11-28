import sys

import numpy as np
from PIL import Image, ImageFilter


def blurred(a, radius):
    return np.asarray(Image.fromarray((a.clip(0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius))).astype(np.float32) / 255.0


def look(a, seed, grain_size=0.7, real=False):
    rng = np.random.default_rng(seed)
    h, w, _ = a.shape

    bright = np.clip((a.max(axis=2, keepdims=True) - 0.6) / 0.4, 0, 1) * a
    glow = blurred(bright, w * 0.012) * np.array([1.0, 0.55, 0.35])
    a = 1 - (1 - a) * (1 - glow * (0.25 if real else 0.55))

    lum = (a * [0.299, 0.587, 0.114]).sum(axis=2, keepdims=True)
    a = lum + (a - lum) * (1.08 if real else 0.86)

    if real:
        a = np.clip((a - 0.02) / 0.98, 0, None)
    else:
        a = a * 0.9 + 0.045
        a[..., 0] = a[..., 0] * 1.03 + 0.01
        a[..., 2] = a[..., 2] * 0.96 + 0.015
        a = np.clip(a, 0, None) ** np.array([0.97, 1.0, 1.04])

    noise = rng.normal(0, 1, (h, w)).astype(np.float32)
    g = blurred(noise[..., None].repeat(3, 2) * 0.25 + 0.5, grain_size)[..., 0]
    noise = (g - 0.5) / 0.25
    lum = (a * [0.299, 0.587, 0.114]).sum(axis=2, keepdims=True)
    amt = (0.022 if real else 0.055) * (1 - (2 * lum - 1) ** 2) + (0.006 if real else 0.015)
    a = a + noise[..., None] * amt
    a = a + rng.normal(0, 0.005 if real else 0.012, (h, w, 3)).astype(np.float32)

    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a = a * (1 - (0.12 if real else 0.22) * np.clip(r - 0.55, 0, 1) ** 1.6)[..., None]
    return a.clip(0, 1)


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0


def save(a, path):
    Image.fromarray((a.clip(0, 1) * 255).astype(np.uint8)).save(path, quality=93)


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    save(look(load(src), seed), dst)
