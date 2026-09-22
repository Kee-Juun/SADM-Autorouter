"""Clean and baseline-align the generated eight-frame side-walk atlas."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "rpg" / "last_clerk_side_walk_atlas_v4.png"
OUTPUT = ROOT / "assets" / "rpg" / "last_clerk_side_walk_runtime_sheet_v4.png"
FRAME_COUNT = 8
FRAME_WIDTH = 290
FRAME_HEIGHT = 410
BASELINE = 398


def _main_character(frame: np.ndarray) -> np.ndarray:
    alpha = frame[:, :, 3]
    binary = np.where(alpha >= 32, 255, 0).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    if count <= 1:
        return frame
    center = np.array([frame.shape[1] / 2, frame.shape[0] / 2])
    candidates = []
    for label in range(1, count):
        area = stats[label, cv2.CC_STAT_AREA]
        if area < 120:
            continue
        distance = np.linalg.norm(centroids[label] - center)
        candidates.append((area - distance * 6, label))
    keep_label = max(candidates)[1]
    kept = labels == keep_label
    cleaned = np.zeros_like(frame)
    cleaned[kept] = frame[kept]
    cleaned[:, :, 3] = np.where(kept, np.maximum(alpha, 48), 0)
    return cleaned


def main() -> None:
    source = np.array(Image.open(SOURCE).convert("RGBA"))
    cell_width = source.shape[1] // FRAME_COUNT
    contents = []
    for index in range(FRAME_COUNT):
        cell = source[:, index * cell_width:(index + 1) * cell_width].copy()
        cell = _main_character(cell)
        ys, xs = np.where(cell[:, :, 3] > 0)
        if not len(xs):
            raise RuntimeError(f"Frame {index} has no visible character pixels")
        contents.append(cell[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    widest = max(content.shape[1] for content in contents)
    tallest = max(content.shape[0] for content in contents)
    scale = min((FRAME_WIDTH - 16) / widest, (FRAME_HEIGHT - 18) / tallest)
    frames = []
    for content in contents:
        size = (max(1, round(content.shape[1] * scale)), max(1, round(content.shape[0] * scale)))
        content = cv2.resize(content, size, interpolation=cv2.INTER_LANCZOS4)
        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 4), dtype=np.uint8)
        left = (FRAME_WIDTH - content.shape[1]) // 2
        top = BASELINE - content.shape[0]
        frame[top:top + content.shape[0], left:left + content.shape[1]] = content
        frames.append(frame)
    sheet = np.concatenate(frames, axis=1)
    Image.fromarray(sheet, "RGBA").save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
