from pathlib import Path
import numpy as np
from PIL import Image

SRC = Path("static/images/home-dashboard-art.png")
OUT = Path("static/images/home-dashboard-art-clean.png")
# Shield icon only — stop before the ScoutMatch wordmark (~x=308).
SHIELD_BOX = (198, 76, 308, 142)

src = Image.open(SRC).convert("RGBA")
arr = np.array(src, dtype=np.float32)
x1, y1, x2, y2 = SHIELD_BOX
h, w = y2 - y1, x2 - x1

left_bg = arr[y1:y2, max(0, x1 - 90) : x1, :3]
fill = np.tile(np.median(left_bg.reshape(-1, 3), axis=0), (h, w, 1)).astype(np.float32)
top = np.median(arr[max(0, y1 - 30) : y1, max(0, x1 - 90) : x2, :3].reshape(-1, 3), axis=0)
bot = np.median(arr[y2 : min(arr.shape[0], y2 + 30), max(0, x1 - 90) : x2, :3].reshape(-1, 3), axis=0)
for row in range(h):
    t = row / max(h - 1, 1)
    fill[row, :, :] = top * (1 - t) + bot * t

mask = np.ones((h, w), dtype=np.float32)
for i in range(10):
    mask[:, -(i + 1)] = (i + 1) / 10

arr[y1:y2, x1:x2, :3] = arr[y1:y2, x1:x2, :3] * (1 - mask[..., None]) + fill * mask[..., None]
Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA").save(OUT, optimize=True)
print("Wrote", OUT)