"""Generate transparent badge VFX frame sequences.

These frames are intentionally pre-rendered instead of painted live in Qt. The
runtime simply plays PNG overlays, which gives the badge animations a more
game-like asset pipeline and keeps the UI code light.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

try:
    from tools.elemental_vfx_assets import ensure_material_sprites, render_badge_effect
except ModuleNotFoundError:
    from elemental_vfx_assets import ensure_material_sprites, render_badge_effect


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "images" / "badge_vfx"
FRAME_COUNT = 32
SIZE = 256
SCALE = 1
CANVAS = SIZE * SCALE


EFFECTS = (
    "first_route_air",
    "routing_spark_lightning",
    "lni_whisperer_mist",
    "brief_storm_lightning",
    "hundred_club_fire",
    "queue_slayer_earth",
    "final_reviewer_solar",
    "calendar_crusher_water",
    "thousand_crown_meteor",
    "docket_warlord_magma",
    "legendary_circuit_electric",
    "clean_sweep_growth",
    "precision_streak_frost",
    "archive_authority_stone",
    "audit_proof_steel",
    "immaculate_crystal",
    "parallel_boss_air",
    "router_captain_beacon",
    "router_admiral_network",
    "full_bench_six_orbit",
    "six_router_void",
    "no_misses_impact",
    "no_misses_elite_cracks",
    "no_misses_apex_explosion",
    "docket_diva_prism_water",
    "court_hopper_portal",
    "jurisdiction_juggler_swarm",
    "full_spectrum_elements",
    "night_shift_moon_vapor",
    "midnight_operator_neon_fumes",
)


def rgba(hex_color: str, alpha: float) -> tuple[int, int, int, int]:
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
        max(0, min(255, int(alpha))),
    )


def pt(x: float, y: float) -> tuple[int, int]:
    return int(x * SCALE), int(y * SCALE)


def blank() -> Image.Image:
    return Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))


def composite(base: Image.Image, layer: Image.Image) -> None:
    base.alpha_composite(layer)


def blur_layer(layer: Image.Image, radius: float) -> Image.Image:
    return layer.filter(ImageFilter.GaussianBlur(radius * SCALE))


def radial_glow(base: Image.Image, center, radius, color, alpha, steps=18, y_scale=1.0) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    cx, cy = center[0] * SCALE, center[1] * SCALE
    for index in range(steps, 0, -1):
        amount = index / steps
        eased = amount * amount
        rx = radius * amount * SCALE
        ry = radius * y_scale * amount * SCALE
        draw.ellipse(
            (cx - rx, cy - ry, cx + rx, cy + ry),
            fill=rgba(color, alpha * eased * 0.42),
        )
    composite(base, blur_layer(layer, 1.2))


def soft_line(base: Image.Image, points, color, alpha, width, blur=2.0) -> None:
    scaled = [pt(x, y) for x, y in points]
    glow = blank()
    draw = ImageDraw.Draw(glow, "RGBA")
    draw.line(scaled, fill=rgba(color, alpha * 0.34), width=max(1, int(width * 3.5 * SCALE)), joint="curve")
    composite(base, blur_layer(glow, blur))

    core = blank()
    draw = ImageDraw.Draw(core, "RGBA")
    draw.line(scaled, fill=rgba(color, alpha), width=max(1, int(width * SCALE)), joint="curve")
    composite(base, core)


def soft_polygon(base: Image.Image, points, color, alpha, blur=5.0) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.polygon([pt(x, y) for x, y in points], fill=rgba(color, alpha))
    composite(base, blur_layer(layer, blur))


def ring(base: Image.Image, center, rx, ry, color, alpha, width=2.0, blur=1.0) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    cx, cy = center
    draw.ellipse(
        (int((cx - rx) * SCALE), int((cy - ry) * SCALE), int((cx + rx) * SCALE), int((cy + ry) * SCALE)),
        outline=rgba(color, alpha),
        width=max(1, int(width * SCALE)),
    )
    composite(base, blur_layer(layer, blur))


def particle(base: Image.Image, x, y, radius, color, alpha, blur=1.4) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.ellipse(
        (int((x - radius) * SCALE), int((y - radius) * SCALE), int((x + radius) * SCALE), int((y + radius) * SCALE)),
        fill=rgba(color, alpha),
    )
    composite(base, blur_layer(layer, blur))


def star(base: Image.Image, x, y, radius, color, alpha) -> None:
    soft_line(base, [(x - radius, y), (x + radius, y)], color, alpha, 1.4, 1.0)
    soft_line(base, [(x, y - radius), (x, y + radius)], color, alpha, 1.4, 1.0)
    soft_line(base, [(x - radius * 0.55, y - radius * 0.55), (x + radius * 0.55, y + radius * 0.55)], color, alpha * 0.65, 1.0, 0.8)
    soft_line(base, [(x + radius * 0.55, y - radius * 0.55), (x - radius * 0.55, y + radius * 0.55)], color, alpha * 0.65, 1.0, 0.8)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    x = clamp((value - edge0) / (edge1 - edge0))
    return x * x * (3 - 2 * x)


def loop_pulse(t: float, center: float, width: float) -> float:
    distance = abs((t - center + 0.5) % 1.0 - 0.5)
    return clamp(1.0 - distance / width)


def soft_arc(base: Image.Image, center, rx, ry, start, end, color, alpha, width=2.0, blur=2.0) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    cx, cy = center
    bbox = (
        int((cx - rx) * SCALE),
        int((cy - ry) * SCALE),
        int((cx + rx) * SCALE),
        int((cy + ry) * SCALE),
    )

    def draw_arc_segment(a: float, b: float) -> None:
        draw.arc(
            bbox,
            start=a,
            end=b,
            fill=rgba(color, alpha),
            width=max(1, int(width * SCALE)),
        )

    if end >= start:
        draw_arc_segment(start, end)
    else:
        draw_arc_segment(start, 360)
        draw_arc_segment(0, end)
    composite(base, blur_layer(layer, blur))


def diamond_glow(base: Image.Image, center, width, height, color, alpha, line_width=1.8, blur=2.0) -> None:
    cx, cy = center
    points = [
        (cx, cy - height / 2),
        (cx + width / 2, cy),
        (cx, cy + height / 2),
        (cx - width / 2, cy),
        (cx, cy - height / 2),
    ]
    soft_line(base, points, color, alpha, line_width, blur)


def perimeter_sparks(base: Image.Image, t: float, palette, seed=0, count=8, alpha=80) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + rng.random() + index / count) % 1.0
        angle = phase * math.tau
        x = 128 + math.cos(angle) * rng.uniform(62, 88)
        y = 128 + math.sin(angle) * rng.uniform(46, 72)
        flicker = math.sin(math.pi * phase)
        particle(base, x, y, rng.uniform(0.8, 2.0) + flicker * 1.2, palette[index % len(palette)], alpha * flicker, 1.0)


def smoke_puff(base: Image.Image, x, y, radius, color, alpha, blur=4.0, y_scale=0.72) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.ellipse(
        (
            int((x - radius) * SCALE),
            int((y - radius * y_scale) * SCALE),
            int((x + radius) * SCALE),
            int((y + radius * y_scale) * SCALE),
        ),
        fill=rgba(color, alpha),
    )
    composite(base, blur_layer(layer, blur))


def drifting_wisps(base: Image.Image, t: float, palette, seed=0, count=12, alpha=52, rise=62, spread=96) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + index / count + rng.random() * 0.25) % 1.0
        sway = math.sin((phase * 1.8 + rng.random()) * math.tau) * rng.uniform(5, 18)
        x = 128 + (rng.random() - 0.5) * spread + sway
        y = 188 - phase * rise + math.sin((phase + index) * math.tau) * 5
        fade = math.sin(math.pi * phase)
        smoke_puff(base, x, y, rng.uniform(7, 17) * (0.75 + fade * 0.4), palette[index % len(palette)], alpha * fade, blur=rng.uniform(4, 8))


def fire_tongues(base: Image.Image, t: float, colors=("#FF553D", "#FFB84C", "#FFF0C6"), seed=0, count=5, height=54, alpha=72) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + index / count * 0.6 + rng.random() * 0.18) % 1.0
        flicker = 0.45 + 0.55 * math.sin((phase * 2.0 + rng.random()) * math.tau)
        base_x = 128 + (index - (count - 1) / 2) * rng.uniform(11, 17)
        base_y = 194 - rng.uniform(0, 16)
        flame_h = height * (0.55 + flicker * 0.55)
        drift = math.sin((t * 1.8 + index) * math.tau) * 7
        points = [
            (base_x - 11, base_y),
            (base_x + drift * 0.4, base_y - flame_h),
            (base_x + 11, base_y),
            (base_x + 3, base_y - flame_h * 0.32),
            (base_x - 3, base_y - flame_h * 0.28),
        ]
        soft_polygon(base, points, colors[index % len(colors)], alpha * (0.72 + flicker * 0.28), blur=5.0)


def electric_branch(base: Image.Image, start, angle, length, color, alpha, seed=0, segments=5, width=1.3) -> None:
    rng = random.Random(seed)
    x, y = start
    points = [(x, y)]
    for step in range(1, segments + 1):
        progress = step / segments
        jitter = rng.uniform(-12, 12)
        local_angle = angle + math.radians(jitter)
        distance = length / segments
        x += math.cos(local_angle) * distance + rng.uniform(-3, 3)
        y += math.sin(local_angle) * distance + rng.uniform(-3, 3)
        points.append((x, y))
        if step in (2, 4) and rng.random() > 0.35:
            fork_angle = local_angle + rng.choice((-1, 1)) * math.radians(rng.uniform(30, 58))
            fx, fy = x, y
            fork = [(fx, fy)]
            for _ in range(2):
                fx += math.cos(fork_angle) * distance * 0.55 + rng.uniform(-2, 2)
                fy += math.sin(fork_angle) * distance * 0.55 + rng.uniform(-2, 2)
                fork.append((fx, fy))
            soft_line(base, fork, color, alpha * 0.45, width * 0.75, 1.4)
    soft_line(base, points, color, alpha, width, 1.7)
    soft_line(base, points, "#F8FDFF", alpha * 0.42, width * 0.45, 0.5)


def crack_lines(base: Image.Image, t: float, color, seed=0, count=6, alpha=76) -> None:
    rng = random.Random(seed)
    pulse = 0.55 + 0.45 * math.sin(t * math.tau)
    for index in range(count):
        angle = index / count * math.tau + rng.uniform(-0.22, 0.22)
        length = rng.uniform(30, 62) * (0.72 + pulse * 0.32)
        x, y = 128 + math.cos(angle) * 12, 128 + math.sin(angle) * 8
        points = [(x, y)]
        for step in range(1, 5):
            p = step / 4
            points.append(
                (
                    x + math.cos(angle) * length * p + rng.uniform(-5, 5),
                    y + math.sin(angle) * length * p + rng.uniform(-5, 5),
                )
            )
        soft_line(base, points, color, alpha * pulse, 1.0, 1.3)


def water_ripples(base: Image.Image, t: float, color="#7EF1FF", count=3, alpha=54) -> None:
    for offset in range(count):
        phase = (t + offset / count) % 1.0
        fade = (1 - phase) ** 1.7
        ring(base, (128, 136), 30 + phase * 62, 18 + phase * 34, color, alpha * fade, width=1.5, blur=1.8)
    for offset in (0.12, 0.42, 0.72):
        phase = (t + offset) % 1.0
        x = 128 + math.sin(phase * math.tau) * 52
        y = 104 + math.cos(phase * math.tau * 0.75) * 24
        particle(base, x, y, 1.8 + math.sin(math.pi * phase) * 2, "#D8FDFF", 58 * math.sin(math.pi * phase), 1.0)


def growing_leaves(base: Image.Image, t: float, seed=0, count=7, color="#8CFFB8", alpha=72) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = clamp((t * 1.25 + index / count) % 1.0)
        fade = math.sin(math.pi * phase)
        angle = -math.pi / 2 + (index - (count - 1) / 2) * 0.24
        stem_len = 26 + phase * 48 + rng.uniform(-6, 6)
        sx, sy = 128, 184
        ex = sx + math.cos(angle) * stem_len + rng.uniform(-4, 4)
        ey = sy + math.sin(angle) * stem_len
        soft_line(base, [(sx, sy), (ex, ey)], "#64FFD0", alpha * 0.34 * fade, 1.0, 1.4)
        leaf_w = 6 + 4 * fade
        leaf_h = 12 + 7 * fade
        soft_polygon(
            base,
            [(ex, ey - leaf_h), (ex + leaf_w, ey), (ex, ey + leaf_h * 0.45), (ex - leaf_w, ey)],
            color,
            alpha * fade,
            blur=2.0,
        )


def spark_burst(base: Image.Image, center, t: float, palette, seed=0, count=10, alpha=76, radius=60) -> None:
    rng = random.Random(seed)
    burst = smoothstep(0.0, 0.9, loop_pulse(t, 0.36, 0.16))
    if not burst:
        return
    cx, cy = center
    for index in range(count):
        angle = index / count * math.tau + rng.uniform(-0.22, 0.22)
        inner = radius * 0.18
        outer = radius * (0.45 + rng.random() * 0.45) * burst
        points = [
            (cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
            (cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
        ]
        soft_line(base, points, palette[index % len(palette)], alpha * burst, rng.uniform(0.8, 1.5), 1.1)


def save_frame(effect: str, index: int, image: Image.Image) -> None:
    out = image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    r, g, b, a = out.split()
    r = r.point(lambda value: min(255, int(value * 1.16)))
    g = g.point(lambda value: min(255, int(value * 1.16)))
    b = b.point(lambda value: min(255, int(value * 1.16)))
    a = a.point(lambda value: 0 if value < 8 else min(255, int(value * 1.38)))
    out = Image.merge("RGBA", (r, g, b, a))
    out.save(OUT_DIR / effect / f"{index:02d}.png", compress_level=4)


def cleanup_output() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for bad_file in OUT_DIR.glob("oga_*.png"):
        if bad_file.stat().st_size == 0:
            bad_file.unlink()
    for effect_dir in OUT_DIR.iterdir():
        if effect_dir.is_dir() and effect_dir.name not in EFFECTS:
            for old_frame in effect_dir.glob("*.png"):
                old_frame.unlink()
            try:
                effect_dir.rmdir()
            except OSError:
                pass
    for effect in EFFECTS:
        effect_dir = OUT_DIR / effect
        effect_dir.mkdir(parents=True, exist_ok=True)
        for old_frame in effect_dir.glob("*.png"):
            old_frame.unlink()


def motes(image, t, color_a, color_b, seed=0, count=14, band=(0.18, 0.74), alpha=90):
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + index / count + rng.random() * 0.15) % 1.0
        x = 128 + (rng.random() - 0.5) * 120 + math.sin((phase + index) * math.tau) * 8
        y = 190 - phase * 120
        if not (band[0] * 256 <= y <= band[1] * 256):
            continue
        fade = math.sin(math.pi * phase)
        color = color_a if index % 2 else color_b
        particle(image, x, y, 1.3 + fade * 2.4, color, alpha * fade)


def storm_core(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.55 + 0.45 * math.sin(t * math.tau)
    radial_glow(img, (128, 162), 62 + pulse * 8, "#8C4DFF", 155, y_scale=0.62)
    radial_glow(img, (128, 154), 32 + pulse * 5, "#E8DAFF", 85, y_scale=0.40)
    ring(img, (128, 158), 48 + pulse * 5, 18 + pulse * 3, "#A259F7", 74, width=2.0, blur=2.0)

    flash = max(0.0, math.sin((t * 2.0 % 1.0) * math.pi))
    if flash > 0.30:
        rng = random.Random(1700 + index // 2)
        for side in (-1, 1):
            y = 160
            points = [(128, y)]
            for step in range(1, 5):
                x = 128 + side * (step * 9 + rng.random() * 7)
                y -= 7 + rng.random() * 6
                points.append((x, y))
            soft_line(img, points, "#B76CFF", 74 * flash, 1.6, 2.2)
            soft_line(img, points, "#F7EAFF", 48 * flash, 0.8, 0.4)
    motes(img, t, "#B76CFF", "#76F6FF", seed=22, count=10, alpha=56)
    return img


def arcane_route(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 146), 88, "#30D7FF", 30 + pulse * 18, y_scale=0.70)
    radial_glow(img, (128, 160), 58, "#7C4DFF", 32, y_scale=0.42)
    drifting_wisps(img, t, ("#7EF1FF", "#B56CFF", "#D8FDFF"), seed=131, count=13, alpha=50, rise=86, spread=92)
    for side in (-1, 1):
        phase = (t + (0.18 if side > 0 else 0.62)) % 1.0
        angle = -72 + side * 18 + math.sin(phase * math.tau) * 8
        soft_arc(img, (128, 142), 62 + phase * 18, 40 + phase * 8, angle, angle + 76, "#7EF1FF", 38 * math.sin(math.pi * phase), 1.4, 2.2)
    for center in (0.18, 0.52, 0.82):
        hit = smoothstep(0.0, 0.55, loop_pulse(t, center, 0.11))
        if hit:
            px = 128 + math.cos(center * math.tau) * 55
            py = 128 + math.sin(center * math.tau) * 34
            particle(img, px, py, 3.8 + hit * 2.6, "#FFD96A", 90 * hit, 1.2)
            particle(img, px, py, 1.3 + hit, "#F8FDFF", 85 * hit, 0.5)
    perimeter_sparks(img, t, ("#54F5FF", "#FFD96A", "#B56CFF"), seed=131, count=7, alpha=48)
    return img


def gold_sweep(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 126), 92, "#E9B84F", 38 + pulse * 22, y_scale=0.78)
    radial_glow(img, (128, 184), 76, "#FF553D", 38, y_scale=0.36)
    fire_tongues(img, t, seed=8, count=6, height=42, alpha=58)
    drifting_wisps(img, t, ("#FF8A3D", "#FFD96A", "#312231"), seed=18, count=10, alpha=32, rise=70, spread=98)
    flare = smoothstep(0.0, 0.65, loop_pulse(t, 0.36, 0.16))
    if flare:
        soft_arc(img, (128, 104), 74, 46, 206, 334, "#FFD96A", 90 * flare, 2.0, 2.8)
        spark_burst(img, (128, 112), t, ("#FFD96A", "#FFF9DC", "#FF8A3D"), seed=27, count=12, alpha=72, radius=72)
    for i, x_pos in enumerate((94, 128, 162)):
        local = smoothstep(0.0, 0.8, loop_pulse(t, 0.24 + i * 0.08, 0.18))
        soft_line(img, [(x_pos, 74), (x_pos - 9, 92), (x_pos + 9, 92), (x_pos, 74)], "#FFD96A", 40 + local * 42, 1.0, 1.5)
    motes(img, t, "#FFD96A", "#F8FDFF", seed=8, count=10, alpha=52)
    return img


def cyan_scan(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 134), 96, "#43EAFF", 30 + pulse * 18, y_scale=0.78)
    radial_glow(img, (128, 170), 62, "#A75DFF", 18, y_scale=0.42)
    water_ripples(img, t, "#7EF1FF", count=4, alpha=54)
    drifting_wisps(img, t, ("#B6FBFF", "#43EAFF", "#D8FDFF"), seed=77, count=7, alpha=28, rise=46, spread=112)
    for side in (-1, 1):
        soft_line(img, [(128 + side * 72, 64), (128 + side * 88, 82), (128 + side * 88, 174), (128 + side * 70, 194)], "#43EAFF", 34 + pulse * 18, 1.2, 2.0)
    scan_hit = smoothstep(0.0, 0.75, loop_pulse(t, 0.60, 0.17))
    if scan_hit:
        ring(img, (128, 136), 58 + scan_hit * 16, 34 + scan_hit * 12, "#D8FDFF", 54 * scan_hit, width=1.4, blur=1.4)
        particle(img, 186, 86, 2.6 + scan_hit * 1.5, "#B6FBFF", 70 * scan_hit, 0.8)
    return img


def ember_aura(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 174), 92, "#FF553D", 82 + pulse * 36, y_scale=0.42)
    radial_glow(img, (128, 146), 58, "#FFD96A", 36 + pulse * 16, y_scale=0.40)
    drifting_wisps(img, t, ("#38212B", "#5A2E33", "#FF8A3D"), seed=45, count=12, alpha=28, rise=88, spread=104)
    fire_tongues(img, t, seed=44, count=7, height=62, alpha=74)
    soft_arc(img, (128, 148), 82, 62, 202, 338, "#FF8A3D", 66 + pulse * 24, 3.0, 3.2)
    soft_arc(img, (128, 150), 62, 42, 212, 328, "#FFD96A", 42 + pulse * 22, 1.4, 1.8)
    heat = smoothstep(0.0, 0.75, loop_pulse(t, 0.20, 0.13))
    if heat:
        spark_burst(img, (128, 166), t, ("#FF553D", "#FFB84C", "#FFF0C6"), seed=47, count=11, alpha=70, radius=62)
        particle(img, 130, 170, 3 + heat * 3, "#FFF0C6", 76 * heat, 0.8)
    motes(img, t, "#FF8A3D", "#FFD96A", seed=44, count=22, band=(0.18, 0.82), alpha=92)
    return img


def circuit_pulse(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 128), 90, "#43EAFF", 34 + pulse * 22, y_scale=0.82)
    crack_lines(img, t, "#43EAFF", seed=640, count=7, alpha=64)
    for offset, color in ((0.08, "#43EAFF"), (0.41, "#B56CFF"), (0.72, "#D8FDFF")):
        flash = smoothstep(0.0, 0.85, loop_pulse(t, offset, 0.10))
        if flash:
            electric_branch(img, (128, 128), offset * math.tau, 58, color, 82 * flash, seed=900 + index + int(offset * 100), segments=5, width=1.2)
    diamond_glow(img, (128, 128), 128, 104, "#43EAFF", 35 + pulse * 26, 1.2, 2.0)
    diamond_glow(img, (128, 128), 72, 60, "#B56CFF", 34 + pulse * 22, 1.0, 1.3)
    paths = [
        ((128, 128), (96, 106), (66, 106)),
        ((128, 128), (160, 106), (190, 106)),
        ((128, 128), (96, 154), (70, 176)),
        ((128, 128), (160, 154), (186, 176)),
    ]
    for i, path in enumerate(paths):
        local = smoothstep(0.0, 0.85, loop_pulse(t, i * 0.16 + 0.12, 0.18))
        soft_line(img, path, "#43EAFF", 28 + local * 70, 1.3, 2.0)
        particle(img, path[-1][0], path[-1][1], 2.4 + local * 3.0, "#B56CFF", 54 + local * 96, 1.2)
    particle(img, 128, 128, 3 + pulse * 2, "#F8FDFF", 42 + pulse * 46, 0.9)
    return img


def seal_bloom(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    bloom = smoothstep(0.0, 0.85, loop_pulse(t, 0.30, 0.18))
    radial_glow(img, (128, 136), 92 + bloom * 18, "#64FFD0", 30 + bloom * 44, y_scale=0.88)
    growing_leaves(img, t, seed=211, count=8, color="#8CFFB8", alpha=64)
    soft_arc(img, (128, 136), 92 + bloom * 12, 76 + bloom * 10, 205, 335, "#64FFD0", 36 + bloom * 44, 2.4, 2.8)
    soft_arc(img, (128, 136), 82 + bloom * 10, 66 + bloom * 8, 30, 150, "#9EEBFF", 22 + bloom * 26, 1.4, 1.8)
    shield = [(128, 52), (190, 84), (176, 170), (128, 210), (80, 170), (66, 84), (128, 52)]
    soft_line(img, shield, "#64FFD0", 34 + pulse * 18 + bloom * 46, 1.6, 2.4)
    soft_line(img, [(86, 108), (128, 92), (170, 108)], "#FFD96A", 32 + bloom * 34, 1.0, 1.6)
    soft_line(img, [(94, 158), (128, 180), (162, 158)], "#F8FDFF", 24 + bloom * 28, 0.9, 1.4)
    if bloom:
        particle(img, 128, 82, 3 + bloom * 3, "#F8FDFF", 96 * bloom, 0.8)
    return img


def target_rings(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    lock = smoothstep(0.0, 0.8, loop_pulse(t, 0.42, 0.20))
    radial_glow(img, (128, 128), 72, "#43EAFF", 28 + lock * 22, y_scale=0.78)
    crack_lines(img, t, "#D8FDFF", seed=410, count=8, alpha=48 + lock * 38)
    for corner_x, corner_y, sx, sy in ((70, 72, 1, 1), (186, 72, -1, 1), (70, 184, 1, -1), (186, 184, -1, -1)):
        slide = 9 * lock
        x = corner_x + sx * slide
        y = corner_y + sy * slide
        soft_line(img, [(x, y + sy * 20), (x, y), (x + sx * 22, y)], "#F8FDFF", 42 + lock * 54, 1.2, 1.6)
    soft_arc(img, (128, 128), 54 + lock * 10, 54 + lock * 10, 210, 330, "#43EAFF", 38 + pulse * 22, 1.2, 1.4)
    soft_arc(img, (128, 128), 54 + lock * 10, 54 + lock * 10, 30, 150, "#B56CFF", 34 + pulse * 20, 1.2, 1.4)
    particle(img, 128, 128, 2.2 + lock * 2.2, "#FFD96A", 78 + lock * 64, 1.0)
    return img


def signal_wave(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 110), 78, "#43EAFF", 30 + pulse * 18, y_scale=0.50)
    drifting_wisps(img, t, ("#D8FDFF", "#7EF1FF", "#B56CFF"), seed=602, count=11, alpha=36, rise=42, spread=124)
    particle(img, 128, 108, 3.8 + pulse * 1.5, "#FFD96A", 92 + pulse * 38, 1.0)
    for offset, color in ((0.0, "#43EAFF"), (0.22, "#B56CFF"), (0.44, "#F8FDFF")):
        p = (t + offset) % 1.0
        alpha = 88 * (1 - p) ** 1.7
        soft_arc(img, (128, 112), 26 + p * 72, 18 + p * 42, 206, 334, color, alpha, 2.2, 2.0)
        soft_arc(img, (128, 112), 26 + p * 72, 18 + p * 42, 26, 154, color, alpha * 0.45, 1.0, 1.4)
    particle(img, 128, 108, 2.4 + pulse * 2.2, "#F8FDFF", 34 + pulse * 44, 0.8)
    return img


def network_pulse(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 88, "#43EAFF", 28 + pulse * 16, y_scale=0.72)
    nodes = [(128, 72), (78, 112), (178, 112), (92, 174), (164, 174), (128, 132)]
    drifting_wisps(img, t, ("#132B44", "#43EAFF", "#B56CFF"), seed=733, count=9, alpha=26, rise=52, spread=116)
    for a, b in ((0, 1), (0, 2), (1, 3), (2, 4), (3, 4)):
        soft_line(img, [nodes[a], nodes[b]], "#43EAFF", 20 + pulse * 26, 0.9, 1.6)
    for i, (x, y) in enumerate(nodes):
        local = smoothstep(0.0, 0.85, loop_pulse(t, i * 0.13, 0.15))
        particle(img, x, y, 2.0 + local * 3.6, "#B56CFF" if i in (0, 5) else "#43EAFF", 42 + local * 106, 1.1)
        if local > 0.55:
            spark_burst(img, (x, y), t, ("#43EAFF", "#F8FDFF"), seed=771 + i, count=6, alpha=30, radius=24)
    diamond_glow(img, (128, 132), 50, 42, "#FFD96A", 24 + pulse * 28, 0.8, 1.2)
    for center in (0.12, 0.45, 0.78):
        hit = smoothstep(0.0, 0.8, loop_pulse(t, center, 0.08))
        if hit:
            x = 128 + math.cos(center * math.tau) * 82
            y = 132 + math.sin(center * math.tau) * 58
            particle(img, x, y, 3.0 + hit * 2.5, "#F8FDFF", 80 * hit, 1.0)
    return img


def blade_glint(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 76, "#B56CFF", 24 + idle * 16, y_scale=0.58)
    crack_lines(img, t, "#FFD96A", seed=919, count=7, alpha=54)
    spark_burst(img, (128, 132), t, ("#FFD96A", "#F8FDFF", "#B56CFF"), seed=920, count=14, alpha=72, radius=76)
    if smoothstep(0.0, 0.8, loop_pulse(t, 0.72, 0.10)):
        hit = smoothstep(0.0, 0.8, loop_pulse(t, 0.72, 0.10))
        soft_arc(img, (128, 132), 78, 58, 210, 314, "#43EAFF", 42 * hit, 1.6, 1.9)
    return img


def apex_crystal(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    coronation = smoothstep(0.0, 0.88, loop_pulse(t, 0.46, 0.16))
    radial_glow(img, (128, 126), 96 + pulse * 8, "#FFD96A", 46 + pulse * 26 + coronation * 34, y_scale=0.95)
    radial_glow(img, (128, 164), 62, "#B56CFF", 34, y_scale=0.48)
    soft_arc(img, (128, 126), 96, 78, 204, 336, "#FFD96A", 40 + coronation * 44, 2.2, 2.4)
    soft_arc(img, (128, 126), 90, 72, 28, 152, "#F8FDFF", 18 + coronation * 24, 1.0, 1.2)
    drifting_wisps(img, t, ("#FFF6C8", "#FFD96A", "#B56CFF"), seed=118, count=8, alpha=28, rise=58, spread=96)
    diamond_glow(img, (128, 126), 92, 144, "#FFF6C8", 32 + pulse * 28, 1.2, 2.0)
    diamond_glow(img, (128, 126), 48, 88, "#FFD96A", 44 + coronation * 42, 1.0, 1.2)
    water_ripples(img, t, "#FFF6C8", count=2, alpha=22)
    if coronation:
        soft_arc(img, (128, 96), 76, 40, 200, 340, "#FFD96A", 62 * coronation, 2.0, 2.2)
        spark_burst(img, (128, 118), t, ("#FFD96A", "#FFF6C8"), seed=119, count=10, alpha=72, radius=64)
        particle(img, 128, 70, 3 + coronation * 4, "#F8FDFF", 95 * coronation, 0.8)
    return img


def orbit_aura(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 88, "#43EAFF", 28 + pulse * 16, y_scale=0.72)
    drifting_wisps(img, t, ("#7EF1FF", "#FFD96A", "#B56CFF"), seed=514, count=10, alpha=32, rise=58, spread=122)
    for offset, color, alpha in ((0.0, "#43EAFF", 58), (0.48, "#FFD96A", 50), (0.74, "#B56CFF", 44)):
        angle = (t + offset) * math.tau
        start = math.degrees(angle) - 28
        end = math.degrees(angle) + 42
        soft_arc(img, (128, 132), 84, 50, start, end, color, alpha, 2.0, 2.4)
        x = 128 + math.cos(angle) * 84
        y = 132 + math.sin(angle) * 50
        particle(img, x, y, 3.0, color, 88, 1.2)
    diamond_glow(img, (128, 132), 58, 48, "#F8FDFF", 20 + pulse * 20, 0.8, 1.0)
    return img


def prism_sweep(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 130), 96, "#43EAFF", 26 + pulse * 14, y_scale=0.90)
    colors = ["#FF67B5", "#FFD96A", "#64FFD0", "#43EAFF", "#B56CFF"]
    water_ripples(img, t, "#64FFD0", count=3, alpha=34)
    drifting_wisps(img, t, tuple(colors), seed=514, count=16, alpha=34, rise=76, spread=134)
    caustic = smoothstep(0.0, 0.85, loop_pulse(t, 0.58, 0.16))
    if caustic:
        diamond_glow(img, (128, 130), 118, 104, "#F8FDFF", 28 + caustic * 40, 1.0, 1.5)
        spark_burst(img, (128, 132), t, tuple(colors), seed=515, count=12, alpha=54, radius=70)
    perimeter_sparks(img, t, tuple(colors), seed=514, count=9, alpha=42)
    return img


def terminal_scan(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 136), 90, "#64FFD0", 22 + pulse * 18, y_scale=0.74)
    drifting_wisps(img, t, ("#64FFD0", "#7EF1FF", "#233C37"), seed=3100, count=16, alpha=38, rise=76, spread=116)
    rng = random.Random(3100)
    for row in range(8):
        phase = (t + row * 0.11) % 1.0
        alpha = 44 * math.sin(math.pi * phase)
        x = 74 + rng.randint(0, 18) + (row % 4) * 26
        yy = 78 + row * 13
        smoke_puff(img, x, yy, 3 + phase * 6, "#64FFD0", alpha, blur=2.6, y_scale=0.5)
    glitch = smoothstep(0.0, 0.85, loop_pulse(t, 0.73, 0.10))
    if glitch:
        spark_burst(img, (128, 128), t, ("#64FFD0", "#43EAFF", "#F8FDFF"), seed=3112, count=8, alpha=48, radius=54)
        particle(img, 128, 128, 3 + glitch * 2, "#F8FDFF", 58 * glitch, 0.9)
    return img


def shard(base: Image.Image, x, y, size, color, alpha, angle=0.0, blur=1.2) -> None:
    points = []
    for offset in (0, 2.1, 4.2):
        points.append(
            (
                x + math.cos(angle + offset) * size,
                y + math.sin(angle + offset) * size * 0.72,
            )
        )
    soft_polygon(base, points, color, alpha, blur=blur)


def dust_cloud(base: Image.Image, t: float, seed=0, color="#8D7050", count=10, alpha=42) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + index / count + rng.random() * 0.14) % 1.0
        fade = math.sin(math.pi * phase)
        x = 128 + (rng.random() - 0.5) * 120 + math.sin(phase * math.tau + index) * 10
        y = 178 - phase * 34 + rng.uniform(-6, 8)
        smoke_puff(base, x, y, rng.uniform(8, 18), color, alpha * fade, blur=5.8, y_scale=0.54)


def air_ribbons(base: Image.Image, t: float, seed=0, color="#D8FDFF", alpha=58, count=4, spread=88) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + index / count + rng.random() * 0.08) % 1.0
        y = 76 + index * 30 + math.sin((phase + index) * math.tau) * 8
        x0 = 52 + math.sin(phase * math.tau) * 10
        x1 = 204 - math.cos(phase * math.tau) * 12
        points = [
            (x0, y),
            (128 - spread * 0.16, y - 12 * math.sin(phase * math.tau)),
            (128 + spread * 0.16, y + 12 * math.cos(phase * math.tau)),
            (x1, y - 4),
        ]
        soft_line(base, points, color, alpha * math.sin(math.pi * phase), 1.7, 2.8)


def water_drops(base: Image.Image, t: float, seed=0, color="#B6FBFF", count=8, alpha=78) -> None:
    rng = random.Random(seed)
    for index in range(count):
        phase = (t + index / count + rng.random() * 0.1) % 1.0
        x = 72 + rng.random() * 112 + math.sin(phase * math.tau) * 4
        y = 58 + phase * 124
        fade = math.sin(math.pi * phase)
        particle(base, x, y, 1.6 + fade * 2.5, color, alpha * fade, 0.8)
        if fade > 0.78:
            ring(base, (x, y), 7 + fade * 5, 3 + fade * 3, color, 38 * fade, width=1.0, blur=1.1)


def earth_effect(index: int, seed=0, glow="#8D7050", crack="#FFD96A", dust="#6B5444") -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 158), 104, glow, 54 + pulse * 26, y_scale=0.50)
    dust_cloud(img, t, seed=seed + 1, color=dust, count=16, alpha=62)
    crack_lines(img, t, crack, seed=seed + 2, count=11, alpha=104)
    for i in range(12):
        local = (t + i / 9) % 1.0
        fade = math.sin(math.pi * local)
        x = 58 + i * 13 + math.sin(local * math.tau + i) * 9
        y = 168 - fade * 36
        shard(img, x, y, 5 + fade * 5, glow, 56 + fade * 64, angle=i * 0.8)
    return img


def fire_effect(index: int, seed=0, intensity=1.0, smoke=True) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 174), 108, "#FF553D", (92 + pulse * 64) * intensity, y_scale=0.46)
    radial_glow(img, (128, 136), 64, "#FFD96A", (42 + pulse * 34) * intensity, y_scale=0.42)
    fire_tongues(img, t, seed=seed, count=9, height=74 * intensity, alpha=92 * intensity)
    soft_arc(img, (128, 162), 94, 54, 200, 340, "#FF8A3D", 68 * intensity, 2.4, 3.0)
    soft_arc(img, (128, 158), 68, 38, 212, 328, "#FFD96A", 54 * intensity, 1.4, 1.8)
    motes(img, t, "#FF8A3D", "#FFD96A", seed=seed + 9, count=30, band=(0.12, 0.80), alpha=124 * intensity)
    spark_burst(img, (128, 150), t, ("#FF553D", "#FFB84C", "#FFF0C6"), seed=seed + 12, count=14, alpha=82 * intensity, radius=78)
    if smoke:
        drifting_wisps(img, t, ("#3B2430", "#5A2E33", "#FF8A3D"), seed=seed + 4, count=10, alpha=28, rise=88, spread=108)
    return img


def water_effect(index: int, seed=0, color="#7EF1FF", deep="#2456B8", drops=True) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 144), 108, color, 50 + pulse * 28, y_scale=0.76)
    radial_glow(img, (128, 182), 82, deep, 30, y_scale=0.38)
    water_ripples(img, t, color, count=5, alpha=104)
    soft_arc(img, (128, 136), 94, 58, 190, 350, color, 70, 2.6, 2.6)
    soft_arc(img, (128, 138), 78, 44, 20, 160, "#D8FDFF", 42, 1.4, 1.6)
    for offset in (0.0, 0.34, 0.68):
        phase = (t + offset) % 1.0
        y = 100 + math.sin(phase * math.tau) * 22
        soft_line(img, [(44, y), (88, y + 12), (128, y - 10), (170, y + 12), (212, y - 2)], "#D8FDFF", 58 * math.sin(math.pi * phase), 1.5, 2.2)
    if drops:
        water_drops(img, t, seed=seed, color="#D8FDFF", count=13, alpha=108)
    return img


def air_effect(index: int, seed=0, color="#D8FDFF", accent="#7EF1FF", storm=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 110, accent, 38 + pulse * 22, y_scale=0.60)
    air_ribbons(img, t, seed=seed, color=color, alpha=96 if storm else 82, count=6 if storm else 5, spread=112)
    drifting_wisps(img, t, (color, accent, "#B56CFF"), seed=seed + 3, count=14 if storm else 11, alpha=56, rise=62, spread=148)
    for offset in (0.12, 0.48, 0.78):
        phase = (t + offset) % 1.0
        soft_arc(img, (128, 136), 88 + phase * 10, 52 + phase * 6, 188 + phase * 70, 282 + phase * 70, color, 42 * math.sin(math.pi * phase), 1.4, 2.4)
    if storm:
        for offset in (0.18, 0.52):
            flash = smoothstep(0.0, 0.9, loop_pulse(t, offset, 0.10))
            if flash:
                electric_branch(img, (128, 132), -math.pi / 2 + offset * 0.9, 52, "#F8FDFF", 72 * flash, seed=seed + index + int(offset * 100), segments=4)
    return img


def lightning_effect(index: int, seed=0, color="#7EF1FF", accent="#B56CFF", branches=4) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 98, color, 52 + pulse * 34, y_scale=0.72)
    diamond_glow(img, (128, 132), 94, 112, accent, 34 + pulse * 34, 1.2, 1.6)
    for i in range(branches):
        center = (i / branches + 0.12) % 1.0
        idle_angle = i / branches * math.tau - math.pi / 2 + math.sin(t * math.tau + i) * 0.12
        electric_branch(img, (128, 132), idle_angle, 44, color if i % 2 else accent, 36 + pulse * 22, seed=seed + i * 37, segments=4, width=1.0)
        flash = smoothstep(0.0, 0.9, loop_pulse(t, center, 0.11))
        if flash:
            angle = i / branches * math.tau - math.pi / 2
            electric_branch(img, (128, 132), angle, 66, color if i % 2 else accent, 118 * flash, seed=seed + index * 7 + i * 29, segments=5, width=1.5)
    perimeter_sparks(img, t, (color, accent, "#F8FDFF"), seed=seed + 17, count=14, alpha=82)
    return img


def growth_effect(index: int, seed=0, flower=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 150), 94, "#64FFD0", 34 + pulse * 24, y_scale=0.74)
    growing_leaves(img, t, seed=seed, count=11 if flower else 8, color="#8CFFB8", alpha=90)
    for i in range(8 if flower else 5):
        phase = (t + i / 8) % 1.0
        fade = math.sin(math.pi * phase)
        x = 84 + i * 12 + math.sin(phase * math.tau) * 8
        y = 116 - fade * 16
        particle(img, x, y, 1.6 + fade * 2.4, "#FFD96A" if flower else "#D8FDFF", 76 * fade, 0.8)
    return img


def frost_effect(index: int, seed=0, intense=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 96, "#B6FBFF", 34 + pulse * 24, y_scale=0.78)
    radial_glow(img, (128, 180), 66, "#6E7CFF", 20, y_scale=0.36)
    for i in range(8 if intense else 6):
        angle = -math.pi / 2 + (i - 3.5) * 0.24
        length = 38 + math.sin(t * math.tau + i) * 8
        x = 128 + math.cos(angle) * 16
        y = 162 + math.sin(angle) * 10
        soft_line(img, [(x, y), (x + math.cos(angle) * length, y + math.sin(angle) * length)], "#D8FDFF", 64 + pulse * 42, 1.0, 1.2)
    water_drops(img, (t + 0.4) % 1.0, seed=seed, color="#D8FDFF", count=10, alpha=54)
    crack_lines(img, t, "#B6FBFF", seed=seed + 4, count=5, alpha=44 if not intense else 70)
    return img


def vapor_effect(index: int, seed=0, color="#64FFD0", accent="#7EF1FF", poison=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 146), 96, color, 26 + pulse * 22, y_scale=0.70)
    drifting_wisps(img, t, (color, accent, "#233C37" if poison else "#2A2346"), seed=seed, count=18 if poison else 14, alpha=48, rise=86, spread=128)
    for i in range(8 if poison else 5):
        phase = (t + i / 8) % 1.0
        fade = math.sin(math.pi * phase)
        x = 86 + i * 12 + math.sin(phase * math.tau) * 12
        y = 152 - phase * 70
        particle(img, x, y, 1.3 + fade * 3, color if i % 2 else accent, 64 * fade, 1.1)
    return img


def portal_effect(index: int, seed=0, swarm=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.45 + 0.55 * math.sin(t * math.tau)
    radial_glow(img, (128, 136), 96, "#7EF1FF", 32 + pulse * 22, y_scale=0.74)
    radial_glow(img, (128, 152), 58, "#B56CFF", 28, y_scale=0.46)
    for offset, color in ((0.0, "#7EF1FF"), (0.33, "#FFD96A"), (0.66, "#B56CFF")):
        phase = (t + offset) % 1.0
        start = math.degrees(phase * math.tau)
        soft_arc(img, (128, 136), 76 + phase * 8, 48 + phase * 6, start, start + 82, color, 62, 2.0, 2.2)
        x = 128 + math.cos(phase * math.tau) * 76
        y = 136 + math.sin(phase * math.tau) * 48
        particle(img, x, y, 2.8, color, 88, 1.0)
    if swarm:
        for i in range(15):
            phase = (t * 1.4 + i / 15) % 1.0
            angle = phase * math.tau
            x = 128 + math.cos(angle * 1.3 + i) * (42 + 30 * math.sin(math.pi * phase))
            y = 136 + math.sin(angle + i * 0.5) * (28 + 18 * math.cos(math.pi * phase))
            particle(img, x, y, 1.4 + math.sin(math.pi * phase), "#FFD96A" if i % 3 == 0 else "#7EF1FF", 74, 0.8)
    return img


def spectrum_effect(index: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    radial_glow(img, (128, 132), 104, "#7EF1FF", 42, y_scale=0.82)
    water_ripples(img, t, "#64FFD0", count=3, alpha=56)
    fire_tongues(img, t, colors=("#FF553D", "#FFD96A", "#FF67B5"), seed=515, count=5, height=48, alpha=62)
    crack_lines(img, t, "#FFD96A", seed=516, count=7, alpha=62)
    air_ribbons(img, t, seed=517, color="#D8FDFF", alpha=58, count=4)
    spark_burst(img, (128, 132), t, ("#FF67B5", "#FFD96A", "#64FFD0", "#43EAFF", "#B56CFF"), seed=518, count=16, alpha=76, radius=80)
    perimeter_sparks(img, t, ("#FF67B5", "#FFD96A", "#64FFD0", "#43EAFF", "#B56CFF"), seed=519, count=16, alpha=74)
    return img


def moon_vapor_effect(index: int, seed=0, neon=False) -> Image.Image:
    t = index / FRAME_COUNT
    moon = blank()
    color = "#64FFD0" if neon else "#B56CFF"
    accent = "#7EF1FF" if neon else "#D8FDFF"
    radial_glow(moon, (128, 130), 88, color, 28, y_scale=0.72)
    moon_x = 134 + math.sin(t * math.tau) * 4
    moon_y = 72 + math.cos(t * math.tau) * 2
    particle(moon, moon_x, moon_y, 17 if not neon else 12, accent, 70, 2.4)
    particle(moon, moon_x + 8, moon_y - 5, 15 if not neon else 10, "#08111D", 88, 2.2)
    base = vapor_effect(index, seed=seed, color=color, accent=accent, poison=neon)
    composite(base, moon)
    return base


def first_route_air(index: int) -> Image.Image:
    return air_effect(index, seed=101, color="#F8FDFF", accent="#7EF1FF")


def routing_spark_lightning(index: int) -> Image.Image:
    return lightning_effect(index, seed=111, color="#FFD96A", accent="#7EF1FF", branches=3)


def lni_whisperer_mist(index: int) -> Image.Image:
    return vapor_effect(index, seed=121, color="#B6FBFF", accent="#B56CFF")


def brief_storm_lightning(index: int) -> Image.Image:
    return lightning_effect(index, seed=131, color="#B56CFF", accent="#7EF1FF", branches=5)


def hundred_club_fire(index: int) -> Image.Image:
    return fire_effect(index, seed=141, intensity=0.92)


def queue_slayer_earth(index: int) -> Image.Image:
    return earth_effect(index, seed=151, glow="#6B5444", crack="#FFD96A", dust="#4A3A33")


def final_reviewer_solar(index: int) -> Image.Image:
    return fire_effect(index, seed=161, intensity=0.78, smoke=False)


def calendar_crusher_water(index: int) -> Image.Image:
    return water_effect(index, seed=171, color="#B6FBFF", deep="#2456B8")


def thousand_crown_meteor(index: int) -> Image.Image:
    return fire_effect(index, seed=181, intensity=1.12)


def docket_warlord_magma(index: int) -> Image.Image:
    img = earth_effect(index, seed=191, glow="#8A3A2A", crack="#FF553D", dust="#3B2430")
    composite(img, fire_effect(index, seed=192, intensity=0.62))
    return img


def legendary_circuit_electric(index: int) -> Image.Image:
    return lightning_effect(index, seed=201, color="#7EF1FF", accent="#B56CFF", branches=6)


def clean_sweep_growth(index: int) -> Image.Image:
    return growth_effect(index, seed=211, flower=True)


def precision_streak_frost(index: int) -> Image.Image:
    return frost_effect(index, seed=221)


def archive_authority_stone(index: int) -> Image.Image:
    return earth_effect(index, seed=231, glow="#6B705C", crack="#64FFD0", dust="#5C6658")


def audit_proof_steel(index: int) -> Image.Image:
    return frost_effect(index, seed=241, intense=True)


def immaculate_crystal(index: int) -> Image.Image:
    return frost_effect(index, seed=251, intense=True)


def parallel_boss_air(index: int) -> Image.Image:
    return air_effect(index, seed=261, color="#D8FDFF", accent="#7EF1FF", storm=True)


def router_captain_beacon(index: int) -> Image.Image:
    return lightning_effect(index, seed=271, color="#7EF1FF", accent="#FFD96A", branches=4)


def router_admiral_network(index: int) -> Image.Image:
    return lightning_effect(index, seed=281, color="#43EAFF", accent="#B56CFF", branches=5)


def full_bench_six_orbit(index: int) -> Image.Image:
    return portal_effect(index, seed=291, swarm=True)


def six_router_void(index: int) -> Image.Image:
    return vapor_effect(index, seed=301, color="#8C4DFF", accent="#43EAFF", poison=True)


def no_misses_impact(index: int) -> Image.Image:
    return earth_effect(index, seed=311, glow="#7D6548", crack="#FFD96A", dust="#4A3A33")


def no_misses_elite_cracks(index: int) -> Image.Image:
    return earth_effect(index, seed=321, glow="#3C4555", crack="#D8FDFF", dust="#2E3542")


def no_misses_apex_explosion(index: int) -> Image.Image:
    img = fire_effect(index, seed=331, intensity=1.05)
    spark_burst(img, (128, 128), index / FRAME_COUNT, ("#FFD96A", "#F8FDFF"), seed=332, count=18, alpha=86, radius=88)
    return img


def docket_diva_prism_water(index: int) -> Image.Image:
    img = water_effect(index, seed=341, color="#FF67B5", deep="#2456B8", drops=False)
    water_ripples(img, index / FRAME_COUNT, "#64FFD0", count=3, alpha=48)
    return img


def court_hopper_portal(index: int) -> Image.Image:
    return portal_effect(index, seed=351)


def jurisdiction_juggler_swarm(index: int) -> Image.Image:
    return portal_effect(index, seed=361, swarm=True)


def full_spectrum_elements(index: int) -> Image.Image:
    return spectrum_effect(index)


def night_shift_moon_vapor(index: int) -> Image.Image:
    return moon_vapor_effect(index, seed=371, neon=False)


def midnight_operator_neon_fumes(index: int) -> Image.Image:
    return moon_vapor_effect(index, seed=381, neon=True)


# Cinematic badge VFX pass -------------------------------------------------
# These functions intentionally override the earlier lightweight recipes. The
# design target is closer to splash/loadout animation: one readable energy
# source, a clear element silhouette, a short impact beat, and lingering residue.

def _cinematic_t(index: int) -> tuple[float, float, float]:
    t = index / FRAME_COUNT
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    impact = smoothstep(0.0, 0.88, loop_pulse(t, 0.55, 0.13))
    return t, idle, impact


def _source_core(img: Image.Image, source, color, accent, idle, impact, radius=18) -> None:
    x, y = source
    radial_glow(img, source, radius * 3.4, color, 48 + idle * 34 + impact * 60, y_scale=0.82)
    particle(img, x, y, radius * (0.45 + impact * 0.22), color, 96 + impact * 70, 1.8)
    particle(img, x, y, radius * (0.18 + impact * 0.16), accent, 90 + impact * 84, 0.8)


def _embers(img: Image.Image, t: float, seed: int, colors, count=26, alpha=105, rise=112) -> None:
    rng = random.Random(seed)
    for i in range(count):
        phase = (t + i / count + rng.random() * 0.12) % 1.0
        fade = math.sin(math.pi * phase)
        x = 128 + (rng.random() - 0.5) * rng.uniform(70, 138) + math.sin((phase + i) * math.tau) * 9
        y = 202 - phase * rise + rng.uniform(-7, 8)
        color = colors[i % len(colors)]
        particle(img, x, y, rng.uniform(1.0, 2.4) + fade * 1.8, color, alpha * fade, 0.9)


def _flame_column(img: Image.Image, t: float, seed: int, source=(128, 186), colors=("#FF3D2E", "#FF9D32", "#FFE5A3"), height=92, width=78, intensity=1.0) -> None:
    rng = random.Random(seed)
    sx, sy = source
    for i in range(8):
        phase = (t * 1.15 + i * 0.11 + rng.random() * 0.08) % 1.0
        flicker = 0.55 + 0.45 * math.sin((phase * 2.2 + i * 0.17) * math.tau)
        base_x = sx + (i - 3.5) * width / 9 + math.sin(t * math.tau + i) * 6
        flame_h = height * (0.48 + flicker * 0.58) * intensity
        flame_w = width * (0.08 + flicker * 0.06) * intensity
        tip = (base_x + math.sin((t + i) * math.tau) * 14, sy - flame_h)
        points = [
            (base_x - flame_w * 1.15, sy + 4),
            (base_x - flame_w * 0.36, sy - flame_h * 0.32),
            tip,
            (base_x + flame_w * 0.42, sy - flame_h * 0.34),
            (base_x + flame_w * 1.10, sy + 3),
            (base_x, sy - flame_h * 0.16),
        ]
        soft_polygon(img, points, colors[i % len(colors)], 72 * intensity, blur=5.0)
    _embers(img, t, seed + 40, colors, count=24, alpha=96 * intensity, rise=126)


def _lightning_storm(img: Image.Image, t: float, seed: int, source=(128, 150), colors=("#7EF1FF", "#B56CFF"), branches=5, reach=92, intensity=1.0) -> None:
    rng = random.Random(seed + int(t * FRAME_COUNT) * 17)
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    for i in range(branches):
        base_angle = -math.pi / 2 + (i - (branches - 1) / 2) * 0.48
        electric_branch(
            img,
            source,
            base_angle + math.sin(t * math.tau + i) * 0.12,
            reach * (0.62 + idle * 0.12),
            colors[i % len(colors)],
            (52 + idle * 26) * intensity,
            seed=seed + i * 31,
            segments=5,
            width=1.2,
        )
    for i in range(2):
        flash = smoothstep(0.0, 0.90, loop_pulse(t, 0.36 + i * 0.24, 0.08))
        if flash:
            angle = rng.uniform(-2.8, 0.3)
            electric_branch(img, source, angle, reach * 1.05, colors[(i + 1) % len(colors)], 132 * flash * intensity, seed=seed + rng.randint(1, 900), segments=6, width=1.8)
    perimeter_sparks(img, t, (*colors, "#F8FDFF"), seed=seed + 9, count=14, alpha=80 * intensity)


def _water_surge(img: Image.Image, t: float, seed: int, source=(128, 166), color="#65E9FF", accent="#D8FDFF", intensity=1.0) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, source, 88, color, 45 + idle * 28, y_scale=0.54)
    for i in range(4):
        phase = (t + i * 0.24) % 1.0
        fade = math.sin(math.pi * phase)
        y = source[1] - 48 * fade + i * 3
        soft_line(
            img,
            [(42, y + 7), (86, y - 8), (126, y + 10), (170, y - 7), (214, y + 4)],
            accent if i % 2 else color,
            76 * fade * intensity,
            2.0,
            2.6,
        )
    water_ripples(img, t, color, count=5, alpha=92 * intensity)
    water_drops(img, t, seed=seed, color=accent, count=16, alpha=118 * intensity)


def _earth_impact(img: Image.Image, t: float, seed: int, source=(128, 172), glow="#7A634A", crack="#FFD96A", dust="#58483C", intensity=1.0) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    impact = smoothstep(0.0, 0.9, loop_pulse(t, 0.48, 0.16))
    radial_glow(img, source, 100, glow, (58 + idle * 24 + impact * 42) * intensity, y_scale=0.42)
    dust_cloud(img, t, seed=seed + 1, color=dust, count=18, alpha=64 * intensity)
    crack_lines(img, t, crack, seed=seed + 2, count=12, alpha=(86 + impact * 52) * intensity)
    for i in range(12):
        phase = (t + i / 12) % 1.0
        fade = math.sin(math.pi * phase)
        angle = -math.pi + i / 11 * math.pi
        x = source[0] + math.cos(angle) * (24 + fade * 56)
        y = source[1] + math.sin(angle) * (10 + fade * 28)
        shard(img, x, y, 4 + fade * 6, glow, (58 + impact * 44) * fade * intensity, angle=angle)
    if impact:
        spark_burst(img, source, t, (crack, "#F8FDFF"), seed=seed + 12, count=14, alpha=72 * impact * intensity, radius=78)


def _wind_vortex(img: Image.Image, t: float, seed: int, source=(128, 132), color="#D8FDFF", accent="#7EF1FF", intensity=1.0) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, source, 104, accent, 38 + idle * 24, y_scale=0.62)
    for i in range(5):
        phase = (t + i * 0.18) % 1.0
        start = math.degrees(phase * math.tau) + i * 12
        soft_arc(img, source, 52 + i * 10, 28 + i * 7, start, start + 145, color if i % 2 else accent, (52 + idle * 18) * intensity, 2.0, 2.8)
    drifting_wisps(img, t, (color, accent, "#B56CFF"), seed=seed + 3, count=15, alpha=58 * intensity, rise=70, spread=152)


def _growth_bloom(img: Image.Image, t: float, seed: int, source=(128, 190), flower=False) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 150), 104, "#64FFD0", 44 + idle * 28, y_scale=0.80)
    growing_leaves(img, t, seed=seed, count=13 if flower else 10, color="#9EFFA8", alpha=102)
    for i in range(10 if flower else 6):
        phase = (t * 1.2 + i / 10) % 1.0
        fade = math.sin(math.pi * phase)
        x = source[0] + (i - 4.5) * 11 + math.sin(phase * math.tau + i) * 9
        y = source[1] - 78 * fade
        color = "#FFD96A" if flower else "#D8FDFF"
        particle(img, x, y, 2 + fade * 4, color, 96 * fade, 1.0)


def _frost_shards(img: Image.Image, t: float, seed: int, source=(128, 158), color="#D8FDFF", accent="#7EF1FF", intense=False) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    impact = smoothstep(0.0, 0.86, loop_pulse(t, 0.42, 0.15))
    radial_glow(img, source, 100, accent, 42 + idle * 28 + impact * 30, y_scale=0.76)
    for i in range(9 if intense else 7):
        angle = -math.pi / 2 + (i - 4) * 0.26
        length = 42 + idle * 8 + impact * 26
        x = source[0] + math.cos(angle) * 15
        y = source[1] + math.sin(angle) * 10
        soft_line(img, [(x, y), (x + math.cos(angle) * length, y + math.sin(angle) * length)], color, 78 + impact * 52, 1.5, 1.4)
        shard(img, x + math.cos(angle) * length, y + math.sin(angle) * length, 5 + impact * 3, accent, 70 + impact * 44, angle=angle)
    water_drops(img, (t + 0.35) % 1.0, seed=seed, color=color, count=12, alpha=68)


def _vapor_coil(img: Image.Image, t: float, seed: int, color="#64FFD0", accent="#7EF1FF", toxic=False, moon=False) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 148), 106, color, 36 + idle * 24, y_scale=0.72)
    drifting_wisps(img, t, (color, accent, "#20352F" if toxic else "#2A2346"), seed=seed, count=20 if toxic else 15, alpha=60, rise=98, spread=140)
    for i in range(4):
        phase = (t + i * 0.25) % 1.0
        start = math.degrees(phase * math.tau)
        soft_arc(img, (128, 146), 42 + i * 14, 26 + i * 9, start, start + 118, color if i % 2 else accent, 40 * math.sin(math.pi * phase), 1.8, 2.8)
    if moon:
        mx = 136 + math.sin(t * math.tau) * 5
        my = 70 + math.cos(t * math.tau) * 3
        particle(img, mx, my, 16, accent, 82, 2.2)
        particle(img, mx + 8, my - 5, 14, "#08111D", 94, 2.2)


def _portal_rings(img: Image.Image, t: float, seed: int, source=(128, 136), swarm=False) -> None:
    idle = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, source, 110, "#7EF1FF", 44 + idle * 26, y_scale=0.76)
    radial_glow(img, (source[0], source[1] + 18), 70, "#B56CFF", 36, y_scale=0.46)
    for i, color in enumerate(("#7EF1FF", "#FFD96A", "#B56CFF")):
        phase = (t * (1.0 + i * 0.15) + i * 0.33) % 1.0
        start = math.degrees(phase * math.tau)
        soft_arc(img, source, 82 + i * 8, 50 + i * 5, start, start + 158, color, 68, 2.4, 2.5)
        soft_arc(img, source, 54 + i * 8, 32 + i * 4, start + 180, start + 270, color, 38, 1.5, 1.8)
    count = 18 if swarm else 9
    for i in range(count):
        phase = (t * 1.4 + i / count) % 1.0
        angle = phase * math.tau
        x = source[0] + math.cos(angle + i * 0.4) * (48 + 36 * math.sin(math.pi * phase))
        y = source[1] + math.sin(angle * 0.8 + i) * (26 + 22 * math.cos(math.pi * phase))
        particle(img, x, y, 1.4 + math.sin(math.pi * phase) * 1.8, "#FFD96A" if i % 3 == 0 else "#7EF1FF", 86, 0.8)


def _cinematic_mix(index: int, primary: str, seed: int, variant=0) -> Image.Image:
    t, idle, impact = _cinematic_t(index)
    img = blank()
    if primary == "air":
        _wind_vortex(img, t, seed, color="#F8FDFF", accent="#7EF1FF", intensity=1.0 + variant * 0.08)
    elif primary == "lightning":
        _source_core(img, (128, 150), "#7EF1FF", "#F8FDFF", idle, impact, radius=18)
        _lightning_storm(img, t, seed, source=(128, 150), colors=("#7EF1FF", "#B56CFF"), branches=4 + variant, reach=88 + variant * 8)
    elif primary == "gold_lightning":
        _source_core(img, (128, 142), "#FFD96A", "#F8FDFF", idle, impact, radius=17)
        _lightning_storm(img, t, seed, source=(128, 142), colors=("#FFD96A", "#7EF1FF"), branches=3 + variant, reach=82 + variant * 8)
    elif primary == "mist":
        _vapor_coil(img, t, seed, color="#B6FBFF", accent="#B56CFF")
    elif primary == "storm":
        _source_core(img, (128, 162), "#8C4DFF", "#F8FDFF", idle, impact, radius=20)
        _lightning_storm(img, t, seed, source=(128, 162), colors=("#B56CFF", "#7EF1FF"), branches=5, reach=92)
        drifting_wisps(img, t, ("#B56CFF", "#D8FDFF", "#2A2346"), seed=seed + 7, count=12, alpha=48, rise=76, spread=130)
    elif primary == "fire":
        _source_core(img, (128, 184), "#FF553D", "#FFF0C6", idle, impact, radius=19)
        _flame_column(img, t, seed, height=92 + variant * 16, width=86, intensity=1.0 + variant * 0.12)
    elif primary == "solar":
        _source_core(img, (128, 148), "#FFD96A", "#FFF9DC", idle, impact, radius=18)
        _flame_column(img, t, seed, source=(128, 182), colors=("#FFD96A", "#FFF0C6", "#FF8A3D"), height=78, width=78, intensity=0.82)
        spark_burst(img, (128, 128), t, ("#FFD96A", "#FFF9DC"), seed=seed + 2, count=14, alpha=90, radius=78)
    elif primary == "meteor":
        _source_core(img, (128, 178), "#FF553D", "#FFF0C6", idle, impact, radius=21)
        _flame_column(img, t, seed, height=112, width=92, intensity=1.12)
        _earth_impact(img, t, seed + 20, source=(128, 188), glow="#7A3D30", crack="#FFD96A", dust="#3B2430", intensity=0.56)
    elif primary == "water":
        _source_core(img, (128, 166), "#65E9FF", "#D8FDFF", idle, impact, radius=17)
        _water_surge(img, t, seed, color="#65E9FF", accent="#D8FDFF", intensity=1.0)
    elif primary == "prism_water":
        _source_core(img, (128, 156), "#FF67B5", "#64FFD0", idle, impact, radius=18)
        _water_surge(img, t, seed, color="#FF67B5", accent="#64FFD0", intensity=0.85)
        perimeter_sparks(img, t, ("#FF67B5", "#FFD96A", "#64FFD0", "#43EAFF"), seed=seed + 3, count=12, alpha=70)
    elif primary == "earth":
        _source_core(img, (128, 172), "#7A634A", "#FFD96A", idle, impact, radius=18)
        _earth_impact(img, t, seed, source=(128, 172), glow="#7A634A", crack="#FFD96A", dust="#4A3A33")
    elif primary == "magma":
        _earth_impact(img, t, seed, source=(128, 174), glow="#8A3A2A", crack="#FF553D", dust="#3B2430", intensity=1.0)
        _flame_column(img, t, seed + 5, source=(128, 190), height=68, width=76, intensity=0.78)
    elif primary == "growth":
        _source_core(img, (128, 186), "#64FFD0", "#FFD96A", idle, impact, radius=17)
        _growth_bloom(img, t, seed, flower=True)
    elif primary == "frost":
        _source_core(img, (128, 158), "#D8FDFF", "#7EF1FF", idle, impact, radius=17)
        _frost_shards(img, t, seed, intense=variant > 0)
    elif primary == "stone":
        _source_core(img, (128, 172), "#6B705C", "#64FFD0", idle, impact, radius=17)
        _earth_impact(img, t, seed, source=(128, 172), glow="#6B705C", crack="#64FFD0", dust="#4F5C52", intensity=0.94)
    elif primary == "steel":
        _source_core(img, (128, 158), "#AAB8C8", "#D8FDFF", idle, impact, radius=17)
        _frost_shards(img, t, seed, color="#CFE8FF", accent="#7EF1FF", intense=True)
    elif primary == "portal":
        _source_core(img, (128, 136), "#7EF1FF", "#FFD96A", idle, impact, radius=17)
        _portal_rings(img, t, seed, swarm=variant > 0)
    elif primary == "void":
        _source_core(img, (128, 144), "#8C4DFF", "#43EAFF", idle, impact, radius=18)
        _vapor_coil(img, t, seed, color="#8C4DFF", accent="#43EAFF", toxic=True)
    elif primary == "impact":
        _source_core(img, (128, 170), "#FFD96A", "#F8FDFF", idle, impact, radius=18)
        _earth_impact(img, t, seed, source=(128, 170), glow="#7D6548", crack="#FFD96A", dust="#4A3A33", intensity=1.05)
    elif primary == "explosion":
        _source_core(img, (128, 154), "#FFD96A", "#F8FDFF", idle, impact, radius=20)
        _flame_column(img, t, seed, source=(128, 186), height=82, width=92, intensity=0.92)
        spark_burst(img, (128, 128), t, ("#FFD96A", "#F8FDFF", "#FF8A3D"), seed=seed + 6, count=22, alpha=116, radius=92)
    elif primary == "spectrum":
        _source_core(img, (128, 144), "#7EF1FF", "#F8FDFF", idle, impact, radius=18)
        _water_surge(img, t, seed, color="#64FFD0", accent="#D8FDFF", intensity=0.48)
        _flame_column(img, t, seed + 1, source=(128, 190), colors=("#FF553D", "#FFD96A", "#FF67B5"), height=54, width=78, intensity=0.48)
        _earth_impact(img, t, seed + 2, source=(128, 178), glow="#6B5444", crack="#FFD96A", dust="#3F3630", intensity=0.36)
        _wind_vortex(img, t, seed + 3, color="#D8FDFF", accent="#7EF1FF", intensity=0.46)
        spark_burst(img, (128, 132), t, ("#FF67B5", "#FFD96A", "#64FFD0", "#43EAFF", "#B56CFF"), seed=seed + 4, count=18, alpha=84, radius=86)
    elif primary == "moon":
        _vapor_coil(img, t, seed, color="#B56CFF", accent="#D8FDFF", moon=True)
    elif primary == "neon_fumes":
        _vapor_coil(img, t, seed, color="#64FFD0", accent="#7EF1FF", toxic=True, moon=True)
    return img


def first_route_air(index: int) -> Image.Image:
    return _cinematic_mix(index, "air", seed=101)


def routing_spark_lightning(index: int) -> Image.Image:
    return _cinematic_mix(index, "gold_lightning", seed=111)


def lni_whisperer_mist(index: int) -> Image.Image:
    return _cinematic_mix(index, "mist", seed=121)


def brief_storm_lightning(index: int) -> Image.Image:
    return _cinematic_mix(index, "storm", seed=131)


def hundred_club_fire(index: int) -> Image.Image:
    return _cinematic_mix(index, "fire", seed=141)


def queue_slayer_earth(index: int) -> Image.Image:
    return _cinematic_mix(index, "earth", seed=151)


def final_reviewer_solar(index: int) -> Image.Image:
    return _cinematic_mix(index, "solar", seed=161)


def calendar_crusher_water(index: int) -> Image.Image:
    return _cinematic_mix(index, "water", seed=171)


def thousand_crown_meteor(index: int) -> Image.Image:
    return _cinematic_mix(index, "meteor", seed=181)


def docket_warlord_magma(index: int) -> Image.Image:
    return _cinematic_mix(index, "magma", seed=191)


def legendary_circuit_electric(index: int) -> Image.Image:
    return _cinematic_mix(index, "lightning", seed=201, variant=2)


def clean_sweep_growth(index: int) -> Image.Image:
    return _cinematic_mix(index, "growth", seed=211)


def precision_streak_frost(index: int) -> Image.Image:
    return _cinematic_mix(index, "frost", seed=221)


def archive_authority_stone(index: int) -> Image.Image:
    return _cinematic_mix(index, "stone", seed=231)


def audit_proof_steel(index: int) -> Image.Image:
    return _cinematic_mix(index, "steel", seed=241)


def immaculate_crystal(index: int) -> Image.Image:
    return _cinematic_mix(index, "frost", seed=251, variant=1)


def parallel_boss_air(index: int) -> Image.Image:
    return _cinematic_mix(index, "air", seed=261, variant=2)


def router_captain_beacon(index: int) -> Image.Image:
    return _cinematic_mix(index, "gold_lightning", seed=271, variant=1)


def router_admiral_network(index: int) -> Image.Image:
    return _cinematic_mix(index, "lightning", seed=281, variant=1)


def full_bench_six_orbit(index: int) -> Image.Image:
    return _cinematic_mix(index, "portal", seed=291, variant=1)


def six_router_void(index: int) -> Image.Image:
    return _cinematic_mix(index, "void", seed=301)


def no_misses_impact(index: int) -> Image.Image:
    return _cinematic_mix(index, "impact", seed=311)


def no_misses_elite_cracks(index: int) -> Image.Image:
    return _cinematic_mix(index, "stone", seed=321)


def no_misses_apex_explosion(index: int) -> Image.Image:
    return _cinematic_mix(index, "explosion", seed=331)


def docket_diva_prism_water(index: int) -> Image.Image:
    return _cinematic_mix(index, "prism_water", seed=341)


def court_hopper_portal(index: int) -> Image.Image:
    return _cinematic_mix(index, "portal", seed=351)


def jurisdiction_juggler_swarm(index: int) -> Image.Image:
    return _cinematic_mix(index, "portal", seed=361, variant=1)


def full_spectrum_elements(index: int) -> Image.Image:
    return _cinematic_mix(index, "spectrum", seed=371)


def night_shift_moon_vapor(index: int) -> Image.Image:
    return _cinematic_mix(index, "moon", seed=381)


def midnight_operator_neon_fumes(index: int) -> Image.Image:
    return _cinematic_mix(index, "neon_fumes", seed=391)


# Material-body VFX pass ---------------------------------------------------
# This overrides the cinematic recipes above with larger filled material shapes.
# The small-line helpers remain available only as accents; every badge starts
# from a readable element body such as flame, water, dust, wind, vapor, or ice.

def _material_band(points, thickness):
    upper = []
    lower = []
    for i, (x, y) in enumerate(points):
        if i == 0:
            nx, ny = points[min(i + 1, len(points) - 1)][0] - x, points[min(i + 1, len(points) - 1)][1] - y
        elif i == len(points) - 1:
            nx, ny = x - points[i - 1][0], y - points[i - 1][1]
        else:
            nx, ny = points[i + 1][0] - points[i - 1][0], points[i + 1][1] - points[i - 1][1]
        length = math.hypot(nx, ny) or 1.0
        px, py = -ny / length * thickness, nx / length * thickness
        upper.append((x + px, y + py))
        lower.append((x - px, y - py))
    return upper + lower[::-1]


def _paint_blob(base: Image.Image, x, y, rx, ry, color, alpha, blur=6.0) -> None:
    layer = blank()
    draw = ImageDraw.Draw(layer, "RGBA")
    draw.ellipse(
        (int((x - rx) * SCALE), int((y - ry) * SCALE), int((x + rx) * SCALE), int((y + ry) * SCALE)),
        fill=rgba(color, alpha),
    )
    composite(base, blur_layer(layer, blur))


def _paint_ribbon(base: Image.Image, points, thickness, color, alpha, blur=4.0) -> None:
    soft_polygon(base, _material_band(points, thickness), color, alpha, blur)


def _material_fire(index: int, seed: int, palette=("#C5161D", "#FF5A24", "#FFB23B", "#FFF1B0"), height=118, width=118, smoke=True) -> Image.Image:
    t = index / FRAME_COUNT
    rng = random.Random(seed)
    img = blank()
    pulse = 0.55 + 0.45 * math.sin(t * math.tau)
    radial_glow(img, (128, 176), 112, palette[1], 118 + pulse * 58, y_scale=0.48)
    radial_glow(img, (128, 138), 72, palette[2], 64 + pulse * 42, y_scale=0.42)
    for i in range(9):
        phase = (t * 1.35 + i * 0.13 + rng.random() * 0.07) % 1.0
        flicker = 0.55 + 0.45 * math.sin((phase * 2.5 + i) * math.tau)
        base_x = 128 + (i - 4) * width / 10 + math.sin(t * math.tau + i) * 8
        base_y = 214 - rng.uniform(0, 14)
        flame_h = height * (0.45 + flicker * 0.62)
        flame_w = width * (0.045 + flicker * 0.045)
        tip = (base_x + math.sin((t + i * 0.17) * math.tau) * 16, base_y - flame_h)
        outer = [
            (base_x - flame_w * 1.9, base_y),
            (base_x - flame_w * 1.1, base_y - flame_h * 0.42),
            tip,
            (base_x + flame_w * 1.1, base_y - flame_h * 0.44),
            (base_x + flame_w * 1.8, base_y),
            (base_x, base_y - flame_h * 0.18),
        ]
        soft_polygon(img, outer, palette[i % 3], 112, blur=4.2)
        if i % 2 == 0:
            inner = [
                (base_x - flame_w * 0.65, base_y - 4),
                (base_x, base_y - flame_h * 0.74),
                (base_x + flame_w * 0.65, base_y - 4),
                (base_x, base_y - flame_h * 0.20),
            ]
            soft_polygon(img, inner, palette[3], 72, blur=2.5)
    if smoke:
        drifting_wisps(img, t, ("#2C1B22", "#4A2528", palette[1]), seed=seed + 20, count=14, alpha=42, rise=102, spread=128)
    _embers(img, t, seed + 40, (palette[1], palette[2], palette[3]), count=34, alpha=128, rise=136)
    return img


def _material_water(index: int, seed: int, color="#54DFFF", deep="#226CD5", accent="#E1FDFF") -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 150), 116, color, 74 + pulse * 34, y_scale=0.62)
    radial_glow(img, (128, 188), 88, deep, 52, y_scale=0.34)
    for band in range(4):
        phase = (t + band * 0.20) % 1.0
        y = 112 + band * 18 + math.sin(phase * math.tau) * 12
        points = []
        for step in range(7):
            x = 28 + step * 34
            yy = y + math.sin(phase * math.tau + step * 0.85) * (12 + band * 2)
            points.append((x, yy))
        _paint_ribbon(img, points, 10 + band * 2, color if band % 2 else deep, 74 - band * 8, blur=4.2)
        _paint_ribbon(img, [(x, y - 3) for x, y in points], 2.5, accent, 54, blur=1.5)
    for i in range(12):
        phase = (t + i / 12) % 1.0
        fade = math.sin(math.pi * phase)
        x = 58 + (i * 17) % 140 + math.sin(phase * math.tau) * 6
        y = 64 + phase * 112
        _paint_blob(img, x, y, 3 + fade * 3, 5 + fade * 5, accent, 82 * fade, blur=1.5)
    return img


def _material_air(index: int, seed: int, storm=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 132), 118, "#8CEFFF", 52 + pulse * 26, y_scale=0.56)
    for band in range(5 if storm else 4):
        phase = (t * (1.0 + band * 0.08) + band * 0.19) % 1.0
        y = 72 + band * 31
        points = []
        for step in range(7):
            x = 24 + step * 36
            yy = y + math.sin(phase * math.tau + step * 0.72 + band) * (10 + band * 2)
            points.append((x, yy))
        _paint_ribbon(img, points, 8 if storm else 7, "#E8FDFF", 66 if storm else 54, blur=5.4)
        _paint_ribbon(img, [(x, y + 8) for x, y in points], 4, "#73DAFF", 42, blur=3.4)
    drifting_wisps(img, t, ("#E8FDFF", "#73DAFF", "#B56CFF"), seed=seed + 10, count=18 if storm else 14, alpha=52, rise=82, spread=158)
    return img


def _material_earth(index: int, seed: int, magma=False, stone=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    impact = smoothstep(0.0, 0.9, loop_pulse(t, 0.48, 0.17))
    glow = "#8A3A2A" if magma else ("#687160" if stone else "#7A5E42")
    crack = "#FF553D" if magma else ("#64FFD0" if stone else "#FFD96A")
    dust = "#352027" if magma else ("#4D584C" if stone else "#4D3C30")
    radial_glow(img, (128, 176), 118, glow, 84 + impact * 58, y_scale=0.42)
    dust_cloud(img, t, seed=seed, color=dust, count=22, alpha=76)
    for i in range(15):
        phase = (t + i / 15) % 1.0
        fade = math.sin(math.pi * phase)
        angle = -math.pi + i / 14 * math.pi
        x = 128 + math.cos(angle) * (28 + fade * 68)
        y = 178 + math.sin(angle) * (8 + fade * 30)
        shard(img, x, y, 5 + fade * 8, glow, 82 * fade, angle=angle + i * 0.4, blur=1.6)
    crack_lines(img, t, crack, seed=seed + 4, count=12, alpha=92 + impact * 54)
    if magma:
        composite(img, _material_fire(index, seed + 11, palette=("#8D171B", "#FF3A21", "#FF8A2A", "#FFF0B8"), height=72, width=92, smoke=False))
    return img


def _material_plasma(index: int, seed: int, palette=("#7EF1FF", "#B56CFF", "#F8FDFF"), gold=False, void=False) -> Image.Image:
    t = index / FRAME_COUNT
    rng = random.Random(seed)
    img = blank()
    pulse = 0.55 + 0.45 * math.sin(t * math.tau)
    core = "#FFD96A" if gold else ("#8C4DFF" if void else palette[0])
    radial_glow(img, (128, 138), 118, core, 76 + pulse * 54, y_scale=0.76)
    for i in range(10):
        phase = (t + i * 0.071 + rng.random() * 0.04) % 1.0
        angle = phase * math.tau
        radius = 22 + (i % 4) * 13 + math.sin(phase * math.tau) * 12
        x = 128 + math.cos(angle + i) * radius
        y = 138 + math.sin(angle * 0.82 + i) * radius * 0.62
        _paint_blob(img, x, y, 16 + pulse * 8, 10 + pulse * 5, palette[i % len(palette)], 58 + pulse * 24, blur=5.2)
    for i in range(5):
        flash = smoothstep(0.0, 0.9, loop_pulse(t, 0.18 + i * 0.15, 0.08))
        if flash:
            electric_branch(img, (128, 138), -math.pi / 2 + (i - 2) * 0.46, 72, palette[i % len(palette)], 94 * flash, seed=seed + index * 13 + i, segments=5, width=1.7)
    perimeter_sparks(img, t, palette, seed=seed + 14, count=16, alpha=86)
    return img


def _material_growth(index: int, seed: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 154), 116, "#50FFB0", 68 + pulse * 36, y_scale=0.72)
    for i in range(13):
        phase = (t * 1.2 + i / 13) % 1.0
        fade = math.sin(math.pi * phase)
        angle = -math.pi / 2 + (i - 6) * 0.16
        sx, sy = 128, 206
        length = 40 + fade * 78
        ex = sx + math.cos(angle) * length + math.sin(phase * math.tau + i) * 7
        ey = sy + math.sin(angle) * length
        _paint_ribbon(img, [(sx, sy), ((sx + ex) / 2, (sy + ey) / 2 + 10 * math.sin(phase * math.tau)), (ex, ey)], 3.6, "#46D97A", 72 * fade, blur=1.8)
        leaf_w = 7 + fade * 5
        leaf_h = 14 + fade * 9
        soft_polygon(img, [(ex, ey - leaf_h), (ex + leaf_w, ey), (ex, ey + leaf_h * 0.5), (ex - leaf_w, ey)], "#9EFFA8", 96 * fade, blur=2.0)
    _embers(img, t, seed + 22, ("#D8FFD0", "#FFD96A"), count=12, alpha=72, rise=92)
    return img


def _material_frost(index: int, seed: int, intense=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 146), 116, "#9DEEFF", 72 + pulse * 34, y_scale=0.76)
    drifting_wisps(img, t, ("#E1FDFF", "#8FE8FF", "#708CFF"), seed=seed, count=12, alpha=44, rise=72, spread=128)
    for i in range(12 if intense else 9):
        angle = -math.pi / 2 + (i - 5.5) * 0.18
        base = (128 + math.cos(angle) * 24, 168 + math.sin(angle) * 12)
        length = 52 + pulse * 18 + (i % 3) * 7
        tip = (base[0] + math.cos(angle) * length, base[1] + math.sin(angle) * length)
        side = 6 + (i % 3) * 2
        shard(img, tip[0], tip[1], side, "#D8FDFF", 96, angle=angle, blur=1.0)
        _paint_ribbon(img, [base, ((base[0] + tip[0]) / 2, (base[1] + tip[1]) / 2), tip], 2.8, "#D8FDFF", 76, blur=1.2)
    return img


def _material_portal(index: int, seed: int, swarm=False, spectrum=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    colors = ("#7EF1FF", "#B56CFF", "#FFD96A", "#64FFD0", "#FF67B5") if spectrum else ("#7EF1FF", "#B56CFF", "#FFD96A")
    radial_glow(img, (128, 136), 120, colors[0], 76, y_scale=0.78)
    for i, color in enumerate(colors[:4]):
        phase = (t * (1.0 + i * 0.12) + i * 0.25) % 1.0
        start = math.degrees(phase * math.tau)
        soft_arc(img, (128, 136), 74 + i * 9, 45 + i * 5, start, start + 210, color, 84, 4.2, 4.2)
        _paint_blob(img, 128 + math.cos(phase * math.tau) * (56 + i * 7), 136 + math.sin(phase * math.tau) * (34 + i * 4), 8, 6, color, 98, blur=2.0)
    count = 24 if swarm else 12
    for i in range(count):
        phase = (t * 1.5 + i / count) % 1.0
        x = 128 + math.cos(phase * math.tau + i) * (40 + 42 * math.sin(math.pi * phase))
        y = 136 + math.sin(phase * math.tau * 0.8 + i) * (24 + 26 * math.cos(math.pi * phase))
        _paint_blob(img, x, y, 2.4, 2.4, colors[i % len(colors)], 96, blur=0.9)
    return img


def _material_vapor(index: int, seed: int, color="#7EF1FF", accent="#B56CFF", moon=False, toxic=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    radial_glow(img, (128, 146), 120, color, 60, y_scale=0.72)
    drifting_wisps(img, t, (color, accent, "#173B35" if toxic else "#2A2346"), seed=seed, count=24 if toxic else 18, alpha=64, rise=104, spread=152)
    for i in range(7):
        phase = (t + i * 0.13) % 1.0
        x = 84 + i * 15 + math.sin(phase * math.tau) * 18
        y = 178 - phase * 100
        _paint_blob(img, x, y, 12 + math.sin(math.pi * phase) * 8, 8 + math.sin(math.pi * phase) * 5, color if i % 2 else accent, 52, blur=6.0)
    if moon:
        mx = 136 + math.sin(t * math.tau) * 5
        my = 70 + math.cos(t * math.tau) * 3
        _paint_blob(img, mx, my, 18, 18, accent, 104, blur=2.0)
        _paint_blob(img, mx + 8, my - 5, 15, 15, "#08111D", 120, blur=2.0)
    return img


def first_route_air(index: int) -> Image.Image:
    return _material_air(index, seed=101)


def routing_spark_lightning(index: int) -> Image.Image:
    return _material_plasma(index, seed=111, palette=("#FFD96A", "#7EF1FF", "#FFF7C8"), gold=True)


def lni_whisperer_mist(index: int) -> Image.Image:
    return _material_vapor(index, seed=121, color="#B6FBFF", accent="#B56CFF")


def brief_storm_lightning(index: int) -> Image.Image:
    return _material_plasma(index, seed=131, palette=("#B56CFF", "#7EF1FF", "#F8FDFF"))


def hundred_club_fire(index: int) -> Image.Image:
    return _material_fire(index, seed=141, height=118, width=118)


def queue_slayer_earth(index: int) -> Image.Image:
    return _material_earth(index, seed=151)


def final_reviewer_solar(index: int) -> Image.Image:
    return _material_fire(index, seed=161, palette=("#E37B22", "#FFD96A", "#FFF1B0", "#FFFFFF"), height=88, width=96, smoke=False)


def calendar_crusher_water(index: int) -> Image.Image:
    return _material_water(index, seed=171)


def thousand_crown_meteor(index: int) -> Image.Image:
    img = _material_fire(index, seed=181, height=128, width=128)
    composite(img, _material_earth(index, seed=182, magma=True))
    return img


def docket_warlord_magma(index: int) -> Image.Image:
    return _material_earth(index, seed=191, magma=True)


def legendary_circuit_electric(index: int) -> Image.Image:
    return _material_plasma(index, seed=201, palette=("#7EF1FF", "#B56CFF", "#F8FDFF"))


def clean_sweep_growth(index: int) -> Image.Image:
    return _material_growth(index, seed=211)


def precision_streak_frost(index: int) -> Image.Image:
    return _material_frost(index, seed=221)


def archive_authority_stone(index: int) -> Image.Image:
    return _material_earth(index, seed=231, stone=True)


def audit_proof_steel(index: int) -> Image.Image:
    return _material_frost(index, seed=241, intense=True)


def immaculate_crystal(index: int) -> Image.Image:
    return _material_frost(index, seed=251, intense=True)


def parallel_boss_air(index: int) -> Image.Image:
    return _material_air(index, seed=261, storm=True)


def router_captain_beacon(index: int) -> Image.Image:
    return _material_plasma(index, seed=271, palette=("#FFD96A", "#7EF1FF", "#F8FDFF"), gold=True)


def router_admiral_network(index: int) -> Image.Image:
    return _material_plasma(index, seed=281, palette=("#43EAFF", "#B56CFF", "#F8FDFF"))


def full_bench_six_orbit(index: int) -> Image.Image:
    return _material_portal(index, seed=291, swarm=True)


def six_router_void(index: int) -> Image.Image:
    return _material_plasma(index, seed=301, palette=("#8C4DFF", "#43EAFF", "#3B1D5E"), void=True)


def no_misses_impact(index: int) -> Image.Image:
    return _material_earth(index, seed=311)


def no_misses_elite_cracks(index: int) -> Image.Image:
    return _material_earth(index, seed=321, stone=True)


def no_misses_apex_explosion(index: int) -> Image.Image:
    return _material_fire(index, seed=331, height=136, width=136, smoke=False)


def docket_diva_prism_water(index: int) -> Image.Image:
    return _material_water(index, seed=341, color="#FF67B5", deep="#2456B8", accent="#64FFD0")


def court_hopper_portal(index: int) -> Image.Image:
    return _material_portal(index, seed=351)


def jurisdiction_juggler_swarm(index: int) -> Image.Image:
    return _material_portal(index, seed=361, swarm=True)


def full_spectrum_elements(index: int) -> Image.Image:
    img = _material_portal(index, seed=371, spectrum=True)
    composite(img, _material_fire(index, seed=372, height=64, width=92, smoke=False))
    composite(img, _material_water(index, seed=373, color="#64FFD0", accent="#E1FDFF"))
    return img


def night_shift_moon_vapor(index: int) -> Image.Image:
    return _material_vapor(index, seed=381, color="#B56CFF", accent="#D8FDFF", moon=True)


def midnight_operator_neon_fumes(index: int) -> Image.Image:
    return _material_vapor(index, seed=391, color="#64FFD0", accent="#7EF1FF", moon=True, toxic=True)


# Elemental material sprite pass -------------------------------------------
# This final pass intentionally replaces the earlier thin-stroke look. The
# readable layer for every badge is now a filled material body first: flame
# tongues, wave sheets, wind/fog ribbons, rock chunks, plasma clouds, ice
# crystals, or growth. Lines and particles are kept as small supporting accents.

def _mix_channel(a: int, b: int, amount: float) -> int:
    return max(0, min(255, int(a + (b - a) * amount)))


def _mix_hex(color_a: str, color_b: str, amount: float) -> str:
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    mixed = (
        _mix_channel(int(a[0:2], 16), int(b[0:2], 16), amount),
        _mix_channel(int(a[2:4], 16), int(b[2:4], 16), amount),
        _mix_channel(int(a[4:6], 16), int(b[4:6], 16), amount),
    )
    return f"#{mixed[0]:02X}{mixed[1]:02X}{mixed[2]:02X}"


def _organic_points(cx: float, cy: float, rx: float, ry: float, seed: int, t: float, count: int = 18, wobble: float = 0.18):
    rng = random.Random(seed)
    points = []
    for i in range(count):
        angle = i / count * math.tau
        noise = (
            math.sin(angle * 2.0 + t * math.tau + rng.random() * 0.5) * wobble
            + math.sin(angle * 5.0 - t * math.tau * 1.7 + rng.random()) * wobble * 0.46
        )
        stretch = 1.0 + noise + rng.uniform(-wobble * 0.35, wobble * 0.35)
        points.append((cx + math.cos(angle) * rx * stretch, cy + math.sin(angle) * ry * stretch))
    return points


def _paint_organic_blob(base: Image.Image, cx: float, cy: float, rx: float, ry: float, color: str, alpha: float, seed: int, t: float, blur: float = 5.0, count: int = 20) -> None:
    soft_polygon(base, _organic_points(cx, cy, rx, ry, seed, t, count=count), color, alpha, blur=blur)


def _paint_flame_tongue(base: Image.Image, cx: float, base_y: float, width: float, height: float, lean: float, color: str, alpha: float, seed: int, t: float, blur: float = 3.8) -> None:
    rng = random.Random(seed)
    left = []
    right = []
    for step in range(8):
        f = step / 7
        y = base_y - height * f
        taper = math.sin((1.0 - f) * math.pi * 0.5) ** 0.62
        body = width * taper * (0.64 + 0.20 * math.sin(f * math.tau + t * math.tau + seed))
        center = cx + lean * f + math.sin(t * math.tau * 1.7 + seed + f * 3.0) * (4 + 7 * f)
        left.append((center - body * rng.uniform(0.72, 1.08), y + rng.uniform(-2, 2)))
        right.append((center + body * rng.uniform(0.60, 0.96), y + rng.uniform(-2, 2)))
    points = left + right[::-1]
    soft_polygon(base, points, color, alpha, blur=blur)


def _paint_wave_sheet(base: Image.Image, y: float, thickness: float, amplitude: float, color: str, alpha: float, t: float, seed: int, blur: float = 3.2, highlight: str = "#E1FDFF") -> None:
    rng = random.Random(seed)
    upper = []
    lower = []
    phase = t * math.tau * (0.75 + rng.random() * 0.35) + rng.random() * math.tau
    for step in range(14):
        p = step / 13
        x = 18 + p * 220
        wave = math.sin(p * math.tau * 1.45 + phase) * amplitude
        chop = math.sin(p * math.tau * 4.5 - phase * 0.7) * amplitude * 0.24
        yy = y + wave + chop
        upper.append((x, yy))
        lower.append((x, yy + thickness + math.sin(p * math.tau * 1.9 + phase + 1.2) * amplitude * 0.34))
    soft_polygon(base, upper + lower[::-1], color, alpha, blur=blur)
    soft_line(base, upper, highlight, alpha * 0.58, 1.8, 1.3)


def _paint_vapor_body(base: Image.Image, t: float, colors, seed: int, count: int, alpha: float, rise: float, spread: float, base_y: float = 184) -> None:
    rng = random.Random(seed)
    for i in range(count):
        phase = (t * 0.82 + i / count + rng.random() * 0.18) % 1.0
        fade = math.sin(math.pi * phase)
        x = 128 + (rng.random() - 0.5) * spread + math.sin(phase * math.tau * 1.4 + i) * 22
        y = base_y - phase * rise + math.cos(phase * math.tau + i) * 5
        rx = rng.uniform(12, 30) * (0.62 + fade * 0.62)
        ry = rng.uniform(8, 22) * (0.62 + fade * 0.45)
        _paint_organic_blob(base, x, y, rx, ry, colors[i % len(colors)], alpha * fade, seed + i * 17, t + phase, blur=rng.uniform(6, 10), count=16)


def _paint_rock_chunk(base: Image.Image, x: float, y: float, sx: float, sy: float, face: str, edge: str, seed: int, t: float, alpha: float = 108) -> None:
    points = _organic_points(x, y, sx, sy, seed, t, count=7, wobble=0.28)
    soft_polygon(base, points, face, alpha, blur=1.5)
    top = sorted(points, key=lambda p: p[1])[:3]
    if len(top) >= 2:
        top = sorted(top, key=lambda p: p[0])
        soft_line(base, top, edge, alpha * 0.58, 1.2, 0.9)
    core = _mix_hex(face, edge, 0.32)
    _paint_organic_blob(base, x + sx * 0.06, y - sy * 0.08, sx * 0.44, sy * 0.34, core, alpha * 0.38, seed + 99, t, blur=2.0, count=7)


def _paint_leaf(base: Image.Image, x: float, y: float, width: float, height: float, angle: float, color: str, alpha: float) -> None:
    tip = (x + math.cos(angle) * height, y + math.sin(angle) * height)
    side = angle + math.pi / 2
    points = [
        (x, y),
        (x + math.cos(side) * width, y + math.sin(side) * width),
        tip,
        (x - math.cos(side) * width, y - math.sin(side) * width),
    ]
    soft_polygon(base, points, color, alpha, blur=1.5)


def _paint_plasma_body(base: Image.Image, t: float, seed: int, colors, void: bool = False, gold: bool = False) -> None:
    rng = random.Random(seed)
    core = colors[0]
    if gold:
        core = "#FFD96A"
    if void:
        core = "#8C4DFF"
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(base, (128, 136), 122, core, 106 + pulse * 66, y_scale=0.78)
    _paint_organic_blob(base, 128, 136, 48 + pulse * 8, 36 + pulse * 6, core, 116, seed, t, blur=8.5, count=24)
    _paint_organic_blob(base, 128, 136, 25 + pulse * 5, 18 + pulse * 4, colors[-1], 102, seed + 4, t, blur=3.8, count=18)
    for i in range(9):
        phase = (t * 0.92 + i / 9 + rng.random() * 0.08) % 1.0
        angle = phase * math.tau + i * 0.42
        length = 54 + math.sin(math.pi * phase) * 34
        points = [
            (128, 136),
            (
                128 + math.cos(angle) * length * 0.46 + math.sin(phase * math.tau) * 12,
                136 + math.sin(angle) * length * 0.30 + math.cos(phase * math.tau) * 9,
            ),
            (128 + math.cos(angle) * length, 136 + math.sin(angle) * length * 0.62),
        ]
        _paint_ribbon(base, points, 5.0 + pulse * 2.2, colors[i % len(colors)], 62 * math.sin(math.pi * phase), blur=4.5)
    for i in range(4):
        hit = smoothstep(0.0, 0.85, loop_pulse(t, 0.14 + i * 0.22, 0.09))
        if hit:
            electric_branch(base, (128, 136), -math.pi / 2 + (i - 1.5) * 0.74, 76, colors[i % len(colors)], 104 * hit, seed=seed + i * 70 + int(t * FRAME_COUNT), segments=6, width=1.8)


def _material_fire(index: int, seed: int, palette=("#C5161D", "#FF5A24", "#FFB23B", "#FFF1B0"), height=118, width=118, smoke=True) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.55 + 0.45 * math.sin(t * math.tau * 1.2)
    radial_glow(img, (128, 180), 120, palette[1], 128 + pulse * 76, y_scale=0.48)
    radial_glow(img, (128, 150), 80, palette[2], 72 + pulse * 52, y_scale=0.48)

    for i in range(10):
        phase = (t * 1.38 + i * 0.093) % 1.0
        local_height = height * (0.62 + 0.34 * math.sin(phase * math.tau + i))
        local_width = width * (0.09 + 0.035 * math.sin(phase * math.tau * 1.6 + i))
        cx = 128 + (i - 4.5) * width / 12 + math.sin(t * math.tau * 1.5 + i) * 10
        color = palette[min(2, i % 3)]
        _paint_flame_tongue(img, cx, 214 - (i % 3) * 5, local_width, local_height, math.sin(i + t * math.tau) * 24, color, 124, seed + i * 19, phase, blur=4.2)

    for i in range(5):
        phase = (t * 1.7 + i * 0.17) % 1.0
        cx = 128 + (i - 2) * width / 12 + math.sin(phase * math.tau) * 8
        _paint_flame_tongue(img, cx, 205 - i * 3, width * 0.045, height * 0.62, math.sin(i) * 14, palette[3], 74, seed + 200 + i, phase, blur=2.6)

    if smoke:
        _paint_vapor_body(img, t, ("#251820", "#482327", "#7A2E27"), seed + 40, count=12, alpha=42, rise=116, spread=126, base_y=188)
    _embers(img, t, seed + 80, (palette[1], palette[2], palette[3]), count=30, alpha=118, rise=142)
    return img


def _material_water(index: int, seed: int, color="#54DFFF", deep="#226CD5", accent="#E1FDFF") -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 154), 122, color, 84 + pulse * 40, y_scale=0.60)
    radial_glow(img, (128, 190), 90, deep, 70, y_scale=0.34)
    for band in range(4):
        _paint_wave_sheet(
            img,
            y=94 + band * 26 + math.sin(t * math.tau + band) * 3,
            thickness=22 + band * 2,
            amplitude=11 + band * 2,
            color=_mix_hex(color, deep, band * 0.18),
            alpha=88 - band * 7,
            t=t + band * 0.08,
            seed=seed + band * 23,
            blur=3.4,
            highlight=accent,
        )
    for i in range(9):
        phase = (t * 0.86 + i / 9) % 1.0
        fade = math.sin(math.pi * phase)
        x = 56 + i * 18 + math.sin(phase * math.tau + i) * 9
        y = 72 + phase * 116
        _paint_organic_blob(img, x, y, 4 + fade * 5, 8 + fade * 8, accent, 82 * fade, seed + i * 31, phase, blur=1.4, count=10)
    water_ripples(img, t, accent, count=3, alpha=36)
    return img


def _material_air(index: int, seed: int, storm=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 136), 124, "#93F4FF", 58 + pulse * 30, y_scale=0.58)
    colors = ("#E8FDFF", "#9AEFFF", "#B56CFF") if storm else ("#E8FDFF", "#9AEFFF", "#D8FDFF")
    for band in range(5 if storm else 4):
        phase = (t * (0.55 + band * 0.08) + band * 0.18) % 1.0
        y = 76 + band * 32
        points = []
        for step in range(8):
            p = step / 7
            x = 20 + p * 216
            yy = y + math.sin(p * math.tau * 1.25 + phase * math.tau) * (12 + band * 1.8)
            points.append((x, yy))
        _paint_ribbon(img, points, 10 + band * 1.5, colors[band % len(colors)], 54 + (18 if storm else 0), blur=7.8)
    _paint_vapor_body(img, t, colors, seed + 90, count=18 if storm else 13, alpha=38, rise=76, spread=176, base_y=176)
    if storm:
        for i in range(3):
            hit = smoothstep(0.0, 0.9, loop_pulse(t, 0.22 + i * 0.23, 0.10))
            if hit:
                electric_branch(img, (92 + i * 34, 120), -math.pi / 2 + i * 0.22, 58, "#E8FDFF", 70 * hit, seed=seed + i * 50 + index, segments=5, width=1.2)
    return img


def _material_earth(index: int, seed: int, magma=False, stone=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    impact = smoothstep(0.0, 0.9, loop_pulse(t, 0.48, 0.18))
    face = "#4A3A2F"
    edge = "#FFD96A"
    dust = "#5C4738"
    glow = "#9A6A3E"
    if magma:
        face, edge, dust, glow = "#3E2024", "#FF623A", "#412027", "#C22C24"
    elif stone:
        face, edge, dust, glow = "#4A514B", "#88FFE2", "#47524A", "#66726A"
    radial_glow(img, (128, 182), 122, glow, 78 + impact * 64, y_scale=0.44)
    _paint_vapor_body(img, t, (dust, _mix_hex(dust, edge, 0.18), "#2B2320"), seed + 20, count=18, alpha=54, rise=50, spread=162, base_y=194)
    for i in range(11):
        phase = (t * 0.72 + i / 11) % 1.0
        spread = 30 + math.sin(math.pi * phase) * 64
        x = 128 + (i - 5) * 15 + math.sin(phase * math.tau + i) * 12
        y = 178 + math.cos(i) * 8 - impact * 12
        _paint_rock_chunk(img, x + math.sin(i) * spread * 0.18, y, 7 + (i % 3) * 3, 9 + (i % 4) * 3, face, edge, seed + i * 41, phase, alpha=118)
    crack_lines(img, t, edge, seed=seed + 7, count=10, alpha=76 + impact * 62)
    if magma:
        composite(img, _material_fire(index, seed + 200, palette=("#8D171B", "#FF3A21", "#FF8A2A", "#FFF0B8"), height=68, width=88, smoke=False))
    return img


def _material_plasma(index: int, seed: int, palette=("#7EF1FF", "#B56CFF", "#F8FDFF"), gold=False, void=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    colors = tuple(palette)
    if gold:
        colors = ("#FFD96A", "#FFB23B", "#F8FDFF")
    elif void:
        colors = ("#8C4DFF", "#43EAFF", "#1F103B", "#F8FDFF")
    _paint_plasma_body(img, t, seed, colors, void=void, gold=gold)
    perimeter_sparks(img, t, colors, seed=seed + 17, count=10, alpha=58)
    return img


def _material_growth(index: int, seed: int) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 156), 122, "#50FFB0", 72 + pulse * 42, y_scale=0.70)
    _paint_vapor_body(img, t, ("#153E2A", "#46D97A", "#B9FFBE"), seed + 14, count=10, alpha=34, rise=82, spread=118, base_y=192)
    for i in range(12):
        phase = (t * 0.9 + i / 12) % 1.0
        fade = math.sin(math.pi * phase)
        angle = -math.pi / 2 + (i - 5.5) * 0.15 + math.sin(phase * math.tau) * 0.08
        sx, sy = 128 + math.sin(i) * 7, 204
        length = 36 + fade * 82
        mid = (sx + math.cos(angle) * length * 0.45, sy + math.sin(angle) * length * 0.52 + 8 * math.sin(phase * math.tau))
        tip = (sx + math.cos(angle) * length, sy + math.sin(angle) * length)
        _paint_ribbon(img, [(sx, sy), mid, tip], 3.2 + fade * 2.0, "#46D97A", 74 * fade, blur=2.0)
        if fade > 0.28:
            _paint_leaf(img, tip[0], tip[1], 7 + fade * 5, 16 + fade * 8, angle + (0.9 if i % 2 else -0.9), "#A8FF9A", 98 * fade)
    return img


def _material_frost(index: int, seed: int, intense=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    pulse = 0.5 + 0.5 * math.sin(t * math.tau)
    radial_glow(img, (128, 146), 122, "#9DEEFF", 84 + pulse * 44, y_scale=0.78)
    _paint_vapor_body(img, t, ("#D8FDFF", "#9DEEFF", "#708CFF"), seed + 10, count=13 if intense else 9, alpha=40, rise=72, spread=138, base_y=178)
    shard_count = 13 if intense else 9
    for i in range(shard_count):
        phase = (t * 0.64 + i / shard_count) % 1.0
        fade = 0.58 + 0.42 * math.sin(math.pi * phase)
        angle = -math.pi / 2 + (i - shard_count / 2) * 0.15
        length = 46 + fade * (28 if intense else 18) + (i % 3) * 7
        base_x = 128 + math.cos(angle) * 20
        base_y = 168 + math.sin(angle) * 12
        tip = (base_x + math.cos(angle) * length, base_y + math.sin(angle) * length)
        side = angle + math.pi / 2
        points = [
            (base_x - math.cos(side) * 5, base_y - math.sin(side) * 5),
            tip,
            (base_x + math.cos(side) * 5, base_y + math.sin(side) * 5),
            (base_x + math.cos(angle) * 12, base_y + math.sin(angle) * 12),
        ]
        soft_polygon(img, points, "#D8FDFF", 74 + fade * 42, blur=1.2)
        soft_line(img, [points[0], tip, points[2]], "#F8FDFF", 60 + fade * 42, 1.0, 0.8)
    return img


def _material_portal(index: int, seed: int, swarm=False, spectrum=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    colors = ("#7EF1FF", "#B56CFF", "#FFD96A", "#64FFD0", "#FF67B5") if spectrum else ("#7EF1FF", "#B56CFF", "#FFD96A")
    radial_glow(img, (128, 136), 124, colors[0], 94, y_scale=0.82)
    for band, color in enumerate(colors[:4]):
        phase = (t * (0.55 + band * 0.08) + band * 0.22) % 1.0
        points = []
        for step in range(18):
            p = step / 17
            angle = p * math.tau * 0.78 + phase * math.tau
            radius_x = 58 + band * 7 + math.sin(p * math.tau * 3 + phase) * 6
            radius_y = 34 + band * 5 + math.cos(p * math.tau * 2 - phase) * 5
            points.append((128 + math.cos(angle) * radius_x, 136 + math.sin(angle) * radius_y))
        _paint_ribbon(img, points, 6.5 + band * 1.6, color, 74 - band * 6, blur=5.0)
    if swarm:
        _paint_vapor_body(img, t, colors, seed + 44, count=16, alpha=42, rise=82, spread=142, base_y=176)
    else:
        _paint_plasma_body(img, t, seed + 50, colors, void=False, gold=False)
    return img


def _material_vapor(index: int, seed: int, color="#7EF1FF", accent="#B56CFF", moon=False, toxic=False) -> Image.Image:
    t = index / FRAME_COUNT
    img = blank()
    palette = (color, accent, "#143E35" if toxic else "#262247", "#D8FDFF")
    radial_glow(img, (128, 150), 126, color, 66, y_scale=0.70)
    _paint_vapor_body(img, t, palette, seed, count=25 if toxic else 20, alpha=58, rise=112, spread=162, base_y=190)
    for i in range(4):
        phase = (t * 0.68 + i * 0.2) % 1.0
        points = []
        for step in range(7):
            p = step / 6
            x = 52 + p * 152 + math.sin(phase * math.tau + step) * 14
            y = 98 + i * 22 + math.cos(p * math.tau + phase * math.tau) * 18
            points.append((x, y))
        _paint_ribbon(img, points, 9 + i * 1.4, palette[i % len(palette)], 42, blur=7.0)
    if moon:
        mx = 136 + math.sin(t * math.tau) * 5
        my = 70 + math.cos(t * math.tau) * 3
        _paint_organic_blob(img, mx, my, 20, 20, accent, 118, seed + 333, t, blur=2.0, count=20)
        _paint_organic_blob(img, mx + 8, my - 5, 16, 16, "#08111D", 132, seed + 334, t, blur=1.8, count=18)
    return img


# Texture-atlas sprite pass ------------------------------------------------
# This is the active badge VFX backend. It replaces the direct shape recipes
# above with transparent material sprites generated in assets/images/vfx_materials
# and then composited per badge into assets/images/badge_vfx.

def _sprite_render(effect_key: str):
    def render(index: int) -> Image.Image:
        return render_badge_effect(effect_key, index, frame_count=FRAME_COUNT, size=SIZE)

    render.__name__ = effect_key
    return render


first_route_air = _sprite_render("first_route_air")
routing_spark_lightning = _sprite_render("routing_spark_lightning")
lni_whisperer_mist = _sprite_render("lni_whisperer_mist")
brief_storm_lightning = _sprite_render("brief_storm_lightning")
hundred_club_fire = _sprite_render("hundred_club_fire")
queue_slayer_earth = _sprite_render("queue_slayer_earth")
final_reviewer_solar = _sprite_render("final_reviewer_solar")
calendar_crusher_water = _sprite_render("calendar_crusher_water")
thousand_crown_meteor = _sprite_render("thousand_crown_meteor")
docket_warlord_magma = _sprite_render("docket_warlord_magma")
legendary_circuit_electric = _sprite_render("legendary_circuit_electric")
clean_sweep_growth = _sprite_render("clean_sweep_growth")
precision_streak_frost = _sprite_render("precision_streak_frost")
archive_authority_stone = _sprite_render("archive_authority_stone")
audit_proof_steel = _sprite_render("audit_proof_steel")
immaculate_crystal = _sprite_render("immaculate_crystal")
parallel_boss_air = _sprite_render("parallel_boss_air")
router_captain_beacon = _sprite_render("router_captain_beacon")
router_admiral_network = _sprite_render("router_admiral_network")
full_bench_six_orbit = _sprite_render("full_bench_six_orbit")
six_router_void = _sprite_render("six_router_void")
no_misses_impact = _sprite_render("no_misses_impact")
no_misses_elite_cracks = _sprite_render("no_misses_elite_cracks")
no_misses_apex_explosion = _sprite_render("no_misses_apex_explosion")
docket_diva_prism_water = _sprite_render("docket_diva_prism_water")
court_hopper_portal = _sprite_render("court_hopper_portal")
jurisdiction_juggler_swarm = _sprite_render("jurisdiction_juggler_swarm")
full_spectrum_elements = _sprite_render("full_spectrum_elements")
night_shift_moon_vapor = _sprite_render("night_shift_moon_vapor")
midnight_operator_neon_fumes = _sprite_render("midnight_operator_neon_fumes")


GENERATORS = {
    "first_route_air": first_route_air,
    "routing_spark_lightning": routing_spark_lightning,
    "lni_whisperer_mist": lni_whisperer_mist,
    "brief_storm_lightning": brief_storm_lightning,
    "hundred_club_fire": hundred_club_fire,
    "queue_slayer_earth": queue_slayer_earth,
    "final_reviewer_solar": final_reviewer_solar,
    "calendar_crusher_water": calendar_crusher_water,
    "thousand_crown_meteor": thousand_crown_meteor,
    "docket_warlord_magma": docket_warlord_magma,
    "legendary_circuit_electric": legendary_circuit_electric,
    "clean_sweep_growth": clean_sweep_growth,
    "precision_streak_frost": precision_streak_frost,
    "archive_authority_stone": archive_authority_stone,
    "audit_proof_steel": audit_proof_steel,
    "immaculate_crystal": immaculate_crystal,
    "parallel_boss_air": parallel_boss_air,
    "router_captain_beacon": router_captain_beacon,
    "router_admiral_network": router_admiral_network,
    "full_bench_six_orbit": full_bench_six_orbit,
    "six_router_void": six_router_void,
    "no_misses_impact": no_misses_impact,
    "no_misses_elite_cracks": no_misses_elite_cracks,
    "no_misses_apex_explosion": no_misses_apex_explosion,
    "docket_diva_prism_water": docket_diva_prism_water,
    "court_hopper_portal": court_hopper_portal,
    "jurisdiction_juggler_swarm": jurisdiction_juggler_swarm,
    "full_spectrum_elements": full_spectrum_elements,
    "night_shift_moon_vapor": night_shift_moon_vapor,
    "midnight_operator_neon_fumes": midnight_operator_neon_fumes,
}


def main() -> None:
    ensure_material_sprites(force=True)
    cleanup_output()
    for effect, generator in GENERATORS.items():
        for index in range(FRAME_COUNT):
            save_frame(effect, index, generator(index))
    print(f"Generated {len(GENERATORS) * FRAME_COUNT} badge VFX frames in {OUT_DIR}")


if __name__ == "__main__":
    main()
