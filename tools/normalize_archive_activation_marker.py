"""Clean the generated 4x3 Archive marker state atlas for runtime use."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "rpg" / "archive_activation_marker_state_atlas_v6.png"
OUTPUT = ROOT / "assets" / "rpg" / "archive_activation_marker_state_runtime_v6.png"


def main() -> None:
    source = np.array(Image.open(SOURCE).convert("RGBA"))
    columns, rows = 4, 3
    cell_width = source.shape[1] // columns
    cell_height = source.shape[0] // rows
    cells = []
    for index in range(columns * rows):
        row, column = divmod(index, columns)
        cell = source[
            row * cell_height:(row + 1) * cell_height,
            column * cell_width:(column + 1) * cell_width,
        ].copy()
        cell[cell[:, :, 3] < 32] = 0
        if row == 2:
            # Generated activation pillars reach the atlas boundary. Fade the
            # upper edge into transparency so runtime beams end naturally.
            fade_height = max(1, round(cell_height * 0.16))
            fade = np.linspace(0.0, 1.0, fade_height, dtype=np.float32)
            cell[:fade_height, :, 3] = (
                cell[:fade_height, :, 3].astype(np.float32) * fade[:, None]
            ).astype(np.uint8)
        ys, xs = np.where(cell[:, :, 3] > 0)
        if not len(xs):
            raise RuntimeError(f"Activation marker frame {index} is empty")
        cells.append(cell)
    # Keep every complete square cell. The generated activation row uses its
    # upper transparent space for the rising energy column, while all rows
    # share the same floor anchor near the bottom of their cell.
    sheet_rows = [
        np.concatenate(cells[row * columns:(row + 1) * columns], axis=1)
        for row in range(rows)
    ]
    sheet = np.concatenate(sheet_rows, axis=0)
    Image.fromarray(sheet, "RGBA").save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
