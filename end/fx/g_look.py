import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from vintage import look, save

src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
for k, path in enumerate(sorted(glob.glob(os.path.join(src, "f*.jpg")))):
    a = np.asarray(Image.open(path).convert("RGB").resize((1080, 2340), Image.BICUBIC)).astype(np.float32) / 255.0
    save(look(a, 9000 + k, grain_size=1.0), os.path.join(dst, os.path.basename(path)))
print("done", k + 1)
