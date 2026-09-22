"""Align incomplete memory plinths to their completed floor contact points."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MEMORY_ASSETS = ROOT / "assets" / "rpg" / "environment" / "memory"
ARCHIVES = ("past", "present", "future")
COMPLETED_SHEETS = {
    "past": "past_idle_runtime_sheet.png",
    "present": "present_idle_runtime_sheet.png",
    "future": "future_v2_idle_runtime_sheet.png",
}
COLS = 4
ROWS = 3


def _floor_anchor(cell: Image.Image) -> tuple[int, int]:
    """Return the median lower-footprint x and lowest solid architectural y."""
    alpha = np.asarray(cell.getchannel("A"))
    height, width = alpha.shape
    yy, xx = np.where(
        (alpha > 180)
        & (np.indices(alpha.shape)[0] >= int(height * 0.68))
    )
    if not len(xx):
        return width // 2, height - 2
    # Use the upper median so even-width masonry silhouettes resolve to one
    # deterministic pixel instead of oscillating around a half-pixel center.
    anchor_x = int(np.partition(xx, len(xx) // 2)[len(xx) // 2])
    return anchor_x, int(yy.max())


def _alpha_bbox(cell: Image.Image) -> tuple[int, int, int, int]:
    alpha = np.asarray(cell.getchannel("A"))
    yy, xx = np.where(alpha > 180)
    if not len(xx):
        return 0, 0, cell.width, cell.height
    return int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1


def _translated(cell: Image.Image, target_anchor: tuple[int, int]) -> Image.Image:
    locked = cell
    for _ in range(3):
        anchor_x, anchor_y = _floor_anchor(locked)
        dx = target_anchor[0] - anchor_x
        dy = target_anchor[1] - anchor_y
        if dx == 0 and dy == 0:
            break
        shifted = Image.new("RGBA", locked.size, (0, 0, 0, 0))
        shifted.alpha_composite(locked, (dx, dy))
        locked = shifted
    return locked


def _completed_anchor(archive_id: str, target_size: tuple[int, int]) -> tuple[int, int]:
    sheet = Image.open(MEMORY_ASSETS / COMPLETED_SHEETS[archive_id]).convert("RGBA")
    cell_width = sheet.width // COLS
    cell = sheet.crop((0, 0, cell_width, sheet.height))
    anchor_x, anchor_y = _floor_anchor(cell)
    target_width, target_height = target_size
    return (
        round(anchor_x / cell_width * target_width),
        round(anchor_y / sheet.height * target_height),
    )


def _completed_bbox(archive_id: str, target_size: tuple[int, int]) -> tuple[int, int, int, int]:
    sheet = Image.open(MEMORY_ASSETS / COMPLETED_SHEETS[archive_id]).convert("RGBA")
    cell_width = sheet.width // COLS
    bounds = _alpha_bbox(sheet.crop((0, 0, cell_width, sheet.height)))
    target_width, target_height = target_size
    return (
        round(bounds[0] / cell_width * target_width),
        round(bounds[1] / sheet.height * target_height),
        round(bounds[2] / cell_width * target_width),
        round(bounds[3] / sheet.height * target_height),
    )


def normalize_atlas(archive_id: str, source: Path, destination: Path) -> None:
    atlas = Image.open(source).convert("RGBA")
    cell_width = atlas.width // COLS
    cell_height = atlas.height // ROWS
    target_anchor = _completed_anchor(archive_id, (cell_width, cell_height))
    normalized = Image.new(
        "RGBA",
        (cell_width * COLS, cell_height * ROWS),
        (0, 0, 0, 0),
    )

    for frame in range(COLS * ROWS):
        col = frame % COLS
        row = frame // COLS
        box = (
            col * cell_width,
            row * cell_height,
            (col + 1) * cell_width,
            (row + 1) * cell_height,
        )
        locked = _translated(atlas.crop(box), target_anchor)
        normalized.alpha_composite(locked, (box[0], box[1]))

    normalized.save(destination)

    # The incomplete physical body is a single immutable frame. Runtime motion
    # comes from a separate transparent VFX strip, never from the architecture.
    source_cell = atlas.crop((0, 0, cell_width, cell_height))
    source_bounds = _alpha_bbox(source_cell)
    destination_bounds = _completed_bbox(archive_id, (cell_width, cell_height))
    physical_body = source_cell.crop(source_bounds).resize(
        (
            destination_bounds[2] - destination_bounds[0],
            destination_bounds[3] - destination_bounds[1],
        ),
        Image.Resampling.LANCZOS,
    )
    static_frame = Image.new("RGBA", (cell_width, cell_height), (0, 0, 0, 0))
    static_frame.alpha_composite(physical_body, destination_bounds[:2])
    static_frame.save(MEMORY_ASSETS / f"{archive_id}_incomplete_static_v1.png")


def normalize_completed_future_sheet() -> None:
    """Remove horizontal base drift without suppressing the completed VFX loop."""
    source = Image.open(MEMORY_ASSETS / "future_v2_idle_runtime_sheet.png").convert("RGBA")
    cell_width = source.width // COLS
    reference = source.crop((0, 0, cell_width, source.height))
    target_anchor = _floor_anchor(reference)
    locked = Image.new("RGBA", (cell_width * COLS, source.height), (0, 0, 0, 0))
    for frame in range(COLS):
        cell = source.crop((frame * cell_width, 0, (frame + 1) * cell_width, source.height))
        locked.alpha_composite(_translated(cell, target_anchor), (frame * cell_width, 0))
    locked.save(MEMORY_ASSETS / "future_v3_idle_runtime_sheet_locked.png")


def main() -> None:
    for archive_id in ARCHIVES:
        normalize_atlas(
            archive_id,
            MEMORY_ASSETS / f"{archive_id}_state_atlas_v2.png",
            MEMORY_ASSETS / f"{archive_id}_state_atlas_v4_aligned.png",
        )
    normalize_completed_future_sheet()


if __name__ == "__main__":
    main()
