"""Texture-sprite based badge VFX assets.

The first badge animation pass used direct drawing primitives. That is reliable,
but it makes every element look like vector art. This module builds reusable
transparent material sprites first, then composes those sprites into badge frame
sequences. The runtime still only plays PNG frames; the heavier asset work stays
inside this offline generator.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MATERIAL_DIR = ROOT / "assets" / "images" / "vfx_materials"
SOURCE_SHEET_DIR = ROOT / "tools" / "vfx_source_sheets"
SPRITE_SIZE = 192
SPRITES_PER_FAMILY = 16


FAMILIES = (
    "air",
    "smoke",
    "fire",
    "water",
    "earth",
    "magma",
    "plasma",
    "void",
    "ice",
    "growth",
    "gold",
    "portal",
)


EFFECT_RECIPES = {
    "first_route_air": {"primary": "air", "secondary": "portal", "seed": 101, "glow": "#7EF1FF"},
    "routing_spark_lightning": {"primary": "plasma", "secondary": "gold", "seed": 111, "glow": "#FFD96A"},
    "lni_whisperer_mist": {"primary": "smoke", "secondary": "air", "seed": 121, "glow": "#B6FBFF"},
    "brief_storm_lightning": {"primary": "plasma", "secondary": "smoke", "seed": 131, "glow": "#B56CFF"},
    "hundred_club_fire": {"primary": "fire", "secondary": "magma", "seed": 141, "glow": "#FF7A2A"},
    "queue_slayer_earth": {"primary": "earth", "secondary": "magma", "seed": 151, "glow": "#8A6B45"},
    "final_reviewer_solar": {"primary": "gold", "secondary": "fire", "seed": 161, "glow": "#FFE58A"},
    "calendar_crusher_water": {"primary": "water", "secondary": "ice", "seed": 171, "glow": "#64E9FF"},
    "thousand_crown_meteor": {"primary": "fire", "secondary": "earth", "seed": 181, "glow": "#FFB23B"},
    "docket_warlord_magma": {"primary": "magma", "secondary": "earth", "seed": 191, "glow": "#FF553D"},
    "legendary_circuit_electric": {"primary": "plasma", "secondary": "portal", "seed": 201, "glow": "#54F5FF"},
    "clean_sweep_growth": {"primary": "growth", "secondary": "air", "seed": 211, "glow": "#64FFD0"},
    "precision_streak_frost": {"primary": "ice", "secondary": "air", "seed": 221, "glow": "#D8FDFF"},
    "archive_authority_stone": {"primary": "earth", "secondary": "smoke", "seed": 231, "glow": "#88FFE2"},
    "audit_proof_steel": {"primary": "ice", "secondary": "gold", "seed": 241, "glow": "#D8FDFF"},
    "immaculate_crystal": {"primary": "ice", "secondary": "portal", "seed": 251, "glow": "#BDEFFF"},
    "parallel_boss_air": {"primary": "air", "secondary": "plasma", "seed": 261, "glow": "#93F4FF"},
    "router_captain_beacon": {"primary": "gold", "secondary": "portal", "seed": 271, "glow": "#FFD96A"},
    "router_admiral_network": {"primary": "water", "secondary": "plasma", "seed": 281, "glow": "#43EAFF"},
    "full_bench_six_orbit": {"primary": "portal", "secondary": "gold", "seed": 291, "glow": "#7EF1FF"},
    "six_router_void": {"primary": "void", "secondary": "plasma", "seed": 301, "glow": "#8C4DFF"},
    "no_misses_impact": {"primary": "earth", "secondary": "gold", "seed": 311, "glow": "#FFD96A"},
    "no_misses_elite_cracks": {"primary": "void", "secondary": "earth", "seed": 321, "glow": "#B56CFF"},
    "no_misses_apex_explosion": {"primary": "gold", "secondary": "fire", "seed": 331, "glow": "#FFE58A"},
    "docket_diva_prism_water": {"primary": "water", "secondary": "portal", "seed": 341, "glow": "#FF67B5"},
    "court_hopper_portal": {"primary": "portal", "secondary": "air", "seed": 351, "glow": "#7EF1FF"},
    "jurisdiction_juggler_swarm": {"primary": "portal", "secondary": "void", "seed": 361, "glow": "#B56CFF"},
    "full_spectrum_elements": {"primary": "portal", "secondary": "fire", "tertiary": "water", "seed": 371, "glow": "#64FFD0"},
    "night_shift_moon_vapor": {"primary": "smoke", "secondary": "void", "seed": 381, "glow": "#B56CFF"},
    "midnight_operator_neon_fumes": {"primary": "smoke", "secondary": "plasma", "seed": 391, "glow": "#64FFD0"},
}


_SPRITE_CACHE: dict[str, list[Image.Image]] = {}


# External sheets are CC0 source material downloaded from OpenGameArt listings.
# Keep these recipes compact: this generator normalizes them into a small local
# material atlas, while the runtime only plays the finished badge_vfx frames.
SOURCE_SPECS = {
    "air_bubbles_01.png": (8, 8),
    "air_bubbles_02.png": (8, 8),
    "fire_01.png": (8, 8),
    "fire_01b.png": (8, 8),
    "fire_01c.png": (8, 8),
    "fire_02.png": (8, 8),
    "lighter_flame_01.png": (8, 8),
    "teleporter_01.png": (8, 8),
    "teleporter_hit.png": (8, 8),
    "Fire01.png": (8, 4),
    "Explosion25.png": (4, 4),
    "Effect36.png": (4, 4),
    "Effect51.png": (4, 4),
    "ToonExplosion31.png": (4, 4),
    "energy1_0.png": (8, 8),
    "energy2.png": (8, 8),
    "energy3.png": (8, 8),
    "energy4.png": (8, 8),
    "fire1_64.png": (10, 6),
    "fire2_64_0.png": (10, 6),
    "fire3_64.png": (10, 6),
    "fire4_64.png": (10, 6),
    "fire5_64.png": (10, 6),
    "fire6_64.png": (10, 6),
    "fire7_64.png": (10, 6),
    "fire8_64.png": (10, 6),
    "Poof.png": (6, 5),
    "MagicMirror.png": (4, 4),
}


FAMILY_SOURCE_RECIPES = {
    "air": [
        ("air_bubbles_01.png", 0.62, "#9EF8FF", 0.18),
        ("air_bubbles_02.png", 0.54, "#E9FFFF", 0.24),
        ("smoke1.png", 0.30, "#A6F7FF", 0.40),
    ],
    "smoke": [
        ("smoke1.png", 0.62, "#C9D6FF", 0.18),
        ("smoke2.png", 0.58, "#B8C7E8", 0.22),
        ("smoke3.png", 0.52, "#D7DBEA", 0.16),
        ("Poof.png", 0.46, "#CCD6EA", 0.32),
    ],
    "fire": [
        ("Fire01.png", 0.82, "#FF6A23", 0.04),
        ("fire_02.png", 0.74, "#FF8A25", 0.05),
        ("fire_01.png", 0.68, "#FF4D2B", 0.02),
        ("fire1_64.png", 0.72, "#FFB23B", 0.03),
    ],
    "water": [
        ("air_bubbles_02.png", 0.66, "#46DFFF", 0.46),
        ("air_bubbles_01.png", 0.58, "#8EF5FF", 0.38),
        ("Effect51.png", 0.44, "#4BE9FF", 0.55),
        ("fire2_64_0.png", 0.34, "#73EDFF", 0.58),
    ],
    "earth": [
        ("smoke4.png", 0.58, "#806A51", 0.62),
        ("smoke1.png", 0.44, "#A98450", 0.56),
        ("Explosion25.png", 0.34, "#A98450", 0.54),
    ],
    "magma": [
        ("Fire01.png", 0.64, "#FF553D", 0.12),
        ("Explosion25.png", 0.54, "#FF7A2A", 0.18),
        ("smoke4.png", 0.38, "#7A3324", 0.50),
    ],
    "plasma": [
        ("energy2.png", 0.70, "#70F6FF", 0.38),
        ("energy3.png", 0.66, "#AE7CFF", 0.42),
        ("Effect36.png", 0.52, "#7EF1FF", 0.28),
        ("teleporter_hit.png", 0.46, "#B56CFF", 0.30),
    ],
    "void": [
        ("energy3.png", 0.64, "#9B58FF", 0.58),
        ("energy4.png", 0.58, "#4B3DFF", 0.62),
        ("teleporter_01.png", 0.50, "#6E3EFF", 0.44),
    ],
    "ice": [
        ("fire2_64_0.png", 0.62, "#C8FBFF", 0.42),
        ("energy4.png", 0.56, "#BDEFFF", 0.36),
        ("Effect51.png", 0.44, "#E2FFFF", 0.44),
    ],
    "growth": [
        ("smoke2.png", 0.44, "#6BE675", 0.66),
        ("air_bubbles_01.png", 0.36, "#92FFB7", 0.54),
        ("smoke3.png", 0.34, "#69FFB0", 0.64),
    ],
    "gold": [
        ("energy1_0.png", 0.72, "#FFD96A", 0.16),
        ("ToonExplosion31.png", 0.54, "#FFC457", 0.18),
        ("Explosion25.png", 0.42, "#FFE58A", 0.22),
    ],
    "portal": [
        ("teleporter_01.png", 0.70, "#7EF1FF", 0.18),
        ("teleporter_hit.png", 0.60, "#B56CFF", 0.20),
        ("MagicMirror.png", 0.42, "#A9F7FF", 0.24),
    ],
}


def _rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = hex_color.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        max(0, min(255, int(alpha))),
    )


def _blank(size: int = SPRITE_SIZE) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def _mask(size: int = SPRITE_SIZE) -> Image.Image:
    return Image.new("L", (size, size), 0)


def _noise(size: int, strength: float, blur: float = 0.0, seed: int = 0) -> Image.Image:
    # effect_noise has no seed, so phase it with a deterministic tiled offset.
    random.seed(seed)
    n = Image.effect_noise((size + 32, size + 32), strength).convert("L")
    left = random.randint(0, 32)
    top = random.randint(0, 32)
    n = n.crop((left, top, left + size, top + size))
    if blur:
        n = n.filter(ImageFilter.GaussianBlur(blur))
    return n


def _combine_mask(shape: Image.Image, noise: Image.Image, boost: float = 1.0) -> Image.Image:
    mixed = ImageChops.multiply(shape, noise)
    mixed = ImageEnhance.Contrast(mixed).enhance(1.35)
    if boost != 1.0:
        mixed = mixed.point(lambda p: max(0, min(255, int(p * boost))))
    return mixed


def _colorized(mask: Image.Image, low: str, high: str, alpha_boost: float = 1.0) -> Image.Image:
    color = ImageOps.colorize(mask, low, high).convert("RGBA")
    alpha = mask.point(lambda p: max(0, min(255, int(p * alpha_boost))))
    color.putalpha(alpha)
    return color


def _soft_glow(mask: Image.Image, color: str, radius: float, alpha: float = 0.46) -> Image.Image:
    glow_mask = mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda p: max(0, min(255, int(p * alpha))))
    glow = Image.new("RGBA", mask.size, _rgba(color, 255))
    glow.putalpha(glow_mask)
    return glow


def _alpha_composite_layers(*layers: Image.Image) -> Image.Image:
    base = _blank(layers[0].size[0] if layers else SPRITE_SIZE)
    for layer in layers:
        base.alpha_composite(layer)
    return base


def _alpha_bbox(image: Image.Image, threshold: int = 8) -> tuple[int, int, int, int] | None:
    alpha = image.convert("RGBA").getchannel("A")
    solid = alpha.point(lambda p: 255 if p > threshold else 0)
    return solid.getbbox()


def _external_source_exists() -> bool:
    if not SOURCE_SHEET_DIR.exists():
        return False
    return any((SOURCE_SHEET_DIR / name).exists() for name in SOURCE_SPECS) or any(SOURCE_SHEET_DIR.glob("smoke*.png"))


def _extract_external_frames(filename: str) -> list[Image.Image]:
    path = SOURCE_SHEET_DIR / filename
    if not path.exists():
        return []

    image = Image.open(path).convert("RGBA")
    spec = SOURCE_SPECS.get(filename)
    if not spec:
        return [image] if _alpha_bbox(image) else []

    columns, rows = spec
    cell_w = image.width // columns
    cell_h = image.height // rows
    frames: list[Image.Image] = []
    for row in range(rows):
        for column in range(columns):
            frame = image.crop((column * cell_w, row * cell_h, (column + 1) * cell_w, (row + 1) * cell_h))
            if _alpha_bbox(frame):
                frames.append(frame)
    return frames


def _normalize_external_sprite(
    frame: Image.Image,
    family: str,
    index: int,
    opacity: float = 1.0,
    tint: str | None = None,
    tint_amount: float = 0.0,
) -> Image.Image:
    frame = frame.convert("RGBA")
    bbox = _alpha_bbox(frame)
    if not bbox:
        return _blank()

    cropped = frame.crop(bbox)
    max_side = SPRITE_SIZE * (0.82 if family in {"smoke", "earth", "air"} else 0.88)
    if family in {"plasma", "gold", "portal", "void"}:
        max_side = SPRITE_SIZE * 0.74
    if family in {"fire", "magma", "ice"}:
        max_side = SPRITE_SIZE * 0.90

    scale = min(max_side / max(1, cropped.width), max_side / max(1, cropped.height))
    new_size = (max(2, int(cropped.width * scale)), max(2, int(cropped.height * scale)))
    sprite = cropped.resize(new_size, Image.Resampling.LANCZOS)

    if tint:
        sprite = _tint(sprite, tint, tint_amount)

    if family in {"earth", "smoke", "air", "growth"}:
        sprite = sprite.filter(ImageFilter.GaussianBlur(0.35))
    elif family in {"plasma", "gold", "portal", "void"}:
        sprite = ImageEnhance.Contrast(sprite).enhance(1.16)
        sprite = ImageEnhance.Brightness(sprite).enhance(1.08)

    alpha = sprite.getchannel("A").point(lambda p: max(0, min(255, int(p * opacity))))
    sprite.putalpha(alpha)

    canvas = _blank()
    rng = random.Random(abs(hash((family, index, "external-vfx"))) & 0xFFFF)
    x = (SPRITE_SIZE - sprite.width) // 2 + int(rng.uniform(-5, 5))
    y = (SPRITE_SIZE - sprite.height) // 2 + int(rng.uniform(-5, 5))
    canvas.alpha_composite(sprite, (x, y))
    return canvas


def _external_family_sprites(family: str) -> list[Image.Image]:
    if not _external_source_exists():
        return []

    recipe = FAMILY_SOURCE_RECIPES.get(family, [])
    prepared_sources: list[tuple[list[Image.Image], float, str, float]] = []
    for filename, opacity, tint, tint_amount in recipe:
        frames = _extract_external_frames(filename)
        if frames:
            prepared_sources.append((frames, opacity, tint, tint_amount))

    if not prepared_sources:
        return []

    sprites: list[Image.Image] = []
    for index in range(SPRITES_PER_FAMILY):
        frames, opacity, tint, tint_amount = prepared_sources[index % len(prepared_sources)]
        frame_index = (index * 5 + len(family) * 3) % len(frames)
        sprites.append(_normalize_external_sprite(frames[frame_index], family, index, opacity, tint, tint_amount))
    return sprites


def _draw_flame_mask(index: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    mask = _mask()
    draw = ImageDraw.Draw(mask, "L")
    for tongue in range(9):
        cx = 96 + (tongue - 4) * rng.uniform(9, 15) + math.sin(index + tongue) * 5
        base_y = 176 + rng.uniform(-8, 8)
        height = rng.uniform(72, 130)
        width = rng.uniform(16, 34)
        lean = rng.uniform(-22, 22)
        left = []
        right = []
        steps = 9
        for step in range(steps):
            p = step / (steps - 1)
            taper = (1 - p) ** 0.72
            x = cx + lean * p + math.sin(p * math.tau * 1.5 + index * 0.8 + tongue) * 9
            y = base_y - height * p
            local_w = width * taper * (0.72 + 0.22 * math.sin(p * 9 + tongue))
            left.append((x - local_w, y))
            right.append((x + local_w * rng.uniform(0.7, 1.1), y))
        draw.polygon(left + right[::-1], fill=rng.randint(150, 245))
    return mask.filter(ImageFilter.GaussianBlur(1.2))


def _draw_wave_mask(index: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    mask = _mask()
    draw = ImageDraw.Draw(mask, "L")
    for band in range(5):
        y = 62 + band * 24 + rng.uniform(-5, 5)
        amp = rng.uniform(9, 17)
        thick = rng.uniform(17, 27)
        phase = index * 0.37 + band * 0.7 + rng.random() * math.tau
        upper = []
        lower = []
        for step in range(18):
            p = step / 17
            x = 8 + p * 176
            wave = math.sin(p * math.tau * 1.2 + phase) * amp
            chop = math.sin(p * math.tau * 4.3 - phase) * amp * 0.24
            yy = y + wave + chop
            upper.append((x, yy))
            lower.append((x, yy + thick + math.cos(p * math.tau * 1.8 + phase) * 5))
        draw.polygon(upper + lower[::-1], fill=135 + band * 20)
    for _ in range(18):
        x = rng.uniform(30, 164)
        y = rng.uniform(38, 170)
        r = rng.uniform(1.5, 4.0)
        draw.ellipse((x - r, y - r * 1.5, x + r, y + r * 1.5), fill=rng.randint(120, 220))
    return mask.filter(ImageFilter.GaussianBlur(1.1))


def _draw_cloud_mask(index: int, seed: int, dense: bool = False) -> Image.Image:
    rng = random.Random(seed)
    mask = _mask()
    draw = ImageDraw.Draw(mask, "L")
    count = 36 if dense else 24
    for puff in range(count):
        phase = puff / count
        x = 96 + math.sin(index * 0.45 + puff) * rng.uniform(16, 58) + rng.uniform(-42, 42)
        y = 132 - phase * rng.uniform(50, 115) + rng.uniform(-16, 20)
        rx = rng.uniform(12, 34) * (1.05 if dense else 0.92)
        ry = rng.uniform(8, 24) * (1.10 if dense else 0.95)
        draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=rng.randint(80, 175))
    return mask.filter(ImageFilter.GaussianBlur(5.0 if dense else 6.5))


def _draw_earth_mask(index: int, seed: int) -> tuple[Image.Image, Image.Image]:
    rng = random.Random(seed)
    dust = _mask()
    rocks = _mask()
    dust_draw = ImageDraw.Draw(dust, "L")
    rock_draw = ImageDraw.Draw(rocks, "L")
    for puff in range(28):
        x = 96 + rng.uniform(-78, 78)
        y = 138 + rng.uniform(-18, 40) - math.sin(index * 0.3 + puff) * 5
        rx = rng.uniform(8, 26)
        ry = rng.uniform(4, 14)
        dust_draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=rng.randint(45, 130))
    for chunk in range(12):
        x = 96 + (chunk - 5.5) * rng.uniform(9, 15) + rng.uniform(-10, 10)
        y = 118 + rng.uniform(-18, 34)
        rx = rng.uniform(6, 14)
        ry = rng.uniform(7, 18)
        points = []
        sides = rng.randint(5, 7)
        for side in range(sides):
            a = side / sides * math.tau + rng.uniform(-0.25, 0.25)
            points.append((x + math.cos(a) * rx * rng.uniform(0.75, 1.18), y + math.sin(a) * ry * rng.uniform(0.72, 1.14)))
        rock_draw.polygon(points, fill=rng.randint(125, 230))
    return dust.filter(ImageFilter.GaussianBlur(4.2)), rocks.filter(ImageFilter.GaussianBlur(0.9))


def _draw_plasma_mask(index: int, seed: int, void: bool = False) -> Image.Image:
    rng = random.Random(seed)
    mask = _mask()
    draw = ImageDraw.Draw(mask, "L")
    for lobe in range(14):
        angle = lobe / 14 * math.tau + index * 0.17
        radius = rng.uniform(9, 38)
        x = 96 + math.cos(angle) * rng.uniform(12, 50)
        y = 96 + math.sin(angle) * rng.uniform(10, 38)
        rx = radius * rng.uniform(0.7, 1.4)
        ry = radius * rng.uniform(0.45, 1.05)
        draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=rng.randint(100, 220))
    for tendril in range(7):
        angle = tendril / 7 * math.tau + index * 0.32
        points = [(96, 96)]
        for step in range(1, 5):
            distance = step * rng.uniform(13, 22)
            points.append(
                (
                    96 + math.cos(angle + math.sin(step + index) * 0.28) * distance,
                    96 + math.sin(angle + math.cos(step + index) * 0.28) * distance * 0.72,
                )
            )
        draw.line(points, fill=rng.randint(105, 205), width=rng.randint(4, 8), joint="curve")
    blur = 2.8 if void else 2.2
    return mask.filter(ImageFilter.GaussianBlur(blur))


def _draw_ice_mask(index: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    mask = _mask()
    draw = ImageDraw.Draw(mask, "L")
    for shard in range(11):
        angle = -math.pi / 2 + (shard - 5) * 0.18 + rng.uniform(-0.12, 0.12)
        base_x = 96 + math.cos(angle) * rng.uniform(10, 34)
        base_y = 130 + math.sin(angle) * rng.uniform(4, 18)
        length = rng.uniform(40, 88)
        width = rng.uniform(7, 17)
        tip = (base_x + math.cos(angle) * length, base_y + math.sin(angle) * length)
        side = angle + math.pi / 2
        points = [
            (base_x - math.cos(side) * width, base_y - math.sin(side) * width),
            tip,
            (base_x + math.cos(side) * width, base_y + math.sin(side) * width),
            (base_x + math.cos(angle) * 12, base_y + math.sin(angle) * 12),
        ]
        draw.polygon(points, fill=rng.randint(120, 238))
    return mask.filter(ImageFilter.GaussianBlur(0.7))


def _draw_growth_mask(index: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    mask = _mask()
    draw = ImageDraw.Draw(mask, "L")
    for vine in range(10):
        phase = vine / 10
        angle = -math.pi / 2 + (vine - 4.5) * 0.16 + math.sin(index + vine) * 0.07
        points = [(96 + rng.uniform(-8, 8), 174)]
        length = rng.uniform(55, 112)
        for step in range(1, 6):
            p = step / 5
            points.append(
                (
                    96 + math.cos(angle) * length * p + math.sin(p * math.tau + vine) * 10,
                    174 + math.sin(angle) * length * p,
                )
            )
        draw.line(points, fill=rng.randint(105, 210), width=rng.randint(4, 8), joint="curve")
        tip = points[-1]
        for side in (-1, 1):
            leaf_angle = angle + side * rng.uniform(0.75, 1.15)
            w = rng.uniform(6, 12)
            h = rng.uniform(15, 28)
            leaf = [
                tip,
                (tip[0] + math.cos(leaf_angle + 0.8) * w, tip[1] + math.sin(leaf_angle + 0.8) * w),
                (tip[0] + math.cos(leaf_angle) * h, tip[1] + math.sin(leaf_angle) * h),
                (tip[0] + math.cos(leaf_angle - 0.8) * w, tip[1] + math.sin(leaf_angle - 0.8) * w),
            ]
            draw.polygon(leaf, fill=rng.randint(120, 230))
    return mask.filter(ImageFilter.GaussianBlur(1.0))


def _make_family_sprite(family: str, index: int) -> Image.Image:
    seed = abs(hash((family, index, "smd-vfx"))) & 0xFFFF
    noise = _noise(SPRITE_SIZE, 70, blur=1.2, seed=seed)

    if family == "fire":
        mask = _combine_mask(_draw_flame_mask(index, seed), noise, 1.35)
        return _alpha_composite_layers(
            _soft_glow(mask, "#FF553D", 7.0, 0.55),
            _colorized(mask, "#8B161E", "#FFF0B8", 1.15),
        )
    if family == "water":
        mask = _combine_mask(_draw_wave_mask(index, seed), noise, 1.18)
        foam = mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(0.7)).point(lambda p: min(255, int(p * 1.8)))
        return _alpha_composite_layers(
            _soft_glow(mask, "#54DFFF", 7.5, 0.42),
            _colorized(mask, "#1A4FC3", "#DDFDFF", 0.92),
            _colorized(foam, "#B6FBFF", "#FFFFFF", 0.78),
        )
    if family == "air":
        mask = _combine_mask(_draw_cloud_mask(index, seed, dense=False), noise, 1.0)
        return _alpha_composite_layers(
            _soft_glow(mask, "#8CEFFF", 8.0, 0.26),
            _colorized(mask, "#7EDFFF", "#FFFFFF", 0.58),
        )
    if family == "smoke":
        mask = _combine_mask(_draw_cloud_mask(index, seed, dense=True), noise, 0.9)
        return _alpha_composite_layers(
            _soft_glow(mask, "#B56CFF", 9.0, 0.24),
            _colorized(mask, "#182034", "#D4E8FF", 0.54),
        )
    if family in {"earth", "magma"}:
        dust, rocks = _draw_earth_mask(index, seed)
        dust_noise = _combine_mask(dust, noise, 0.96)
        rock_noise = _combine_mask(rocks, noise, 1.18)
        if family == "magma":
            return _alpha_composite_layers(
                _soft_glow(dust_noise, "#FF553D", 8.0, 0.48),
                _colorized(dust_noise, "#2B1720", "#873124", 0.72),
                _colorized(rock_noise, "#351F22", "#FF9A35", 1.05),
            )
        return _alpha_composite_layers(
            _soft_glow(dust_noise, "#8A6B45", 8.0, 0.25),
            _colorized(dust_noise, "#2E2B28", "#9A7B57", 0.66),
            _colorized(rock_noise, "#343538", "#D0B782", 0.94),
        )
    if family in {"plasma", "void", "gold", "portal"}:
        mask = _combine_mask(_draw_plasma_mask(index, seed, void=(family == "void")), noise, 1.18)
        edge = mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(0.8)).point(lambda p: min(255, int(p * 1.75)))
        if family == "gold":
            low, high, glow = "#8A4B14", "#FFF1A8", "#FFD96A"
        elif family == "void":
            low, high, glow = "#171034", "#BC74FF", "#8C4DFF"
        elif family == "portal":
            low, high, glow = "#1B52B8", "#F1E9FF", "#7EF1FF"
        else:
            low, high, glow = "#2435B8", "#E8FFFF", "#7EF1FF"
        return _alpha_composite_layers(
            _soft_glow(mask, glow, 8.5, 0.54),
            _colorized(mask, low, high, 0.90),
            _colorized(edge, glow, "#FFFFFF", 0.76),
        )
    if family == "ice":
        mask = _combine_mask(_draw_ice_mask(index, seed), noise, 1.18)
        facets = mask.filter(ImageFilter.FIND_EDGES).point(lambda p: min(255, int(p * 2.1)))
        return _alpha_composite_layers(
            _soft_glow(mask, "#9DEEFF", 7.0, 0.44),
            _colorized(mask, "#5272FF", "#F3FFFF", 0.94),
            _colorized(facets, "#B6FBFF", "#FFFFFF", 0.80),
        )
    if family == "growth":
        mask = _combine_mask(_draw_growth_mask(index, seed), noise, 1.2)
        return _alpha_composite_layers(
            _soft_glow(mask, "#64FFD0", 7.0, 0.35),
            _colorized(mask, "#166A35", "#D8FFD0", 0.96),
        )

    return _blank()


def ensure_material_sprites(force: bool = False) -> None:
    if force:
        _SPRITE_CACHE.clear()

    MATERIAL_DIR.mkdir(parents=True, exist_ok=True)
    for family in FAMILIES:
        family_dir = MATERIAL_DIR / family
        family_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(family_dir.glob("*.png"))
        if not force and len(existing) == SPRITES_PER_FAMILY:
            continue
        for old in existing:
            old.unlink()

        sprites = _external_family_sprites(family)
        if len(sprites) != SPRITES_PER_FAMILY:
            sprites = [_make_family_sprite(family, index) for index in range(SPRITES_PER_FAMILY)]

        for index, sprite in enumerate(sprites):
            sprite.save(family_dir / f"{index:02d}.png", compress_level=4)


def _family_sprites(family: str) -> list[Image.Image]:
    if family not in _SPRITE_CACHE:
        ensure_material_sprites()
        sprites = []
        for path in sorted((MATERIAL_DIR / family).glob("*.png")):
            sprites.append(Image.open(path).convert("RGBA"))
        _SPRITE_CACHE[family] = sprites
    return _SPRITE_CACHE[family]


def _sprite(family: str, frame: int, offset: int = 0) -> Image.Image:
    sprites = _family_sprites(family)
    return sprites[(frame + offset) % len(sprites)]


def _adjust_alpha(image: Image.Image, opacity: float) -> Image.Image:
    out = image.copy()
    alpha = out.getchannel("A").point(lambda p: max(0, min(255, int(p * opacity))))
    out.putalpha(alpha)
    return out


def _trim_alpha(image: Image.Image, threshold: int = 7) -> Image.Image:
    out = image.copy()
    alpha = out.getchannel("A").point(lambda p: 0 if p < threshold else p)
    out.putalpha(alpha)
    return out


def _tint(image: Image.Image, color: str, amount: float) -> Image.Image:
    if amount <= 0:
        return image
    tint = Image.new("RGBA", image.size, _rgba(color, 255))
    rgb = Image.blend(image.convert("RGBA"), tint, amount)
    rgb.putalpha(image.getchannel("A"))
    return rgb


def _place(base: Image.Image, sprite: Image.Image, center: tuple[float, float], scale: float, angle: float, opacity: float, tint: str | None = None, tint_amount: float = 0.0) -> None:
    w = max(4, int(sprite.width * scale))
    h = max(4, int(sprite.height * scale))
    out = sprite.resize((w, h), Image.Resampling.LANCZOS)
    if tint:
        out = _tint(out, tint, tint_amount)
    out = out.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    out = _adjust_alpha(out, opacity)
    x = int(center[0] - out.width / 2)
    y = int(center[1] - out.height / 2)
    base.alpha_composite(out, (x, y))


def _glow(base: Image.Image, center: tuple[float, float], color: str, radius: float, opacity: float) -> None:
    size = base.size[0]
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask, "L")
    x, y = center
    draw.ellipse((x - radius, y - radius * 0.72, x + radius, y + radius * 0.72), fill=int(255 * opacity))
    layer = Image.new("RGBA", (size, size), _rgba(color, 255))
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * 0.42)))
    base.alpha_composite(layer)


def _event_pulse(t: float, center: float, width: float) -> float:
    distance = abs((t - center + 0.5) % 1.0 - 0.5)
    if distance >= width:
        return 0.0
    x = 1.0 - distance / width
    return x * x * (3.0 - 2.0 * x)


def _event_progress(t: float, center: float, width: float) -> float:
    start = (center - width) % 1.0
    duration = width * 2.0
    elapsed = (t - start) % 1.0
    if elapsed > duration:
        return 0.0
    return max(0.0, min(1.0, elapsed / duration))


def _perimeter_anchor(rng: random.Random, family: str, side: str | None = None) -> tuple[float, float]:
    side = side or rng.choice(("left", "right", "top", "bottom"))

    if side == "left":
        return (rng.uniform(30, 62), rng.uniform(78, 184))
    if side == "right":
        return (rng.uniform(194, 226), rng.uniform(78, 184))
    if side == "top":
        return (rng.uniform(76, 180), rng.uniform(28, 66))
    if side == "bottom":
        if family in {"fire", "magma", "gold", "earth", "growth"}:
            return (rng.uniform(86, 170), rng.uniform(198, 226))
        return (rng.uniform(76, 180), rng.uniform(184, 218))

    return (rng.uniform(82, 174), rng.uniform(82, 174))


def _draw_soft_dot(base: Image.Image, x: float, y: float, radius: float, color: str, opacity: float, blur: float = 1.1) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=_rgba(color, 255 * opacity))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _draw_micro_arc(base: Image.Image, rng: random.Random, anchor: tuple[float, float], color: str, strength: float) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    branch_count = 1 + (1 if rng.random() > 0.58 else 0)
    for branch in range(branch_count):
        angle = rng.uniform(-2.7, -0.45) if branch == 0 else rng.uniform(-0.4, 0.6)
        length = rng.uniform(16, 34) * (0.75 + strength * 0.35)
        points = [anchor]
        for step in range(1, 5):
            p = step / 4
            jitter = rng.uniform(-5, 5) * (1.0 - p * 0.35)
            points.append(
                (
                    anchor[0] + math.cos(angle) * length * p + jitter,
                    anchor[1] + math.sin(angle) * length * p + rng.uniform(-4, 4),
                )
            )
        rgba = _rgba(color, 120 * strength)
        draw.line(points, fill=rgba, width=2, joint="curve")
        draw.line(points, fill=_rgba("#FFFFFF", 155 * strength), width=1, joint="curve")
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.35)))


def _draw_micro_particles(base: Image.Image, rng: random.Random, anchor: tuple[float, float], color: str, strength: float, kind: str) -> None:
    if kind == "ember":
        count = 3
        drift_y = -1
        spread = (22, 38)
    elif kind == "drip":
        count = 2
        drift_y = 1
        spread = (9, 24)
    elif kind == "dust":
        count = 4
        drift_y = -0.2
        spread = (16, 30)
    else:
        count = 3
        drift_y = -0.6
        spread = (16, 32)
    for _ in range(count):
        angle = rng.uniform(-math.pi, math.pi)
        distance = rng.uniform(*spread) * (0.35 + strength * 0.65)
        x = anchor[0] + math.cos(angle) * distance
        y = anchor[1] + math.sin(angle) * distance + distance * drift_y * 0.28
        radius = rng.uniform(1.1, 3.4) * (0.45 + strength * 0.55)
        _draw_soft_dot(base, x, y, radius, color, 0.10 + 0.24 * strength, 0.8)


def _draw_rising_embers(
    base: Image.Image,
    seed: int,
    anchor: tuple[float, float],
    progress: float,
    strength: float,
    color: str = "#FFB84C",
) -> None:
    rng = random.Random(seed)
    for ember_index in range(4):
        delay = ember_index * rng.uniform(0.10, 0.18)
        local = (progress - delay) / max(0.08, 1.0 - delay)
        if local < 0.0 or local > 1.0:
            continue

        eased = 1.0 - (1.0 - local) * (1.0 - local)
        start_x = anchor[0] + rng.uniform(-18, 18)
        start_y = anchor[1] + rng.uniform(6, 20)
        rise = rng.uniform(42, 74)
        lateral = rng.uniform(-12, 12) * eased
        wiggle = math.sin((local * 1.8 + rng.random()) * math.tau) * rng.uniform(2.0, 5.8)
        x = start_x + lateral + wiggle
        y = start_y - rise * eased
        fade = math.sin(math.pi * local) * strength
        if fade <= 0:
            continue

        radius = rng.uniform(1.4, 3.3) * (0.78 + 0.38 * fade)
        _draw_soft_dot(base, x, y, radius, color, 0.22 + 0.42 * fade, 0.50)
        _draw_soft_dot(base, x, y, radius * 2.5, "#FF7A2A", 0.050 + 0.085 * fade, 1.9)

        # A tiny downward tail makes the upward travel read without becoming a flame.
        tail = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(tail, "RGBA")
        draw.line(
            ((x, y + radius * 0.7), (x - lateral * 0.22, y + 7 + radius * 1.4)),
            fill=_rgba(color, 68 * fade),
            width=1,
        )
        base.alpha_composite(tail.filter(ImageFilter.GaussianBlur(0.55)))

        if ember_index % 2 == 0 and fade > 0.18:
            streak = Image.new("RGBA", base.size, (0, 0, 0, 0))
            streak_draw = ImageDraw.Draw(streak, "RGBA")
            length = rng.uniform(7, 16) * (0.7 + fade * 0.45)
            angle = rng.uniform(-2.25, -1.05)
            x2 = x + math.cos(angle) * length
            y2 = y + math.sin(angle) * length
            streak_draw.line(
                ((x, y), (x2, y2)),
                fill=_rgba("#FFD36E", 96 * fade),
                width=1,
            )
            if fade > 0.42:
                streak_draw.line(
                    ((x, y), (x2, y2)),
                    fill=_rgba("#FFF4C2", 52 * fade),
                    width=1,
                )
            base.alpha_composite(streak.filter(ImageFilter.GaussianBlur(0.18)))


def _draw_material_micro_event(
    base: Image.Image,
    family: str,
    frame: int,
    seed: int,
    strength: float,
    glow_color: str,
    anchor: tuple[float, float],
    progress: float,
) -> None:
    rng = random.Random(seed + frame * 41)
    if strength <= 0:
        return

    if family in {"plasma", "portal", "void"}:
        _draw_micro_arc(base, rng, anchor, glow_color, strength)
        sprite_family = "plasma" if family != "portal" else "portal"
        _place(base, _sprite(sprite_family, frame, seed % SPRITES_PER_FAMILY), anchor, 0.26, rng.uniform(-14, 14), 0.16 + 0.24 * strength, tint=glow_color, tint_amount=0.08)
        return

    if family in {"fire", "magma", "gold"}:
        heat_color = "#FFB84C" if family == "gold" else "#FF7A2A"
        _glow(base, anchor, heat_color, 18 + 10 * strength, 0.028 + 0.068 * strength)
        _draw_rising_embers(base, seed, anchor, progress, strength, "#FFB84C")
        if rng.random() > 0.64 and 0.16 < progress < 0.72:
            spark_anchor = (anchor[0] + rng.uniform(-8, 8), anchor[1] + rng.uniform(-4, 5))
            _draw_micro_arc(base, rng, spark_anchor, "#FFD36E", strength * 0.26)
        return

    if family in {"water", "ice"}:
        sprite_family = "water" if family == "water" else "ice"
        _place(base, _sprite(sprite_family, frame, seed % SPRITES_PER_FAMILY), anchor, 0.24, rng.uniform(-8, 8), 0.11 + 0.21 * strength, tint=glow_color, tint_amount=0.16)
        _draw_micro_particles(base, rng, anchor, "#9EF8FF", strength, "drip")
        return

    if family in {"air", "smoke"}:
        _place(base, _sprite("smoke", frame, seed % SPRITES_PER_FAMILY), anchor, 0.34, rng.uniform(-12, 12), 0.10 + 0.18 * strength, tint=glow_color, tint_amount=0.10)
        return

    if family == "earth":
        _place(base, _sprite("earth", frame, seed % SPRITES_PER_FAMILY), anchor, 0.28, rng.uniform(-8, 8), 0.11 + 0.20 * strength)
        _draw_micro_particles(base, rng, anchor, "#C6A36B", strength, "dust")
        return

    if family == "growth":
        _place(base, _sprite("growth", frame, seed % SPRITES_PER_FAMILY), anchor, 0.28, rng.uniform(-7, 7), 0.10 + 0.20 * strength, tint="#80FFB7", tint_amount=0.12)
        _draw_micro_particles(base, rng, anchor, "#98FFB5", strength, "sprout")


def render_badge_effect(effect_key: str, index: int, frame_count: int = 32, size: int = 256) -> Image.Image:
    """Render one quiet ambient badge overlay frame from material sprites."""
    recipe = EFFECT_RECIPES[effect_key]
    seed = recipe["seed"]
    rng = random.Random(seed)
    t = index / frame_count
    primary = recipe["primary"]
    secondary = recipe.get("secondary")
    tertiary = recipe.get("tertiary")

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_color = recipe.get("glow", "#7EF1FF")
    calm = 0.5 + 0.5 * math.sin(t * math.tau + seed * 0.013)

    # Nearly invisible base breath. The badge art remains the visual hero.
    _glow(img, (128, 132), glow_color, 52 + calm * 7, 0.032 + calm * 0.016)

    event_families = [primary]
    if secondary:
        event_families.append(secondary)
    if tertiary:
        event_families.append(tertiary)

    side_rng = random.Random(seed * 17 + 503)
    sides = ["left", "right", "top", "bottom"]
    side_rng.shuffle(sides)
    centers = [0.14, 0.38, 0.63, 0.86]
    side_rng.shuffle(centers)

    for event_index, side in enumerate(sides):
        family = primary
        local_rng = random.Random(seed + event_index * 937 + len(side) * 41)
        center = (centers[event_index] + local_rng.uniform(-0.035, 0.035)) % 1.0
        width = 0.055 + local_rng.random() * 0.028
        if family in {"fire", "magma", "gold"}:
            width = max(width, 0.088)
        strength = _event_pulse(t, center, width)
        if strength <= 0:
            continue
        progress = _event_progress(t, center, width)
        anchor = _perimeter_anchor(local_rng, family, side)
        # Later accents stay gentle so the multi-side motion does not become noisy.
        strength *= 1.0 if event_index == 0 else 0.82
        _draw_material_micro_event(img, family, index, seed + event_index * 151, strength, glow_color, anchor, progress)

        accent_family = event_families[(event_index + 1) % len(event_families)]
        if accent_family != primary and event_index % 2 == 1:
            accent_anchor = (
                anchor[0] + local_rng.uniform(-8, 8),
                anchor[1] + local_rng.uniform(-8, 8),
            )
            _draw_material_micro_event(
                img,
                accent_family,
                index,
                seed + event_index * 181,
                strength * 0.34,
                glow_color,
                accent_anchor,
                progress,
            )

    return _trim_alpha(img.filter(ImageFilter.GaussianBlur(0.12)), threshold=5)
