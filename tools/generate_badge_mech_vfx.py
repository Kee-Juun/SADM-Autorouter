"""Generate context-aware mechanical idle frames for achievement badges.

The source badges are flat PNGs, so the generator cannot know true production
layers. Instead, each badge gets a tiny semantic rig that targets the visual
parts that already look movable: portal posts, rings, paper slips, crown tips,
node hubs, check plates, shield faces, and vault dials.

Important art rule: do not animate broad arbitrary slices. Each sequence starts
on the original badge, moves only believable parts a few pixels/degrees, returns
them home, and ends on the original badge again.
"""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SHOP_ICON_DIR = ROOT / "assets" / "images" / "shop_icons"
OUT_DIR = ROOT / "assets" / "images" / "badge_mech"
SIZE = 256
FRAMES = 30


@dataclass(frozen=True)
class Motion:
    shape: str
    dx: float = 0.0
    dy: float = 0.0
    angle: float = 0.0
    start: float = 0.0
    end: float = 1.0
    curve: str = "settle"
    pivot: str = "center"
    tint: tuple[int, int, int] = (132, 236, 255)
    edge: float = 0.38
    shadow: float = 0.34
    erase: bool = True
    opacity: float = 1.0
    scale: float = 0.0


@dataclass(frozen=True)
class EffectSpec:
    image_name: str
    motions: tuple[Motion, ...]


def m(
    shape: str,
    dx: float = 0.0,
    dy: float = 0.0,
    angle: float = 0.0,
    start: float = 0.0,
    end: float = 1.0,
    curve: str = "settle",
    pivot: str = "center",
    tint: tuple[int, int, int] = (132, 236, 255),
    edge: float = 0.38,
    shadow: float = 0.34,
    erase: bool = True,
    opacity: float = 1.0,
    scale: float = 0.0,
) -> Motion:
    return Motion(shape, dx, dy, angle, start, end, curve, pivot, tint, edge, shadow, erase, opacity, scale)


def _fit_badge(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    image.thumbnail((236, 236), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2))
    return canvas


def _badge_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    return image.getchannel("A").getbbox() or (16, 16, 240, 240)


def _pt(bounds: tuple[int, int, int, int], x: float, y: float) -> tuple[float, float]:
    left, top, right, bottom = bounds
    return left + (right - left) * x, top + (bottom - top) * y


def _rect(bounds: tuple[int, int, int, int], x1: float, y1: float, x2: float, y2: float) -> list[float]:
    ax, ay = _pt(bounds, x1, y1)
    bx, by = _pt(bounds, x2, y2)
    return [ax, ay, bx, by]


def _poly(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], points: list[tuple[float, float]], fill: int = 255) -> None:
    draw.polygon([_pt(bounds, x, y) for x, y in points], fill=fill)


def _ellipse(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], box: tuple[float, float, float, float]) -> None:
    draw.ellipse(_rect(bounds, *box), fill=255)


def _rectangle(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], box: tuple[float, float, float, float]) -> None:
    draw.rounded_rectangle(_rect(bounds, *box), radius=7, fill=255)


def _ring(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], outer, inner) -> None:
    draw.ellipse(_rect(bounds, *outer), fill=255)
    draw.ellipse(_rect(bounds, *inner), fill=0)


def _arc(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], start: int, end: int) -> None:
    draw.pieslice(_rect(bounds, 0.10, 0.10, 0.90, 0.90), start, end, fill=255)
    draw.ellipse(_rect(bounds, 0.31, 0.31, 0.69, 0.69), fill=0)


def _shape_mask(bounds: tuple[int, int, int, int], shape: str) -> Image.Image:
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)

    if shape in {"portal_left_post", "court_left_post"}:
        _poly(draw, bounds, [(0.16, 0.30), (0.34, 0.20), (0.40, 0.74), (0.22, 0.82)])
    elif shape in {"portal_right_post", "court_right_post"}:
        _poly(draw, bounds, [(0.84, 0.30), (0.66, 0.20), (0.60, 0.74), (0.78, 0.82)])
    elif shape in {"portal_core", "court_floor"}:
        _poly(draw, bounds, [(0.30, 0.60), (0.70, 0.60), (0.78, 0.82), (0.22, 0.82)])
    elif shape == "portal_top_crystal":
        _poly(draw, bounds, [(0.50, 0.06), (0.62, 0.28), (0.50, 0.38), (0.38, 0.28)])

    elif shape == "spark_nodes":
        for box in [(0.24, 0.28, 0.36, 0.40), (0.64, 0.28, 0.76, 0.40), (0.23, 0.62, 0.35, 0.74), (0.65, 0.62, 0.77, 0.74)]:
            _ellipse(draw, bounds, box)
    elif shape == "spark_center_star":
        _poly(draw, bounds, [(0.50, 0.08), (0.58, 0.48), (0.50, 0.92), (0.42, 0.48)])
    elif shape == "spark_lower_frame":
        _poly(draw, bounds, [(0.25, 0.72), (0.50, 0.92), (0.75, 0.72), (0.66, 0.86), (0.34, 0.86)])

    elif shape == "paper_top":
        _poly(draw, bounds, [(0.16, 0.09), (0.84, 0.13), (0.76, 0.40), (0.10, 0.34)])
    elif shape == "paper_middle":
        _poly(draw, bounds, [(0.12, 0.33), (0.88, 0.35), (0.78, 0.58), (0.10, 0.56)])
    elif shape == "paper_bottom":
        _poly(draw, bounds, [(0.14, 0.52), (0.82, 0.56), (0.72, 0.82), (0.22, 0.82)])
    elif shape == "storm_lower_energy":
        _ellipse(draw, bounds, (0.24, 0.56, 0.76, 0.90))

    elif shape == "stack_top_plate":
        _poly(draw, bounds, [(0.24, 0.22), (0.76, 0.22), (0.68, 0.36), (0.32, 0.36)])
        _poly(draw, bounds, [(0.50, 0.07), (0.68, 0.36), (0.50, 0.55), (0.32, 0.36)], fill=0)
    elif shape == "stack_mid_plate":
        _poly(draw, bounds, [(0.18, 0.36), (0.82, 0.36), (0.72, 0.56), (0.28, 0.56)])
        _poly(draw, bounds, [(0.50, 0.07), (0.68, 0.36), (0.50, 0.55), (0.32, 0.36)], fill=0)
    elif shape == "stack_bottom_plate":
        _poly(draw, bounds, [(0.14, 0.55), (0.86, 0.55), (0.72, 0.76), (0.28, 0.76)])
    elif shape == "stack_core":
        _poly(draw, bounds, [(0.50, 0.07), (0.66, 0.36), (0.50, 0.52), (0.34, 0.36)])

    elif shape == "crown_points":
        _poly(draw, bounds, [(0.16, 0.22), (0.28, 0.04), (0.38, 0.24), (0.50, 0.00), (0.62, 0.24), (0.72, 0.04), (0.84, 0.22), (0.78, 0.40), (0.22, 0.40)])
    elif shape == "crown_center_gem":
        _poly(draw, bounds, [(0.50, 0.70), (0.62, 0.88), (0.50, 0.99), (0.38, 0.88)])
    elif shape == "crown_left_loop":
        _ellipse(draw, bounds, (0.18, 0.48, 0.52, 0.78))
    elif shape == "crown_right_loop":
        _ellipse(draw, bounds, (0.48, 0.48, 0.82, 0.78))

    elif shape == "calendar_check":
        _poly(draw, bounds, [(0.20, 0.52), (0.34, 0.42), (0.46, 0.58), (0.80, 0.20), (0.88, 0.32), (0.48, 0.78)])
    elif shape == "calendar_page":
        _rectangle(draw, bounds, (0.20, 0.18, 0.70, 0.76))
    elif shape == "calendar_spine":
        _rectangle(draw, bounds, (0.18, 0.07, 0.78, 0.28))

    elif shape == "warlord_faceplate":
        _poly(draw, bounds, [(0.35, 0.24), (0.65, 0.24), (0.72, 0.58), (0.50, 0.83), (0.28, 0.58)])
    elif shape == "warlord_side_flags":
        _poly(draw, bounds, [(0.09, 0.35), (0.25, 0.40), (0.22, 0.88), (0.11, 0.76)])
        _poly(draw, bounds, [(0.91, 0.35), (0.75, 0.40), (0.78, 0.88), (0.89, 0.76)])
    elif shape == "warlord_top_spikes":
        _poly(draw, bounds, [(0.16, 0.13), (0.50, 0.00), (0.84, 0.13), (0.75, 0.34), (0.25, 0.34)])

    elif shape == "circuit_crystal":
        _poly(draw, bounds, [(0.50, 0.08), (0.65, 0.50), (0.50, 0.92), (0.35, 0.50)])
    elif shape == "circuit_side_nodes":
        for box in [(0.17, 0.44, 0.31, 0.58), (0.69, 0.44, 0.83, 0.58)]:
            _ellipse(draw, bounds, box)
    elif shape == "circuit_board_rails":
        _poly(draw, bounds, [(0.11, 0.18), (0.30, 0.28), (0.30, 0.78), (0.10, 0.86)])
        _poly(draw, bounds, [(0.89, 0.18), (0.70, 0.28), (0.70, 0.78), (0.90, 0.86)])
    elif shape == "circuit_left_rail":
        _poly(draw, bounds, [(0.11, 0.18), (0.30, 0.28), (0.30, 0.78), (0.10, 0.86)])
    elif shape == "circuit_right_rail":
        _poly(draw, bounds, [(0.89, 0.18), (0.70, 0.28), (0.70, 0.78), (0.90, 0.86)])

    elif shape == "clean_shield_face":
        _poly(draw, bounds, [(0.50, 0.10), (0.78, 0.24), (0.72, 0.68), (0.50, 0.92), (0.28, 0.68), (0.22, 0.24)])
    elif shape == "clean_outer_frame":
        _ring(draw, bounds, (0.15, 0.12, 0.85, 0.88), (0.29, 0.29, 0.71, 0.74))
    elif shape == "clean_bottom_gem":
        _poly(draw, bounds, [(0.50, 0.78), (0.62, 0.92), (0.50, 0.99), (0.38, 0.92)])

    elif shape == "precision_targets":
        for box in [(0.23, 0.18, 0.43, 0.38), (0.57, 0.18, 0.77, 0.38), (0.22, 0.57, 0.42, 0.77), (0.58, 0.57, 0.78, 0.77)]:
            _ring(draw, bounds, box, (box[0] + 0.05, box[1] + 0.05, box[2] - 0.05, box[3] - 0.05))
    elif shape == "precision_top_reticle":
        _ring(draw, bounds, (0.38, 0.08, 0.62, 0.32), (0.45, 0.15, 0.55, 0.25))
    elif shape == "precision_top_cylinder":
        _ellipse(draw, bounds, (0.20, 0.05, 0.80, 0.59))
    elif shape == "precision_left_cylinder":
        _ellipse(draw, bounds, (0.02, 0.38, 0.52, 0.88))
    elif shape == "precision_right_cylinder":
        _ellipse(draw, bounds, (0.48, 0.38, 0.98, 0.88))
    elif shape == "precision_lower_plates":
        _poly(draw, bounds, [(0.26, 0.72), (0.50, 0.94), (0.74, 0.72), (0.65, 0.88), (0.35, 0.88)])

    elif shape == "audit_door":
        _rectangle(draw, bounds, (0.30, 0.24, 0.70, 0.78))
    elif shape == "audit_seal":
        _ellipse(draw, bounds, (0.42, 0.58, 0.58, 0.74))
    elif shape == "audit_edges":
        _ring(draw, bounds, (0.10, 0.12, 0.90, 0.90), (0.24, 0.26, 0.76, 0.78))

    elif shape == "immaculate_scales":
        _ellipse(draw, bounds, (0.20, 0.36, 0.46, 0.62))
        _ellipse(draw, bounds, (0.54, 0.36, 0.80, 0.62))
    elif shape == "immaculate_top_crystal":
        _poly(draw, bounds, [(0.50, 0.02), (0.62, 0.22), (0.50, 0.36), (0.38, 0.22)])
    elif shape == "immaculate_lower_gem":
        _poly(draw, bounds, [(0.50, 0.70), (0.66, 0.88), (0.50, 0.99), (0.34, 0.88)])

    elif shape == "parallel_nodes":
        for box in [(0.20, 0.18, 0.34, 0.32), (0.66, 0.18, 0.80, 0.32), (0.20, 0.64, 0.34, 0.78), (0.66, 0.64, 0.80, 0.78), (0.43, 0.41, 0.57, 0.55)]:
            _ellipse(draw, bounds, box)
    elif shape == "parallel_plate":
        _rectangle(draw, bounds, (0.18, 0.20, 0.82, 0.80))
    elif shape == "parallel_lower_diamond":
        _poly(draw, bounds, [(0.50, 0.78), (0.60, 0.90), (0.50, 0.99), (0.40, 0.90)])

    elif shape == "captain_helmet":
        _poly(draw, bounds, [(0.30, 0.32), (0.50, 0.18), (0.70, 0.32), (0.66, 0.68), (0.50, 0.84), (0.34, 0.68)])
    elif shape == "captain_side_wings":
        _poly(draw, bounds, [(0.12, 0.46), (0.32, 0.34), (0.30, 0.72), (0.12, 0.68)])
        _poly(draw, bounds, [(0.88, 0.46), (0.68, 0.34), (0.70, 0.72), (0.88, 0.68)])
    elif shape == "captain_left_wing":
        _poly(draw, bounds, [(0.12, 0.46), (0.32, 0.34), (0.30, 0.72), (0.12, 0.68)])
    elif shape == "captain_right_wing":
        _poly(draw, bounds, [(0.88, 0.46), (0.68, 0.34), (0.70, 0.72), (0.88, 0.68)])
    elif shape == "captain_crown":
        _poly(draw, bounds, [(0.42, 0.10), (0.50, 0.00), (0.58, 0.10), (0.55, 0.22), (0.45, 0.22)])

    elif shape == "admiral_spire":
        _poly(draw, bounds, [(0.50, 0.00), (0.62, 0.60), (0.50, 0.94), (0.38, 0.60)])
    elif shape == "admiral_nodes":
        for box in [(0.20, 0.45, 0.34, 0.59), (0.66, 0.45, 0.80, 0.59), (0.43, 0.76, 0.57, 0.90)]:
            _ellipse(draw, bounds, box)
    elif shape == "admiral_shell":
        _ring(draw, bounds, (0.10, 0.12, 0.90, 0.88), (0.33, 0.28, 0.67, 0.72))
    elif shape == "admiral_left_shell":
        _poly(draw, bounds, [(0.12, 0.22), (0.37, 0.12), (0.46, 0.30), (0.39, 0.82), (0.13, 0.76), (0.08, 0.48)])
    elif shape == "admiral_right_shell":
        _poly(draw, bounds, [(0.88, 0.22), (0.63, 0.12), (0.54, 0.30), (0.61, 0.82), (0.87, 0.76), (0.92, 0.48)])

    elif shape == "bench_pillars":
        for box in [(0.22, 0.32, 0.32, 0.72), (0.45, 0.28, 0.55, 0.75), (0.68, 0.32, 0.78, 0.72)]:
            _rectangle(draw, bounds, box)
    elif shape == "bench_crystals":
        for x in [0.24, 0.50, 0.76]:
            _poly(draw, bounds, [(x, 0.05), (x + 0.07, 0.28), (x, 0.40), (x - 0.07, 0.28)])
    elif shape == "bench_base":
        _rectangle(draw, bounds, (0.18, 0.72, 0.82, 0.88))

    elif shape == "check_face":
        _poly(draw, bounds, [(0.26, 0.52), (0.40, 0.40), (0.50, 0.58), (0.76, 0.28), (0.84, 0.38), (0.50, 0.78)])
    elif shape == "check_ring":
        _ring(draw, bounds, (0.18, 0.13, 0.82, 0.87), (0.34, 0.30, 0.66, 0.70))
    elif shape == "check_bottom":
        _poly(draw, bounds, [(0.50, 0.74), (0.62, 0.92), (0.50, 0.99), (0.38, 0.92)])

    elif shape == "elite_cross_blades":
        _poly(draw, bounds, [(0.10, 0.18), (0.90, 0.82), (0.80, 0.92), (0.00, 0.30)])
        _poly(draw, bounds, [(0.90, 0.18), (0.10, 0.82), (0.20, 0.92), (1.00, 0.30)])
    elif shape == "elite_left_blade":
        _poly(draw, bounds, [(0.10, 0.18), (0.90, 0.82), (0.80, 0.92), (0.00, 0.30)])
    elif shape == "elite_right_blade":
        _poly(draw, bounds, [(0.90, 0.18), (0.10, 0.82), (0.20, 0.92), (1.00, 0.30)])
    elif shape == "elite_core_check":
        _poly(draw, bounds, [(0.25, 0.54), (0.40, 0.42), (0.50, 0.60), (0.73, 0.28), (0.84, 0.38), (0.50, 0.82)])
    elif shape == "elite_side_crystals":
        _ellipse(draw, bounds, (0.14, 0.32, 0.30, 0.48))
        _ellipse(draw, bounds, (0.70, 0.32, 0.86, 0.48))

    elif shape == "apex_wings":
        _poly(draw, bounds, [(0.08, 0.16), (0.39, 0.28), (0.38, 0.90), (0.14, 0.72)])
        _poly(draw, bounds, [(0.92, 0.16), (0.61, 0.28), (0.62, 0.90), (0.86, 0.72)])
    elif shape == "apex_left_wing":
        _poly(draw, bounds, [(0.08, 0.16), (0.39, 0.28), (0.38, 0.90), (0.14, 0.72)])
    elif shape == "apex_right_wing":
        _poly(draw, bounds, [(0.92, 0.16), (0.61, 0.28), (0.62, 0.90), (0.86, 0.72)])
    elif shape == "apex_check":
        _poly(draw, bounds, [(0.24, 0.54), (0.39, 0.43), (0.50, 0.61), (0.76, 0.25), (0.84, 0.36), (0.50, 0.84)])
    elif shape == "apex_top_prism":
        _poly(draw, bounds, [(0.50, 0.04), (0.64, 0.35), (0.50, 0.56), (0.36, 0.35)])

    elif shape == "jurisdiction_orbit":
        _ring(draw, bounds, (0.04, 0.10, 0.96, 0.90), (0.30, 0.32, 0.70, 0.68))
    elif shape == "jurisdiction_planets":
        for box in [(0.08, 0.72, 0.24, 0.88), (0.76, 0.20, 0.92, 0.36), (0.45, 0.82, 0.57, 0.94)]:
            _ellipse(draw, bounds, box)
    elif shape == "jurisdiction_court":
        _rectangle(draw, bounds, (0.25, 0.28, 0.75, 0.72))

    elif shape == "spectrum_columns":
        for box in [(0.24, 0.35, 0.32, 0.77), (0.38, 0.35, 0.46, 0.77), (0.54, 0.35, 0.62, 0.77), (0.68, 0.35, 0.76, 0.77)]:
            _rectangle(draw, bounds, box)
    elif shape == "spectrum_roof":
        _poly(draw, bounds, [(0.14, 0.32), (0.50, 0.08), (0.86, 0.32), (0.76, 0.42), (0.24, 0.42)])
    elif shape == "spectrum_diamond":
        _poly(draw, bounds, [(0.50, 0.76), (0.61, 0.89), (0.50, 0.99), (0.39, 0.89)])

    elif shape == "night_laptop":
        _rectangle(draw, bounds, (0.35, 0.52, 0.67, 0.77))
    elif shape == "night_frame":
        _ring(draw, bounds, (0.12, 0.10, 0.88, 0.88), (0.25, 0.24, 0.75, 0.76))
    elif shape == "night_bottom_gem":
        _poly(draw, bounds, [(0.50, 0.79), (0.60, 0.91), (0.50, 0.99), (0.40, 0.91)])

    elif shape == "midnight_screen_tiles":
        for box in [(0.18, 0.38, 0.34, 0.53), (0.66, 0.38, 0.82, 0.53), (0.18, 0.56, 0.34, 0.71), (0.66, 0.56, 0.82, 0.71)]:
            _rectangle(draw, bounds, box)
    elif shape == "midnight_outer_ring":
        _ring(draw, bounds, (0.10, 0.10, 0.90, 0.90), (0.26, 0.26, 0.74, 0.76))
    elif shape == "midnight_moon_window":
        _ellipse(draw, bounds, (0.36, 0.08, 0.64, 0.36))

    elif shape == "lni_document_face":
        _poly(draw, bounds, [(0.34, 0.18), (0.72, 0.30), (0.68, 0.76), (0.40, 0.86), (0.28, 0.60)])
    elif shape == "lni_circuit_node":
        _ellipse(draw, bounds, (0.46, 0.46, 0.58, 0.58))
    elif shape == "docket_diamond_frame":
        _poly(draw, bounds, [(0.50, 0.06), (0.87, 0.50), (0.50, 0.94), (0.13, 0.50)])
        _poly(draw, bounds, [(0.50, 0.26), (0.70, 0.50), (0.50, 0.74), (0.30, 0.50)])
    elif shape == "docket_left_rail":
        _poly(draw, bounds, [(0.10, 0.32), (0.30, 0.16), (0.43, 0.28), (0.28, 0.78), (0.10, 0.68)])
    elif shape == "docket_right_rail":
        _poly(draw, bounds, [(0.90, 0.32), (0.70, 0.16), (0.57, 0.28), (0.72, 0.78), (0.90, 0.68)])
    elif shape == "docket_top_prong":
        _poly(draw, bounds, [(0.50, 0.02), (0.62, 0.22), (0.50, 0.34), (0.38, 0.22)])
    elif shape == "docket_bottom_prong":
        _poly(draw, bounds, [(0.50, 0.98), (0.62, 0.78), (0.50, 0.66), (0.38, 0.78)])
    elif shape == "docket_center_gem":
        _poly(draw, bounds, [(0.50, 0.22), (0.68, 0.50), (0.50, 0.78), (0.32, 0.50)])
    elif shape == "queue_shutters":
        for y in [0.18, 0.32, 0.46, 0.60]:
            _poly(draw, bounds, [(0.20, y), (0.86, y + 0.03), (0.78, y + 0.13), (0.12, y + 0.10)])
    elif shape == "archive_vault_dial":
        _ring(draw, bounds, (0.34, 0.28, 0.66, 0.60), (0.43, 0.37, 0.57, 0.51))
    elif shape == "archive_side_locks":
        _rectangle(draw, bounds, (0.08, 0.36, 0.26, 0.68))
        _rectangle(draw, bounds, (0.74, 0.36, 0.92, 0.68))
    elif shape == "archive_left_lock":
        _rectangle(draw, bounds, (0.08, 0.36, 0.26, 0.68))
    elif shape == "archive_right_lock":
        _rectangle(draw, bounds, (0.74, 0.36, 0.92, 0.68))
    elif shape == "final_crystal":
        _poly(draw, bounds, [(0.50, 0.10), (0.66, 0.50), (0.50, 0.88), (0.34, 0.50)])
    elif shape == "final_side_armor":
        _poly(draw, bounds, [(0.10, 0.22), (0.36, 0.26), (0.36, 0.80), (0.12, 0.70)])
        _poly(draw, bounds, [(0.90, 0.22), (0.64, 0.26), (0.64, 0.80), (0.88, 0.70)])
    elif shape == "final_left_armor":
        _poly(draw, bounds, [(0.10, 0.22), (0.36, 0.26), (0.36, 0.80), (0.12, 0.70)])
    elif shape == "final_right_armor":
        _poly(draw, bounds, [(0.90, 0.22), (0.64, 0.26), (0.64, 0.80), (0.88, 0.70)])
    elif shape == "six_router_nodes":
        for box in [(0.24, 0.16, 0.38, 0.30), (0.62, 0.16, 0.76, 0.30), (0.24, 0.43, 0.38, 0.57), (0.62, 0.43, 0.76, 0.57), (0.24, 0.70, 0.38, 0.84), (0.62, 0.70, 0.76, 0.84)]:
            _ellipse(draw, bounds, box)
    elif shape == "six_router_core":
        _ellipse(draw, bounds, (0.42, 0.42, 0.58, 0.58))

    else:
        _ellipse(draw, bounds, (0.32, 0.32, 0.68, 0.68))

    return mask.filter(ImageFilter.GaussianBlur(0.28))


def _protected_anchor_mask(image: Image.Image, effect_key: str | None, shape: str) -> Image.Image:
    mask = Image.new("L", (SIZE, SIZE), 0)
    if not effect_key:
        return mask

    alpha = image.getchannel("A")
    for anchor_shape in PROTECTED_ANCHORS_BY_EFFECT.get(effect_key, ()):
        if anchor_shape == shape:
            continue
        anchor = ImageChops.multiply(_shape_mask(_badge_bounds(image), anchor_shape), alpha)
        anchor = anchor.filter(ImageFilter.MaxFilter(7)).point(lambda value: 255 if value > 2 else 0)
        mask = ImageChops.lighter(mask, anchor)
    return mask


PRECISION_CAP_SHAPES = {
    "precision_top_cylinder",
    "precision_left_cylinder",
    "precision_right_cylinder",
}


PRECISION_CAP_CENTERS = {
    "precision_top_cylinder": (0.50, 0.32),
    "precision_left_cylinder": (0.27, 0.63),
    "precision_right_cylinder": (0.73, 0.63),
}


def _precision_warm_frame_mask(image: Image.Image) -> Image.Image:
    """Find brass/gold frame pixels so Precision caps can animate as their own layer."""
    red, green, blue, alpha = image.split()
    visible = alpha.point(lambda value: 255 if value > 8 else 0)
    red_gate = red.point(lambda value: 255 if value > 72 else 0)
    green_gate = green.point(lambda value: 255 if value > 45 else 0)
    red_over_blue = ImageChops.subtract(red, blue).point(lambda value: 255 if value > 24 else 0)
    green_over_blue = ImageChops.subtract(green, blue).point(lambda value: 255 if value > 8 else 0)

    warm = ImageChops.multiply(visible, red_gate)
    warm = ImageChops.multiply(warm, green_gate)
    warm = ImageChops.multiply(warm, red_over_blue)
    warm = ImageChops.multiply(warm, green_over_blue)
    return warm.filter(ImageFilter.MaxFilter(3))


def _precision_cap_territory_mask(image: Image.Image, shape: str) -> Image.Image:
    bounds = _badge_bounds(image)
    ordered_shapes = (
        "precision_top_cylinder",
        "precision_left_cylinder",
        "precision_right_cylinder",
    )
    centers = {
        cap_shape: _pt(bounds, *center)
        for cap_shape, center in PRECISION_CAP_CENTERS.items()
    }
    territory = Image.new("L", (SIZE, SIZE), 0)
    pixels = territory.load()

    for y in range(SIZE):
        for x in range(SIZE):
            winner = min(
                ordered_shapes,
                key=lambda cap_shape: (
                    (x - centers[cap_shape][0]) ** 2 + (y - centers[cap_shape][1]) ** 2,
                    ordered_shapes.index(cap_shape),
                ),
            )
            if winner == shape:
                pixels[x, y] = 255

    return territory


def _precision_cap_layer_mask(image: Image.Image, shape: str, mask: Image.Image) -> Image.Image:
    warm_frame = _precision_warm_frame_mask(image)
    territory = _precision_cap_territory_mask(image, shape)
    cap = ImageChops.subtract(mask, warm_frame)
    cap = ImageChops.multiply(cap, territory)
    cap = cap.filter(ImageFilter.GaussianBlur(0.35))
    cap = ImageChops.multiply(cap, territory)
    return ImageChops.subtract(cap, warm_frame.filter(ImageFilter.MaxFilter(3)))


def _component(image: Image.Image, shape: str, effect_key: str | None = None, protect_anchors: bool = False) -> Image.Image:
    alpha = image.getchannel("A")
    mask = ImageChops.multiply(_shape_mask(_badge_bounds(image), shape), alpha)
    if shape in PRECISION_CAP_SHAPES:
        mask = _precision_cap_layer_mask(image, shape, mask)
    if protect_anchors:
        mask = ImageChops.subtract(mask, _protected_anchor_mask(image, effect_key, shape))
    piece = image.copy()
    piece.putalpha(mask)
    return piece


def _pivot_point(bounds: tuple[int, int, int, int], pivot: str) -> tuple[float, float]:
    pivots = {
        "center": (0.50, 0.50),
        "top": (0.50, 0.12),
        "bottom": (0.50, 0.88),
        "left": (0.18, 0.50),
        "right": (0.82, 0.50),
        "upper_left": (0.24, 0.24),
        "upper_right": (0.76, 0.24),
        "lower_left": (0.24, 0.76),
        "lower_right": (0.76, 0.76),
        "upper_center": (0.50, 0.28),
        "lower_center": (0.50, 0.72),
        "precision_top_cap": (0.50, 0.32),
        "precision_left_cap": (0.27, 0.63),
        "precision_right_cap": (0.73, 0.63),
    }
    return _pt(bounds, *pivots.get(pivot, pivots["center"]))


def _transform_layer(layer: Image.Image, dx=0.0, dy=0.0, angle=0.0, pivot=(SIZE / 2, SIZE / 2), scale: float = 1.0) -> Image.Image:
    rotated = layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=pivot, fillcolor=(0, 0, 0, 0))
    scale = max(0.20, float(scale or 1.0))
    inv_scale = 1.0 / scale
    pivot_x, pivot_y = pivot
    return rotated.transform(
        (SIZE, SIZE),
        Image.Transform.AFFINE,
        (
            inv_scale,
            0,
            pivot_x - (dx + pivot_x) * inv_scale,
            0,
            inv_scale,
            pivot_y - (dy + pivot_y) * inv_scale,
        ),
        resample=Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )


def _shadow_base(layer: Image.Image) -> Image.Image:
    shadow_alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(1.7))
    shadow_alpha = shadow_alpha.point(lambda value: round(value * 0.30))
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha)
    return shadow


def _edge_light_base(layer: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
    edge_alpha = layer.getchannel("A").filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(0.55))
    edge_alpha = edge_alpha.point(lambda value: round(value * 0.34))
    edge = Image.new("RGBA", (SIZE, SIZE), (*tint, 0))
    edge.putalpha(edge_alpha)
    return edge


def _opacity(layer: Image.Image, amount: float) -> Image.Image:
    amount = max(0.0, min(1.0, amount))
    if amount >= 0.995:
        return layer
    faded = layer.copy()
    faded.putalpha(layer.getchannel("A").point(lambda value: round(value * amount)))
    return faded


def _clip_layer_alpha(layer: Image.Image, clip_alpha: Image.Image) -> Image.Image:
    clipped = layer.copy()
    clipped.putalpha(ImageChops.multiply(clipped.getchannel("A"), clip_alpha))
    return clipped


def _erase_piece(base: Image.Image, piece: Image.Image, amount: float) -> None:
    alpha = base.getchannel("A")
    erase = piece.getchannel("A").point(lambda value: round(value * amount))
    base.putalpha(ImageChops.subtract(alpha, erase))


def _curve_amount(position: float, motion: Motion) -> float:
    if position < motion.start or position > motion.end:
        return 0.0
    span = max(0.001, motion.end - motion.start)
    t = (position - motion.start) / span
    bell = math.sin(math.pi * t)

    if motion.curve == "hinge":
        amount = bell ** 1.20
    elif motion.curve == "servo":
        amount = (bell ** 1.35) * (0.96 + 0.04 * math.sin(8 * math.pi * t))
    elif motion.curve == "ratchet":
        amount = (bell ** 1.10) * (0.92 + 0.08 * abs(math.sin(6 * math.pi * t)))
    elif motion.curve == "breathe":
        amount = bell ** 1.85
    elif motion.curve == "snap":
        amount = (bell ** 0.86) * (0.97 + 0.03 * math.sin(10 * math.pi * t))
    else:
        amount = bell ** 1.55

    return max(0.0, min(1.0, amount))


VENT_STYLE_BY_EFFECT = {
    "first_route_gate": "plasma",
    "routing_spark_core_latches": "electric",
    "brief_storm_paper_shutters": "storm",
    "hundred_club_heat_vents": "ember",
    "thousand_crown_lock": "gold",
    "calendar_tick_shutters": "ice",
    "docket_warlord_armor_lock": "ember",
    "legendary_circuit_calibration": "electric",
    "clean_sweep_guardian_clamps": "mint",
    "precision_frost_servo": "ice",
    "audit_vault_lock": "dust",
    "immaculate_crystal_prongs": "crystal",
    "parallel_rail_shift": "electric",
    "captain_beacon_panels": "air",
    "admiral_command_ring": "electric_gold",
    "full_bench_docking": "plasma",
    "no_misses_reticle_lock": "spark",
    "no_misses_elite_seal": "purple_spark",
    "no_misses_apex_unfold": "gold",
    "court_hopper_portal_gate": "plasma",
    "jurisdiction_swarm_grid": "orbital",
    "full_spectrum_segment_ring": "rainbow",
    "night_shift_moon_panels": "vapor",
    "midnight_terminal_locks": "neon",
    "title_lni_whisperer_parts": "neon",
    "title_docket_diva_parts": "prism",
    "title_queue_slayer_parts": "purple_spark",
    "title_archive_authority_parts": "dust",
    "title_final_reviewer_parts": "plasma",
    "title_six_router_menace_parts": "electric",
}


VENT_PALETTES = {
    "air": ((156, 236, 255), (225, 255, 255)),
    "crystal": ((172, 233, 255), (239, 255, 255)),
    "dust": ((174, 151, 115), (230, 213, 170)),
    "electric": ((82, 230, 255), (178, 116, 255)),
    "electric_gold": ((92, 229, 255), (255, 216, 105)),
    "ember": ((255, 127, 67), (255, 218, 114)),
    "gold": ((255, 195, 74), (255, 236, 151)),
    "ice": ((145, 231, 255), (231, 255, 255)),
    "mint": ((102, 255, 183), (206, 255, 221)),
    "neon": ((83, 238, 255), (209, 103, 255)),
    "orbital": ((255, 206, 76), (109, 239, 255)),
    "plasma": ((99, 227, 255), (185, 97, 255)),
    "prism": ((255, 145, 227), (255, 221, 119)),
    "purple_spark": ((204, 106, 255), (255, 170, 232)),
    "rainbow": ((255, 123, 190), (111, 246, 255)),
    "spark": ((255, 214, 116), (162, 236, 255)),
    "storm": ((137, 104, 255), (169, 238, 255)),
    "vapor": ((159, 188, 255), (231, 241, 255)),
}


VENT_LINGER_FRAMES_BY_STYLE = {
    "air": 6,
    "crystal": 4,
    "dust": 5,
    "electric": 3,
    "electric_gold": 4,
    "ember": 5,
    "gold": 5,
    "ice": 4,
    "mint": 6,
    "neon": 4,
    "orbital": 4,
    "plasma": 4,
    "prism": 5,
    "purple_spark": 4,
    "rainbow": 5,
    "spark": 4,
    "storm": 4,
    "vapor": 7,
}


GAP_SCALE_BY_EFFECT = {
    "brief_storm_paper_shutters": 1.0,
    "no_misses_elite_seal": 2.10,
}


MIN_GAP_BY_EFFECT = {
    "brief_storm_paper_shutters": 0.0,
    "no_misses_elite_seal": 2.6,
}


FULL_ERASE_EFFECTS = {"precision_frost_servo"}


CAVITY_COLORS_BY_STYLE = {
    "air": ((8, 25, 38), (136, 236, 255)),
    "crystal": ((9, 22, 39), (178, 236, 255)),
    "dust": ((31, 24, 17), (224, 190, 125)),
    "electric": ((4, 14, 31), (82, 230, 255)),
    "electric_gold": ((5, 16, 28), (255, 215, 105)),
    "ember": ((36, 9, 5), (255, 140, 68)),
    "gold": ((36, 24, 5), (255, 216, 94)),
    "ice": ((6, 21, 35), (162, 236, 255)),
    "mint": ((3, 26, 20), (102, 255, 183)),
    "neon": ((13, 8, 35), (202, 96, 255)),
    "orbital": ((19, 18, 28), (111, 242, 255)),
    "plasma": ((13, 7, 35), (174, 98, 255)),
    "prism": ((26, 10, 33), (255, 161, 229)),
    "purple_spark": ((20, 7, 35), (214, 106, 255)),
    "rainbow": ((16, 14, 32), (111, 246, 255)),
    "spark": ((30, 20, 8), (255, 214, 116)),
    "storm": ((10, 8, 35), (137, 104, 255)),
    "vapor": ((13, 17, 35), (170, 198, 255)),
}


PROTECTED_ANCHORS_BY_EFFECT = {
    "first_route_gate": ("portal_core", "portal_top_crystal"),
    "routing_spark_core_latches": ("spark_center_star",),
    "hundred_club_heat_vents": ("stack_core",),
    "thousand_crown_lock": ("crown_center_gem",),
    "legendary_circuit_calibration": ("circuit_crystal",),
    "clean_sweep_guardian_clamps": ("clean_bottom_gem",),
    "parallel_rail_shift": ("parallel_lower_diamond",),
    "admiral_command_ring": ("admiral_spire",),
    "no_misses_elite_seal": ("elite_core_check", "elite_side_crystals"),
    "no_misses_apex_unfold": ("apex_top_prism",),
    "immaculate_crystal_prongs": ("immaculate_top_crystal", "immaculate_lower_gem"),
    "full_bench_docking": ("bench_crystals",),
    "court_hopper_portal_gate": ("portal_top_crystal",),
    "night_shift_moon_panels": ("night_bottom_gem",),
    "title_docket_diva_parts": ("docket_center_gem",),
    "title_queue_slayer_parts": ("clean_bottom_gem",),
    "title_final_reviewer_parts": ("final_crystal",),
}


def _noise(seed: float) -> float:
    return math.sin(seed * 12.9898 + 78.233) % 1.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _smoothstep(value: float) -> float:
    value = _clamp(value)
    return value * value * (3.0 - 2.0 * value)


def _motion_frame_values(effect_key: str, motion: Motion, amount: float, frame: int, index: int):
    if effect_key == "precision_frost_servo" and motion.shape in PRECISION_CAP_SHAPES:
        position = frame / max(1, FRAMES - 1)
        span = max(0.001, motion.end - motion.start)
        t = _clamp((position - motion.start) / span)
        lift_up = _smoothstep(t / 0.22)
        settle_down = _smoothstep((t - 0.78) / 0.22)
        lift_amount = _clamp(lift_up * (1.0 - settle_down))
        spin_progress = _smoothstep((t - 0.18) / 0.64)
        return (
            motion.dx * lift_amount,
            motion.dy * lift_amount,
            motion.angle * spin_progress,
            1.0 + max(-0.40, motion.scale) * lift_amount,
        )

    gap_scale = 1.0 if not motion.erase else GAP_SCALE_BY_EFFECT.get(effect_key, 3.35)
    base_dx = motion.dx * gap_scale
    base_dy = motion.dy * gap_scale
    if motion.erase:
        min_gap = MIN_GAP_BY_EFFECT.get(effect_key, 4.4)
        peak_gap = math.hypot(base_dx, base_dy)
        if 0.08 < peak_gap < min_gap:
            boost = min_gap / peak_gap
            base_dx *= boost
            base_dy *= boost
    dx = base_dx * amount
    dy = base_dy * amount
    angle = motion.angle * amount * (1.0 if effect_key == "brief_storm_paper_shutters" else 1.04)

    if motion.erase and amount > 0.03:
        travel = math.hypot(base_dx, base_dy)
        seed = sum(ord(ch) for ch in f"{effect_key}:{motion.shape}:{index}") * 0.017
        grind = math.sin(frame * 2.65 + seed) * 0.13 * amount
        settle = math.sin(frame * 1.35 + seed * 1.7) * 0.07 * amount
        angle += math.sin(frame * 2.1 + seed * 2.3) * 0.045 * amount

        if travel > 0.08:
            tx, ty = base_dx / travel, base_dy / travel
            px, py = -ty, tx
            dx += px * grind + tx * settle
            dy += py * grind + ty * settle

    scale = 1.0 + max(-0.40, motion.scale) * amount
    return dx, dy, angle, scale


def _seam_emitters(piece: Image.Image, dx: float, dy: float, seed: float = 0.0, shape: str = ""):
    bbox = piece.getchannel("A").getbbox()
    if not bbox:
        return []
    left, top, right, bottom = bbox
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    width = right - left
    height = bottom - top

    if shape.startswith("precision_") and shape.endswith("_cylinder"):
        radius_x = width / 2
        radius_y = height / 2
        base_angles = (220, 270, 320, 90)
        emitters = []
        for index, degrees in enumerate(base_angles):
            jitter = (_noise(seed + index * 7.3) - 0.5) * 12
            angle = math.radians(degrees + jitter)
            x = cx + math.cos(angle) * radius_x * 0.84 + dx
            y = cy + math.sin(angle) * radius_y * 0.84 + dy
            nx = math.cos(angle)
            ny = math.sin(angle)
            emitters.append((x, y, nx, ny))
        return emitters

    count = 1
    if max(width, height) > 92:
        count = 2
    if max(width, height) > 142:
        count = 3

    emitters = []

    if abs(dx) >= abs(dy) and abs(dx) > 0.08:
        x = left + dx if dx > 0 else right + dx
        nx = -1 if dx > 0 else 1
        for index in range(count):
            t = (index + 1) / (count + 1)
            jitter = (_noise(seed + index * 4.1) - 0.5) * 0.16
            y = top + height * max(0.18, min(0.82, t + jitter)) + dy
            emitters.append((x, y, nx, 0))
        return emitters
    if abs(dy) > 0.08:
        y = top + dy if dy > 0 else bottom + dy
        ny = -1 if dy > 0 else 1
        for index in range(count):
            t = (index + 1) / (count + 1)
            jitter = (_noise(seed + index * 4.1) - 0.5) * 0.16
            x = left + width * max(0.18, min(0.82, t + jitter)) + dx
            emitters.append((x, y, 0, ny))
        return emitters
    return [(cx, cy, 0, -1)]


def _seam_point(piece: Image.Image, dx: float, dy: float):
    emitters = _seam_emitters(piece, dx, dy)
    return emitters[len(emitters) // 2] if emitters else None


def _draw_soft_glow(layer: Image.Image, x: float, y: float, color, amount: float, radius: float):
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    alpha = round(105 * amount)
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(*color, alpha))
    layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius * 0.48)))


def _soft_edge_fade(layer: Image.Image) -> Image.Image:
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([8, 8, SIZE - 9, SIZE - 9], radius=20, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(4.0))
    hard_margin = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(hard_margin).rectangle([3, 3, SIZE - 4, SIZE - 4], fill=255)
    mask = ImageChops.multiply(mask, hard_margin)
    faded = layer.copy()
    faded.putalpha(ImageChops.multiply(faded.getchannel("A"), mask))
    return faded


def _draw_jagged(draw: ImageDraw.ImageDraw, x: float, y: float, nx: float, ny: float, color, alpha: int, seed: float, length: float):
    px, py = -ny, nx
    points = []
    for step in range(5):
        t = step / 4
        jitter = (_noise(seed + step * 3.7) - 0.5) * 8
        points.append((x + nx * length * t + px * jitter, y + ny * length * t + py * jitter))
    draw.line(points, fill=(*color, alpha), width=2)


def _inner_cavity_layer(effect_key: str, active_layers: list[tuple]) -> Image.Image:
    style = VENT_STYLE_BY_EFFECT.get(effect_key, "spark")
    dark, glow = CAVITY_COLORS_BY_STYLE.get(style, CAVITY_COLORS_BY_STYLE["spark"])
    cavity = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    for index, (motion, piece, _shadow, _edge, _pivot, amount, dx, dy, _angle, _scale) in enumerate(active_layers):
        if not motion.erase or amount <= 0.05:
            continue

        piece_alpha = piece.getchannel("A")
        core_alpha = piece_alpha.filter(ImageFilter.GaussianBlur(0.65))
        core_alpha = core_alpha.point(lambda value, a=amount: round(value * min(0.78, 0.34 + a * 0.44)))
        pocket = Image.new("RGBA", (SIZE, SIZE), (*dark, 0))
        pocket.putalpha(core_alpha)
        cavity.alpha_composite(pocket)

        edge_alpha = piece_alpha.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1.2))
        edge_alpha = edge_alpha.point(lambda value, a=amount: round(value * min(0.68, 0.18 + a * 0.50)))
        rim = Image.new("RGBA", (SIZE, SIZE), (*glow, 0))
        rim.putalpha(edge_alpha)
        cavity.alpha_composite(rim)

        seed = sum(ord(ch) for ch in f"{effect_key}:{motion.shape}:cavity") + index * 19.0
        for vent_index, (x, y, nx, ny) in enumerate(_seam_emitters(piece, dx, dy, seed, motion.shape)):
            _draw_soft_glow(cavity, x - nx * 2.0, y - ny * 2.0, glow, min(0.9, amount * 0.82), 12 + vent_index * 2)

    return _soft_edge_fade(cavity)


def _draw_crack_vent(
    layer: Image.Image,
    style: str,
    x: float,
    y: float,
    nx: float,
    ny: float,
    amount: float,
    seed: float,
    linger: float = 1.0,
    age: int = 0,
):
    primary, secondary = VENT_PALETTES.get(style, VENT_PALETTES["spark"])
    draw = ImageDraw.Draw(layer)
    px, py = -ny, nx
    x -= nx * (3.0 + amount * 2.0)
    y -= ny * (3.0 + amount * 2.0)
    outward = age * (1.6 + _noise(seed + 2.2) * 1.5)
    lift = age * (1.4 + _noise(seed + 3.1) * 1.8)
    x = x + nx * outward + px * ((_noise(seed + 4.4) - 0.5) * age * 1.2)
    y = y + ny * outward
    if style in {"ember", "gold", "spark", "purple_spark", "rainbow", "vapor", "air", "mint", "dust"}:
        y -= lift

    intensity = min(1.0, 0.18 + amount * 1.10) * max(0.0, min(1.0, linger))
    if intensity <= 0.02:
        return

    if style in {"electric", "electric_gold", "plasma", "storm", "neon", "prism"}:
        _draw_soft_glow(layer, x, y, secondary, intensity, 15 + age * 0.8)
        for i in range(3):
            spread = (_noise(seed + i) - 0.5) * 10
            _draw_jagged(
                draw,
                x + px * spread,
                y + py * spread,
                nx * (0.65 + _noise(seed + 9 + i) * 0.40),
                ny * (0.65 + _noise(seed + 14 + i) * 0.40),
                primary if i == 0 else secondary,
                round(190 * intensity),
                seed + i * 8.4,
                (15 + _noise(seed + i * 11) * 11) * (1.0 + age * 0.08),
            )
        return

    if style in {"ember", "gold", "spark", "purple_spark", "rainbow"}:
        _draw_soft_glow(layer, x, y, secondary, intensity, 12 + age * 0.9)
        for i in range(6):
            side = (_noise(seed + i * 2.1) - 0.5) * 12
            length = 4 + _noise(seed + i * 5.3) * 10 + age * 0.8
            sx = x + px * side
            sy = y + py * side
            ex = sx + nx * length + px * ((_noise(seed + i * 7.1) - 0.5) * (5 + age))
            ey = sy + ny * length + py * ((_noise(seed + i * 7.6) - 0.5) * (5 + age)) - age * 0.9
            color = primary if i % 2 == 0 else secondary
            alpha = round((115 + 75 * _noise(seed + i)) * intensity)
            if i % 3 == 0:
                draw.line([(sx, sy), (ex, ey)], fill=(*color, alpha), width=1)
            else:
                r = 1.0 + _noise(seed + i * 1.7) * 1.4
                draw.ellipse([ex - r, ey - r, ex + r, ey + r], fill=(*color, alpha))
        return

    if style in {"vapor", "air", "mint"}:
        haze = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        haze_draw = ImageDraw.Draw(haze)
        for i in range(5):
            side = (_noise(seed + i * 3.2) - 0.5) * 16
            drift = 6 + _noise(seed + i * 4.4) * 14 + age * 2.1
            r = 4 + _noise(seed + i * 6.1) * 6 + age * 0.9
            hx = x + px * side + nx * drift
            hy = y + py * side + ny * drift
            haze_draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=(*primary, round(66 * intensity)))
        layer.alpha_composite(haze.filter(ImageFilter.GaussianBlur(2.2 + age * 0.22)))
        return

    if style in {"ice", "crystal"}:
        _draw_soft_glow(layer, x, y, primary, intensity, 11 + age * 0.35)
        for i in range(5):
            side = (_noise(seed + i * 2.6) - 0.5) * 12
            length = 6 + _noise(seed + i * 5.1) * 10 + age * 0.5
            sx = x + px * side
            sy = y + py * side
            ex = sx + nx * length
            ey = sy + ny * length
            draw.line([(sx, sy), (ex, ey)], fill=(*secondary, round(175 * intensity)), width=1)
            if i % 2 == 0:
                r = 1.0 + _noise(seed + i * 4.7) * 1.3
                draw.ellipse([ex - r, ey - r, ex + r, ey + r], fill=(*primary, round(130 * intensity)))
        return

    if style == "dust":
        _draw_soft_glow(layer, x, y, secondary, intensity * 0.65, 10)
        for i in range(8):
            side = (_noise(seed + i * 1.9) - 0.5) * 14
            drift = 4 + _noise(seed + i * 3.1) * 11 + age * 1.1
            size = 1.2 + _noise(seed + i * 2.5) * 2.6
            cx = x + px * side + nx * drift
            cy = y + py * side + ny * drift + age * 0.5
            color = primary if i % 2 else secondary
            draw.rectangle([cx - size, cy - size, cx + size, cy + size], fill=(*color, round(145 * intensity)))


def _crack_vent_layer(effect_key: str, layers: list[tuple], frame: int) -> Image.Image:
    if frame <= 0 or frame >= FRAMES - 1:
        return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    style = VENT_STYLE_BY_EFFECT.get(effect_key, "spark")
    max_age = VENT_LINGER_FRAMES_BY_STYLE.get(style, 4)
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    for age in range(max_age + 1):
        sample_frame = frame - age
        if sample_frame <= 0:
            continue
        position = sample_frame / max(1, FRAMES - 1)
        age_fade = (1.0 - age / (max_age + 1)) ** (0.95 if style in {"vapor", "air", "mint"} else 1.25)
        for index, (motion, piece, _shadow, _edge, _pivot) in enumerate(layers):
            if not motion.erase:
                continue
            amount = _curve_amount(position, motion)
            if amount < 0.12:
                continue
            dx, dy, _angle, _scale = _motion_frame_values(effect_key, motion, amount, sample_frame, index)
            seed = sum(ord(ch) for ch in f"{effect_key}:{motion.shape}") + sample_frame * 5.37 + index * 17.0
            for vent_index, (x, y, nx, ny) in enumerate(_seam_emitters(piece, dx, dy, seed, motion.shape)):
                _draw_crack_vent(layer, style, x, y, nx, ny, amount, seed + vent_index * 29.0, age_fade, age)
    return _soft_edge_fade(layer)


EFFECT_SPECS: dict[str, EffectSpec] = {
    "first_route_gate": EffectSpec("achievement_first_route.png", (
        m("portal_left_post", -1.0, 0.1, -0.35, 0.10, 0.74, "hinge", "left"),
        m("portal_right_post", 1.0, 0.1, 0.35, 0.16, 0.80, "hinge", "right"),
        m("portal_core", 0.0, 0.9, 0.0, 0.38, 0.94, "servo", "bottom", erase=False, opacity=0.35, edge=0.46),
        m("portal_top_crystal", 0.0, -0.8, 0.0, 0.02, 0.58, "snap", "top", erase=False, opacity=0.46, edge=0.52),
    )),
    "routing_spark_core_latches": EffectSpec("achievement_routing_spark.png", (
        m("spark_nodes", 0.0, 0.0, 0.8, 0.12, 0.82, "ratchet", erase=False, opacity=0.42, edge=0.54),
        m("spark_center_star", 0.0, -0.7, 0.0, 0.00, 0.62, "snap", "center", opacity=0.96, edge=0.58),
        m("spark_lower_frame", 0.0, 0.8, 0.0, 0.42, 0.98, "servo", "bottom", opacity=0.94, edge=0.38),
    )),
    "brief_storm_paper_shutters": EffectSpec("achievement_brief_storm.png", (
        m("paper_top", -0.8, -0.8, -0.25, 0.00, 0.50, "hinge", "upper_left", tint=(190, 190, 255), opacity=0.98),
        m("paper_middle", 0.7, 0.0, 0.25, 0.20, 0.72, "ratchet", "center", tint=(178, 226, 255), opacity=0.95),
        m("paper_bottom", -0.4, 0.7, 0.18, 0.48, 1.00, "servo", "lower_right", tint=(160, 130, 255), opacity=0.95),
        m("storm_lower_energy", 0.0, 0.0, 0.0, 0.10, 0.95, "breathe", "center", tint=(178, 108, 255), edge=0.28, shadow=0.12, erase=False, opacity=0.28),
    )),
    "hundred_club_heat_vents": EffectSpec("achievement_hundred_club.png", (
        m("stack_top_plate", 0.0, -0.8, 0.0, 0.00, 0.48, "servo", "top", tint=(255, 215, 124), opacity=0.96),
        m("stack_mid_plate", -0.7, 0.0, 0.0, 0.18, 0.70, "ratchet", "center", tint=(255, 160, 84), opacity=0.94),
        m("stack_bottom_plate", 0.7, 0.5, 0.0, 0.38, 0.92, "ratchet", "bottom", tint=(255, 138, 78), opacity=0.94),
        m("stack_core", 0.0, -0.5, 0.0, 0.10, 0.56, "breathe", "center", tint=(255, 226, 135), erase=False, opacity=0.32, edge=0.48),
    )),
    "thousand_crown_lock": EffectSpec("achievement_thousand_routes.png", (
        m("crown_points", 0.0, -1.0, 0.0, 0.00, 0.56, "snap", "top", tint=(255, 228, 126), opacity=0.98),
        m("crown_left_loop", -0.45, 0.25, -0.25, 0.24, 0.80, "hinge", "left", tint=(255, 210, 110), opacity=0.96),
        m("crown_right_loop", 0.45, 0.25, 0.25, 0.28, 0.84, "hinge", "right", tint=(255, 210, 110), opacity=0.96),
        m("crown_center_gem", 0.0, 0.8, 0.0, 0.54, 1.00, "servo", "bottom", tint=(164, 122, 255), erase=False, opacity=0.38, edge=0.56),
    )),
    "calendar_tick_shutters": EffectSpec("achievement_calendar_crusher.png", (
        m("calendar_spine", 0.0, -0.7, 0.0, 0.02, 0.46, "servo", "top", tint=(176, 220, 255), opacity=0.96),
        m("calendar_page", -0.5, 0.0, -0.18, 0.18, 0.70, "hinge", "upper_left", tint=(198, 232, 255), opacity=0.94),
        m("calendar_check", 0.8, -0.5, 0.16, 0.44, 0.98, "snap", "center", tint=(121, 215, 255), erase=False, opacity=0.45, edge=0.62),
    )),
    "docket_warlord_armor_lock": EffectSpec("achievement_docket_warlord.png", (
        m("warlord_top_spikes", 0.0, -0.9, 0.0, 0.00, 0.46, "snap", "top", tint=(255, 204, 106), opacity=0.96),
        m("warlord_faceplate", 0.0, 0.6, 0.0, 0.22, 0.76, "servo", "center", tint=(255, 178, 96), erase=False, opacity=0.38, edge=0.56),
        m("warlord_side_flags", 0.0, 0.5, 0.0, 0.44, 1.00, "breathe", "bottom", tint=(255, 126, 92), opacity=0.92),
    )),
    "legendary_circuit_calibration": EffectSpec("achievement_legendary_circuit.png", (
        m("circuit_side_nodes", 0.0, 0.0, 0.9, 0.10, 0.78, "ratchet", "center", tint=(111, 246, 255), erase=False, opacity=0.42, edge=0.58),
        m("circuit_crystal", 0.0, -0.5, 0.0, 0.00, 0.62, "snap", "center", tint=(190, 132, 255), erase=False, opacity=0.38, edge=0.62),
        m("circuit_left_rail", -0.7, 0.2, -0.22, 0.36, 0.96, "servo", "left", tint=(120, 180, 255), opacity=0.95),
        m("circuit_right_rail", 0.7, 0.2, 0.22, 0.40, 1.00, "servo", "right", tint=(120, 180, 255), opacity=0.95),
    )),
    "clean_sweep_guardian_clamps": EffectSpec("achievement_clean_sweep.png", (
        m("clean_shield_face", 0.0, -0.5, 0.0, 0.08, 0.66, "snap", "center", tint=(130, 241, 255), opacity=0.94, edge=0.52),
        m("clean_outer_frame", 0.0, 0.0, 0.5, 0.24, 0.88, "ratchet", "center", tint=(140, 255, 195), erase=False, opacity=0.28, edge=0.44),
        m("clean_bottom_gem", 0.0, 0.8, 0.0, 0.54, 1.00, "servo", "bottom", tint=(198, 255, 255), opacity=0.92, edge=0.54),
    )),
    "precision_frost_servo": EffectSpec("achievement_precision_streak.png", (
        m("precision_top_cylinder", 0.0, 0.0, -360.0, 0.00, 1.00, "servo", "precision_top_cap", tint=(192, 248, 255), opacity=0.98, edge=0.64, scale=0.082),
        m("precision_left_cylinder", 0.0, 0.0, -360.0, 0.00, 1.00, "servo", "precision_left_cap", tint=(126, 214, 255), opacity=0.97, edge=0.58, scale=0.076),
        m("precision_right_cylinder", 0.0, 0.0, -360.0, 0.00, 1.00, "servo", "precision_right_cap", tint=(126, 214, 255), opacity=0.97, edge=0.58, scale=0.076),
    )),
    "audit_vault_lock": EffectSpec("achievement_audit_proof.png", (
        m("audit_door", 0.0, -0.35, 0.45, 0.14, 0.72, "ratchet", "center", tint=(174, 226, 255), opacity=0.94, edge=0.50),
        m("audit_seal", 0.0, 0.6, 0.0, 0.42, 0.96, "snap", "center", tint=(255, 220, 152), opacity=0.94, edge=0.58),
        m("audit_edges", 0.0, 0.0, -0.35, 0.00, 0.52, "servo", "center", tint=(150, 210, 255), erase=False, opacity=0.28, edge=0.40),
    )),
    "immaculate_crystal_prongs": EffectSpec("achievement_immaculate.png", (
        m("immaculate_top_crystal", 0.0, -0.8, 0.0, 0.00, 0.52, "snap", "top", tint=(225, 250, 255), opacity=0.94, edge=0.58),
        m("immaculate_scales", 0.0, 0.0, 0.45, 0.24, 0.82, "hinge", "center", tint=(187, 232, 255), erase=False, opacity=0.34, edge=0.42),
        m("immaculate_lower_gem", 0.0, 0.8, 0.0, 0.52, 1.00, "servo", "bottom", tint=(244, 255, 255), opacity=0.94, edge=0.58),
    )),
    "parallel_rail_shift": EffectSpec("achievement_parallel_boss.png", (
        m("parallel_nodes", 0.0, 0.0, 0.65, 0.08, 0.82, "ratchet", "center", tint=(110, 243, 255), erase=False, opacity=0.42, edge=0.58),
        m("parallel_plate", 0.7, 0.0, 0.0, 0.20, 0.70, "servo", "center", tint=(165, 130, 255), opacity=0.92, edge=0.38),
        m("parallel_lower_diamond", 0.0, 0.8, 0.0, 0.54, 1.00, "snap", "bottom", tint=(141, 255, 216), opacity=0.94, edge=0.54),
    )),
    "captain_beacon_panels": EffectSpec("achievement_router_captain.png", (
        m("captain_crown", 0.0, -0.8, 0.0, 0.00, 0.48, "snap", "top", tint=(255, 231, 130), opacity=0.96),
        m("captain_helmet", 0.0, 0.5, 0.0, 0.24, 0.78, "servo", "center", tint=(121, 234, 255), erase=False, opacity=0.36, edge=0.50),
        m("captain_left_wing", -0.7, 0.1, -0.25, 0.40, 0.96, "hinge", "left", tint=(135, 180, 255), opacity=0.94),
        m("captain_right_wing", 0.7, 0.1, 0.25, 0.44, 1.00, "hinge", "right", tint=(135, 180, 255), opacity=0.94),
    )),
    "admiral_command_ring": EffectSpec("achievement_router_admiral.png", (
        m("admiral_spire", 0.0, -0.6, 0.0, 0.00, 0.58, "snap", "top", tint=(114, 246, 255), erase=False, opacity=0.40, edge=0.56),
        m("admiral_nodes", 0.0, 0.0, 0.75, 0.18, 0.84, "ratchet", "center", tint=(255, 220, 128), erase=False, opacity=0.42, edge=0.56),
        m("admiral_left_shell", -0.5, 0.1, -0.22, 0.34, 0.96, "servo", "left", tint=(145, 183, 255), opacity=0.94),
        m("admiral_right_shell", 0.5, 0.1, 0.22, 0.38, 1.00, "servo", "right", tint=(145, 183, 255), opacity=0.94),
    )),
    "full_bench_docking": EffectSpec("achievement_full_bench.png", (
        m("bench_crystals", 0.0, -0.7, 0.0, 0.00, 0.48, "snap", "top", tint=(178, 135, 255), erase=False, opacity=0.42, edge=0.56),
        m("bench_pillars", 0.0, 0.5, 0.0, 0.22, 0.82, "servo", "center", tint=(120, 238, 255), erase=False, opacity=0.34, edge=0.46),
        m("bench_base", 0.0, 0.6, 0.0, 0.48, 1.00, "ratchet", "bottom", tint=(255, 224, 126), opacity=0.92),
    )),
    "no_misses_reticle_lock": EffectSpec("achievement_no_misses.png", (
        m("check_ring", 0.0, 0.0, 0.55, 0.10, 0.78, "ratchet", "center", tint=(164, 238, 255), erase=False, opacity=0.34, edge=0.50),
        m("check_face", 0.0, -0.5, 0.0, 0.26, 0.86, "snap", "center", tint=(255, 231, 130), opacity=0.96, edge=0.62),
        m("check_bottom", 0.0, 0.6, 0.0, 0.54, 1.00, "servo", "bottom", tint=(156, 181, 255), opacity=0.94, edge=0.44),
    )),
    "no_misses_elite_seal": EffectSpec("achievement_no_misses_50.png", (
        m("elite_left_blade", -0.45, 0.25, -0.20, 0.00, 0.58, "servo", "lower_left", tint=(150, 216, 255), opacity=0.94),
        m("elite_right_blade", 0.45, 0.25, 0.20, 0.04, 0.62, "servo", "lower_right", tint=(150, 216, 255), opacity=0.94),
        m("elite_core_check", 0.0, -0.6, 0.0, 0.22, 0.78, "snap", "center", tint=(255, 230, 138), erase=False, opacity=0.42, edge=0.58),
        m("elite_side_crystals", 0.0, 0.0, 0.55, 0.42, 1.00, "ratchet", "center", tint=(180, 132, 255), erase=False, opacity=0.36, edge=0.50),
    )),
    "no_misses_apex_unfold": EffectSpec("achievement_no_misses_100.png", (
        m("apex_left_wing", -0.6, 0.0, -0.24, 0.00, 0.56, "hinge", "left", tint=(255, 224, 122), opacity=0.96),
        m("apex_right_wing", 0.6, 0.0, 0.24, 0.04, 0.60, "hinge", "right", tint=(255, 224, 122), opacity=0.96),
        m("apex_top_prism", 0.0, -0.8, 0.0, 0.18, 0.74, "snap", "top", tint=(255, 242, 170), erase=False, opacity=0.42, edge=0.58),
        m("apex_check", 0.0, -0.5, 0.0, 0.40, 0.98, "servo", "center", tint=(255, 255, 214), erase=False, opacity=0.40, edge=0.56),
    )),
    "court_hopper_portal_gate": EffectSpec("achievement_court_hopper.png", (
        m("court_left_post", -1.0, 0.0, -0.25, 0.00, 0.62, "hinge", "left", tint=(133, 247, 255), opacity=0.96),
        m("court_right_post", 1.0, 0.0, 0.25, 0.08, 0.70, "hinge", "right", tint=(133, 247, 255), opacity=0.96),
        m("court_floor", 0.0, 0.7, 0.0, 0.38, 0.96, "servo", "bottom", tint=(185, 128, 255), erase=False, opacity=0.32, edge=0.44),
        m("portal_top_crystal", 0.0, -0.6, 0.0, 0.18, 0.78, "snap", "top", tint=(255, 211, 124), erase=False, opacity=0.40, edge=0.52),
    )),
    "jurisdiction_swarm_grid": EffectSpec("achievement_jurisdiction_juggler.png", (
        m("jurisdiction_orbit", 0.0, 0.0, 0.55, 0.00, 0.78, "ratchet", "center", tint=(255, 218, 122), erase=False, opacity=0.34, edge=0.48),
        m("jurisdiction_planets", 0.0, 0.0, -0.65, 0.20, 0.88, "servo", "center", tint=(120, 245, 255), erase=False, opacity=0.46, edge=0.58),
        m("jurisdiction_court", 0.0, 0.4, 0.0, 0.46, 1.00, "breathe", "center", tint=(173, 128, 255), opacity=0.92, edge=0.38),
    )),
    "full_spectrum_segment_ring": EffectSpec("achievement_full_spectrum.png", (
        m("spectrum_roof", 0.0, -0.7, 0.0, 0.00, 0.48, "snap", "top", tint=(255, 148, 204), opacity=0.94, edge=0.52),
        m("spectrum_columns", 0.0, 0.5, 0.0, 0.24, 0.84, "servo", "center", tint=(122, 255, 178), opacity=0.92, edge=0.42),
        m("spectrum_diamond", 0.0, 0.7, 0.0, 0.54, 1.00, "ratchet", "bottom", tint=(120, 219, 255), opacity=0.94, edge=0.50),
    )),
    "night_shift_moon_panels": EffectSpec("achievement_night_shift.png", (
        m("night_laptop", 0.0, 0.5, 0.0, 0.20, 0.76, "servo", "center", tint=(118, 215, 255), opacity=0.92, edge=0.46),
        m("night_frame", 0.0, 0.0, -0.32, 0.02, 0.58, "breathe", "center", tint=(174, 200, 255), erase=False, opacity=0.28, edge=0.40),
        m("night_bottom_gem", 0.0, 0.6, 0.0, 0.54, 1.00, "snap", "bottom", tint=(207, 225, 255), opacity=0.94, edge=0.50),
    )),
    "midnight_terminal_locks": EffectSpec("achievement_midnight_operator.png", (
        m("midnight_screen_tiles", 0.0, 0.0, 0.45, 0.12, 0.82, "ratchet", "center", tint=(128, 248, 255), erase=False, opacity=0.40, edge=0.54),
        m("midnight_outer_ring", 0.0, 0.0, -0.35, 0.02, 0.62, "servo", "center", tint=(198, 126, 255), erase=False, opacity=0.28, edge=0.40),
        m("midnight_moon_window", 0.0, -0.4, 0.0, 0.34, 0.94, "breathe", "top", tint=(229, 241, 255), opacity=0.92, edge=0.42),
    )),
    "title_lni_whisperer_parts": EffectSpec("title_lni_whisperer.png", (
        m("lni_document_face", 0.6, 0.0, 0.18, 0.08, 0.76, "servo", "center", tint=(164, 229, 255), opacity=0.94, edge=0.48),
        m("lni_circuit_node", 0.0, 0.0, 0.65, 0.30, 0.96, "ratchet", "center", tint=(180, 136, 255), erase=False, opacity=0.42, edge=0.56),
    )),
    "title_docket_diva_parts": EffectSpec("title_docket_diva.png", (
        m("docket_left_rail", -1.8, 0.2, -0.75, 0.02, 0.68, "hinge", "left", tint=(255, 190, 116), opacity=0.98, edge=0.52),
        m("docket_right_rail", 1.8, 0.2, 0.75, 0.08, 0.74, "hinge", "right", tint=(255, 190, 116), opacity=0.98, edge=0.52),
        m("docket_top_prong", 0.0, -1.6, 0.0, 0.18, 0.78, "snap", "top", tint=(255, 222, 138), opacity=0.98, edge=0.58),
        m("docket_bottom_prong", 0.0, 1.3, 0.0, 0.44, 1.00, "servo", "bottom", tint=(255, 202, 120), opacity=0.96, edge=0.52),
        m("docket_center_gem", 0.0, -0.5, 0.0, 0.30, 0.96, "breathe", "center", tint=(218, 132, 255), erase=False, opacity=0.55, edge=0.78),
    )),
    "title_queue_slayer_parts": EffectSpec("title_queue_slayer.png", (
        m("queue_shutters", 0.75, 0.0, 0.0, 0.00, 0.70, "ratchet", "center", tint=(255, 126, 206), opacity=0.94),
        m("clean_bottom_gem", 0.0, 0.6, 0.0, 0.54, 1.00, "snap", "bottom", tint=(119, 246, 255), erase=False, opacity=0.36, edge=0.48),
    )),
    "title_archive_authority_parts": EffectSpec("title_archive_authority.png", (
        m("archive_vault_dial", 0.0, 0.0, 0.9, 0.10, 0.82, "ratchet", "center", tint=(255, 224, 128), erase=False, opacity=0.48, edge=0.60),
        m("archive_left_lock", -0.65, 0.0, -0.16, 0.34, 0.96, "servo", "left", tint=(118, 232, 255), opacity=0.94),
        m("archive_right_lock", 0.65, 0.0, 0.16, 0.38, 1.00, "servo", "right", tint=(118, 232, 255), opacity=0.94),
    )),
    "title_final_reviewer_parts": EffectSpec("title_final_reviewer.png", (
        m("final_crystal", 0.0, -0.5, 0.0, 0.00, 0.64, "snap", "center", tint=(198, 130, 255), erase=False, opacity=0.42, edge=0.58),
        m("final_left_armor", -0.65, 0.15, -0.20, 0.32, 0.94, "hinge", "left", tint=(132, 232, 255), opacity=0.94),
        m("final_right_armor", 0.65, 0.15, 0.20, 0.36, 0.98, "hinge", "right", tint=(132, 232, 255), opacity=0.94),
        m("clean_bottom_gem", 0.0, 0.6, 0.0, 0.54, 1.00, "servo", "bottom", tint=(255, 222, 134), erase=False, opacity=0.36, edge=0.48),
    )),
    "title_six_router_menace_parts": EffectSpec("title_six_router_menace.png", (
        m("six_router_nodes", 0.0, 0.0, 0.55, 0.02, 0.82, "ratchet", "center", tint=(118, 237, 255), erase=False, opacity=0.42, edge=0.56),
        m("six_router_core", 0.0, -0.4, 0.0, 0.34, 0.94, "snap", "center", tint=(190, 122, 255), opacity=0.94, edge=0.56),
    )),
}


def render_effect(effect_key: str, spec: EffectSpec) -> None:
    source = _fit_badge(SHOP_ICON_DIR / spec.image_name)
    bounds = _badge_bounds(source)
    layers = []

    for motion in spec.motions:
        piece = _component(source, motion.shape, effect_key, motion.erase)
        if not piece.getchannel("A").getbbox():
            continue
        layers.append((
            motion,
            piece,
            _shadow_base(piece),
            _edge_light_base(piece, motion.tint),
            _pivot_point(bounds, motion.pivot),
        ))

    effect_dir = OUT_DIR / effect_key
    effect_dir.mkdir(parents=True, exist_ok=True)

    for frame in range(FRAMES):
        position = frame / max(1, FRAMES - 1)
        canvas = source.copy()
        active_layers = []

        for index, (motion, piece, shadow_base, edge_base, pivot) in enumerate(layers):
            amount = _curve_amount(position, motion)
            if amount <= 0.01:
                continue
            dx, dy, angle, scale = _motion_frame_values(effect_key, motion, amount, frame, index)
            if motion.erase:
                erase_amount = 1.0 if effect_key in FULL_ERASE_EFFECTS else min(0.99, 0.88 + amount * 0.11)
                _erase_piece(canvas, piece, erase_amount)
            active_layers.append((motion, piece, shadow_base, edge_base, pivot, amount, dx, dy, angle, scale))

        canvas.alpha_composite(_inner_cavity_layer(effect_key, active_layers))
        canvas.alpha_composite(_crack_vent_layer(effect_key, layers, frame))

        for motion, piece, shadow_base, edge_base, pivot, amount, dx, dy, angle, scale in active_layers:
            shadow_layer = _transform_layer(shadow_base, dx + 0.7 * amount, dy + 1.0 * amount, angle, pivot, scale)
            piece_layer = _transform_layer(piece, dx, dy, angle, pivot, scale)
            edge_layer = _transform_layer(edge_base, dx, dy, angle, pivot, scale)
            if effect_key == "precision_frost_servo" and motion.shape in PRECISION_CAP_SHAPES:
                cap_clip = piece.getchannel("A")
                shadow_layer = _clip_layer_alpha(shadow_layer, cap_clip)
                piece_layer = _clip_layer_alpha(piece_layer, cap_clip)
                edge_layer = _clip_layer_alpha(edge_layer, cap_clip)

            canvas.alpha_composite(_opacity(shadow_layer, amount * motion.shadow))
            canvas.alpha_composite(_opacity(piece_layer, motion.opacity))
            canvas.alpha_composite(_opacity(edge_layer, amount * motion.edge))

        canvas.save(effect_dir / f"{frame:02d}.png")


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for effect_key, spec in EFFECT_SPECS.items():
        render_effect(effect_key, spec)
    print(f"Generated {len(EFFECT_SPECS)} semantic badge mechanical effect(s) in {OUT_DIR}")


if __name__ == "__main__":
    main()
