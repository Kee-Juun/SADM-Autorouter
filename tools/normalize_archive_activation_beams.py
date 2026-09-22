"""Remove low-alpha atlas haze so activation pillars retain runtime height."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "rpg" / "archive_activation_beam_overlay_atlas_v1.png"
OUTPUT = ROOT / "assets" / "rpg" / "archive_activation_beam_overlay_runtime_v1.png"


def main() -> None:
    image = np.array(Image.open(SOURCE).convert("RGBA"))
    # Image generation leaves an almost invisible bloom across the full cell.
    # Clearing it lets the shared-frame crop follow the actual pillar artwork.
    image[image[:, :, 3] < 24] = 0
    cell_width = image.shape[1] // 4
    for index in range(4):
        alpha = image[:, index * cell_width:(index + 1) * cell_width, 3]
        ys, _xs = np.where(alpha > 0)
        if not len(ys):
            continue
        top, bottom = int(ys.min()), int(ys.max()) + 1
        fade_height = max(12, round((bottom - top) * 0.18))
        fade_end = min(bottom, top + fade_height)
        fade = np.linspace(0.0, 1.0, fade_end - top, dtype=np.float32)
        alpha[top:fade_end] = (
            alpha[top:fade_end].astype(np.float32) * fade[:, None]
        ).astype(np.uint8)
    Image.fromarray(image, "RGBA").save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
