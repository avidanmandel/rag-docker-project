from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "static/images/home-dashboard-art.png"
OUT = ROOT / "static/images/home-dashboard-art-clean.png"

# Remove shield/glow only; preserve wordmark from x=292 onward.
X1, X2 = 198, 292
Y1, Y2 = 68, 126
REF_X1, REF_X2 = 148, 198

src = Image.open(SRC).convert("RGBA")
arr = np.array(src, dtype=np.float32)
out = arr.copy()
ref_w = REF_X2 - REF_X1

for y in range(Y1, Y2):
    strip = arr[y, REF_X1:REF_X2, :3]
    for x in range(X1, X2):
        out[y, x, :3] = strip[(x - X1) % ref_w]

Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA").save(OUT, optimize=True)
print("Wrote", OUT)