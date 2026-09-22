"""Extract tight glow silhouettes for furniture baked into the Memory Hall art."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "rpg" / "hall_of_memory_clean_v1.png"
OUTPUT = ROOT / "assets" / "rpg" / "environment" / "memory" / "search_masks"
CUTOUT_OUTPUT = ROOT / "assets" / "rpg" / "environment" / "memory" / "search_cutouts"
DETAIL_OUTPUT = ROOT / "assets" / "rpg" / "environment" / "memory" / "search_details"

# Coordinates use the 960x640 game canvas. Each mask describes the connected
# components visible in the baked room art, then exports only their edge halo.
SPECS = {
    "west_archive_bank": {"rect": (28, 98, 255, 132)},
    "north_votive_altar": {"rect": (360, 62, 250, 123)},
    "east_book_bank": {"rect": (648, 90, 258, 158)},
    "west_scriptorium_desk": {"rect": (46, 424, 280, 170)},
    "east_scriptorium_desk": {"rect": (684, 424, 270, 170)},
}


def _scaled_room() -> np.ndarray:
    image = cv2.imread(str(SOURCE), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(SOURCE)
    return cv2.resize(image, (960, 640), interpolation=cv2.INTER_AREA)


def _component_mask(object_id: str, width: int, height: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if object_id == "west_archive_bank":
        cv2.fillPoly(mask, [np.array(((35, 0), (229, 0), (229, 8), (236, 8), (236, 65), (226, 65), (226, 71), (42, 71), (42, 65), (35, 65)))], 255)
    elif object_id == "east_book_bank":
        cv2.fillPoly(mask, [np.array(((0, 0), (224, 0), (224, 8), (231, 8), (231, 82), (222, 82), (222, 89), (0, 89)))], 255)
    elif object_id == "north_votive_altar":
        cv2.fillPoly(mask, [np.array(((64, 91), (64, 25), (79, 8), (96, 0), (120, 0), (145, 0), (162, 8), (176, 25), (176, 91)))], 255)
        cv2.rectangle(mask, (52, 76), (188, 100), 255, -1)
        cv2.rectangle(mask, (42, 99), (198, 110), 255, -1)
    elif object_id == "west_scriptorium_desk":
        cv2.fillPoly(mask, [np.array(((0, 26), (20, 10), (168, 10), (185, 28), (185, 103), (170, 116), (10, 116), (0, 103)))], 255)
        cv2.rectangle(mask, (18, 26), (178, 101), 255, -1)
        cv2.fillPoly(mask, [np.array(((176, 91), (202, 82), (224, 101), (220, 133), (193, 145), (170, 126)))], 255)
    else:
        cv2.fillPoly(mask, [np.array(((56, 22), (72, 8), (240, 8), (255, 25), (255, 108), (240, 119), (65, 119), (52, 105)))], 255)
        cv2.rectangle(mask, (68, 23), (250, 105), 255, -1)
        cv2.fillPoly(mask, [np.array(((18, 99), (43, 86), (70, 101), (68, 132), (39, 145), (14, 126)))], 255)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))


def _extract(object_id: str, crop: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, width = crop.shape[:2]
    mask = _component_mask(object_id, width, height)
    # Export a narrow halo around the authored object's silhouette. A filled
    # mask makes large baked-in furniture look like a cyan rectangle, while a
    # contour ring reads as a deliberate interactable-object highlight.
    outer = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
    inner = cv2.erode(mask, np.ones((3, 3), np.uint8), iterations=1)
    alpha = cv2.GaussianBlur(cv2.subtract(outer, inner), (5, 5), 1.0)
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, :3] = 255
    rgba[:, :, 3] = alpha
    cutout = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
    cutout[:, :, 3] = mask
    gray = cv2.bilateralFilter(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 5, 24, 24)
    detail_alpha = cv2.bitwise_and(cv2.Canny(gray, 38, 94), mask)
    detail_alpha = cv2.GaussianBlur(
        cv2.dilate(detail_alpha, np.ones((2, 2), np.uint8)), (3, 3), 0.6
    )
    details = np.zeros((height, width, 4), dtype=np.uint8)
    details[:, :, :3] = 255
    details[:, :, 3] = detail_alpha
    return rgba, cutout, details


def main() -> None:
    room = _scaled_room()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CUTOUT_OUTPUT.mkdir(parents=True, exist_ok=True)
    DETAIL_OUTPUT.mkdir(parents=True, exist_ok=True)
    for object_id, spec in SPECS.items():
        x, y, width, height = spec["rect"]
        crop = room[y:y + height, x:x + width]
        target = OUTPUT / f"{object_id}.png"
        cutout_target = CUTOUT_OUTPUT / f"{object_id}.png"
        detail_target = DETAIL_OUTPUT / f"{object_id}.png"
        mask, cutout, details = _extract(object_id, crop)
        if not cv2.imwrite(str(target), mask):
            raise OSError(f"Could not write {target}")
        if not cv2.imwrite(str(cutout_target), cutout):
            raise OSError(f"Could not write {cutout_target}")
        if not cv2.imwrite(str(detail_target), details):
            raise OSError(f"Could not write {detail_target}")
        print(target)


if __name__ == "__main__":
    main()
