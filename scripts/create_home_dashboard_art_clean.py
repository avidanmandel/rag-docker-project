from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "static" / "images" / "home-dashboard-art.png"
OUT = ROOT / "static" / "images" / "home-dashboard-art-clean.png"

X1, X2 = 208, 293
Y1, Y2 = 66, 136
REF_X1, REF_X2 = 718, 808
LEFT_FEATHER = 5
RIGHT_FEATHER = 7

src = Image.open(SRC).convert("RGBA")
arr = np.array(src, dtype=np.float32)
out = arr.copy()
ref_w = REF_X2 - REF_X1

for y in range(Y1, Y2):
    strip = arr[y, REF_X1:REF_X2, :3]
    for x in range(X1, X2):
        out[y, x, :3] = strip[(x - X1) % ref_w]

for i in range(LEFT_FEATHER):
    x = X1 + i
    alpha = (i + 1) / LEFT_FEATHER
    out[Y1:Y2, x, :3] = arr[Y1:Y2, x, :3] * (1 - alpha) + out[Y1:Y2, x, :3] * alpha

for i in range(RIGHT_FEATHER):
    x = X2 - RIGHT_FEATHER + i
    alpha = (i + 1) / RIGHT_FEATHER
    out[Y1:Y2, x, :3] = arr[Y1:Y2, x, :3] * (1 - alpha) + out[Y1:Y2, x, :3] * alpha

Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(OUT, optimize=True)
print("Wrote", OUT)