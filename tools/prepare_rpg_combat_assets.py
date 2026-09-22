"""Normalize generated RPG atlases into isolated runtime frames.

Image generators do not guarantee mathematically even sprite cells. Runtime code
therefore consumes these trimmed standalone images, never neighboring atlas pixels.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
RPG_DIR = ROOT / "assets" / "rpg"
SOURCE_DIR = RPG_DIR / "combat_source"
OUTPUT_DIR = RPG_DIR / "combat"

ARCHIVIST_FRAMES = (
    ("ready", 0, 335),
    ("q_slash", 335, 735),
    ("w_ward", 735, 1048),
    ("e_mark", 1048, 1410),
    ("r_redline", 1410, 1835),
    ("hit", 1835, 2172),
)

PENDING_FRAMES = (
    ("idle_a", 25, 205),
    ("idle_b", 234, 498),
    ("windup", 519, 745),
    ("release", 775, 1077),
    ("vortex", 1102, 1383),
    ("hit", 1450, 1640),
    ("stagger", 1743, 1878),
    ("defeat", 1974, 2136),
)

ICON_NAMES = ("q_slash", "w_ward", "e_mark", "r_redline", "appeal_tonic", "archive_compass")
TRIAL_ITEM_NAMES = ("recall_lens", "appeal_tonic", "reset_compass", "memory_shard", "mercy_sigil", "docket_shard")
TRIAL_EDGE_CLEANUP = {
    ("red_tape", "hit"): {"left": 82},
    ("misfiled_mimic", "idle_b"): {"top": 30},
    ("misfiled_mimic", "attack"): {"top": 22},
    ("misfiled_mimic", "hit"): {"left": 62, "top": 28},
}
ARCHIVIST_GRID_NAMES = ("ready", "q_slash", "w_ward", "e_mark", "r_redline", "hit")
PENDING_GRID_NAMES = ("idle_a", "idle_b", "windup", "release", "vortex", "hit", "stagger", "defeat")
ISOLATED_OVERRIDES = {
    "archivist": ("q_slash", "e_mark", "r_redline"),
    "pending": ("windup", "release"),
}
ARCHIVIST_EDGE_CLEANUP = {
    "ready": (None, 437),
    "w_ward": (53, None),
    "r_redline": (28, None),
    "hit": (161, None),
}


def _trim_alpha(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("Generated frame has no visible pixels")
    return image.crop(bounds)


def _clear_cell_edges(image: Image.Image, cleanup: dict[str, int]) -> None:
    """Remove fragments leaked in from neighboring generated sprite cells."""
    draw = ImageDraw.Draw(image)
    width, height = image.size
    if "left" in cleanup:
        draw.rectangle((0, 0, cleanup["left"], height), fill=(0, 0, 0, 0))
    if "right" in cleanup:
        draw.rectangle((cleanup["right"], 0, width, height), fill=(0, 0, 0, 0))
    if "top" in cleanup:
        draw.rectangle((0, 0, width, cleanup["top"]), fill=(0, 0, 0, 0))
    if "bottom" in cleanup:
        draw.rectangle((0, cleanup["bottom"], width, height), fill=(0, 0, 0, 0))


def _retain_largest_alpha_component(image: Image.Image) -> None:
    """Keep one complete silhouette when a generated grid leaks a detached neighbor."""
    alpha = image.getchannel("A")
    pixels = alpha.load()
    width, height = image.size
    visited: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] <= 12 or (x, y) in visited:
                continue
            component: list[tuple[int, int]] = []
            queue = deque(((x, y),))
            visited.add((x, y))
            while queue:
                current_x, current_y = queue.popleft()
                component.append((current_x, current_y))
                for next_x, next_y in (
                    (current_x - 1, current_y), (current_x + 1, current_y),
                    (current_x, current_y - 1), (current_x, current_y + 1),
                    (current_x - 1, current_y - 1), (current_x + 1, current_y - 1),
                    (current_x - 1, current_y + 1), (current_x + 1, current_y + 1),
                ):
                    point = (next_x, next_y)
                    if 0 <= next_x < width and 0 <= next_y < height and point not in visited and pixels[point] > 12:
                        visited.add(point)
                        queue.append(point)
            components.append(component)
    if not components:
        return
    keep = set(max(components, key=len))
    for component in components:
        if component and component[0] not in keep:
            for point in component:
                pixels[point] = 0
    image.putalpha(alpha)


def extract_pose_atlas(source_name: str, frame_specs, output_name: str) -> None:
    source = Image.open(SOURCE_DIR / source_name).convert("RGBA")
    frames = []
    for name, left, right in frame_specs:
        frame = _trim_alpha(source.crop((left, 0, right, source.height)))
        frames.append((name, frame))

    canvas_width = max(frame.width for _, frame in frames) + 64
    canvas_height = max(frame.height for _, frame in frames) + 40
    destination = OUTPUT_DIR / output_name
    destination.mkdir(parents=True, exist_ok=True)
    for name, frame in frames:
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        x = (canvas_width - frame.width) // 2
        y = canvas_height - frame.height - 20
        canvas.alpha_composite(frame, (x, y))
        canvas.save(destination / f"{name}.png", optimize=True)


def extract_icon_atlas() -> None:
    source = Image.open(RPG_DIR / "ability_item_icons.png").convert("RGBA")
    destination = OUTPUT_DIR / "icons"
    destination.mkdir(parents=True, exist_ok=True)
    cell_width = source.width // 3
    cell_height = source.height // 2
    for index, name in enumerate(ICON_NAMES):
        column = index % 3
        row = index // 3
        frame = source.crop((
            column * cell_width,
            row * cell_height,
            (column + 1) * cell_width,
            (row + 1) * cell_height,
        ))
        frame.save(destination / f"{name}.png", optimize=True)


def extract_trial_assets() -> None:
    enemy_source = Image.open(SOURCE_DIR / "trial_enemies_grid.png").convert("RGBA")
    enemy_specs = (
        ("red_tape", "idle_a", 0, 0),
        ("red_tape", "idle_b", 1, 0),
        ("red_tape", "attack", 2, 0),
        ("red_tape", "hit", 3, 0),
        ("misfiled_mimic", "idle_a", 0, 1),
        ("misfiled_mimic", "idle_b", 1, 1),
        ("misfiled_mimic", "attack", 2, 1),
        ("misfiled_mimic", "hit", 3, 1),
    )
    cell_width = enemy_source.width // 4
    cell_height = enemy_source.height // 2
    for group, name, column, row in enemy_specs:
        frame = enemy_source.crop((
            column * cell_width, row * cell_height,
            (column + 1) * cell_width, (row + 1) * cell_height,
        ))
        cleanup = TRIAL_EDGE_CLEANUP.get((group, name))
        if cleanup:
            _clear_cell_edges(frame, cleanup)
        if (group, name) == ("red_tape", "idle_b"):
            _retain_largest_alpha_component(frame)
        alpha = frame.getchannel("A").point(lambda value: 0 if value <= 12 else value)
        frame.putalpha(alpha)
        frame = _trim_alpha(frame)
        frame.thumbnail((464, 464), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        canvas.alpha_composite(frame, ((512 - frame.width) // 2, (512 - frame.height) // 2))
        destination = OUTPUT_DIR / group
        destination.mkdir(parents=True, exist_ok=True)
        canvas.save(destination / f"{name}.png", optimize=True)

    item_source = Image.open(SOURCE_DIR / "trial_items_grid.png").convert("RGBA")
    item_destination = RPG_DIR / "quest" / "icons"
    item_destination.mkdir(parents=True, exist_ok=True)
    cell_width = item_source.width // 3
    cell_height = item_source.height // 2
    for index, name in enumerate(TRIAL_ITEM_NAMES):
        column = index % 3
        row = index // 3
        frame = item_source.crop((
            column * cell_width, row * cell_height,
            (column + 1) * cell_width, (row + 1) * cell_height,
        ))
        frame.save(item_destination / f"{name}.png", optimize=True)


def extract_pose_grid(source_name: str, names, columns: int, output_name: str, cleanup=None) -> None:
    """Export fixed grid cells; wide gutters keep generated poses independent."""
    source = Image.open(SOURCE_DIR / source_name).convert("RGBA")
    rows = (len(names) + columns - 1) // columns
    cell_width = source.width // columns
    cell_height = source.height // rows
    frames = []
    for index, name in enumerate(names):
        column = index % columns
        row = index // columns
        frame = source.crop((
            column * cell_width,
            row * cell_height,
            (column + 1) * cell_width,
            (row + 1) * cell_height,
        ))
        if cleanup and name in cleanup:
            keep_left, keep_right = cleanup[name]
            pixels = frame.load()
            for x in range(frame.width):
                if (keep_left is not None and x < keep_left) or (keep_right is not None and x >= keep_right):
                    for y in range(frame.height):
                        pixels[x, y] = (0, 0, 0, 0)
        frames.append((name, _trim_alpha(frame)))

    canvas_width = max(frame.width for _, frame in frames) + 40
    canvas_height = max(frame.height for _, frame in frames) + 40
    destination = OUTPUT_DIR / output_name
    destination.mkdir(parents=True, exist_ok=True)
    for name, frame in frames:
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        canvas.alpha_composite(frame, ((canvas_width - frame.width) // 2, (canvas_height - frame.height) // 2))
        canvas.save(destination / f"{name}.png", optimize=True)


def extract_isolated_overrides() -> None:
    """Normalize individually generated poses that replace grid cells with crossed effects."""
    source_directory = SOURCE_DIR / "isolated"
    for group, names in ISOLATED_OVERRIDES.items():
        destination = OUTPUT_DIR / group
        for name in names:
            frame = Image.open(source_directory / f"{group}_{name}.png").convert("RGBA")
            alpha = frame.getchannel("A").point(lambda value: 0 if value <= 12 else value)
            frame.putalpha(alpha)
            frame = _trim_alpha(frame)
            frame.thumbnail((720, 720), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (768, 768), (0, 0, 0, 0))
            canvas.alpha_composite(frame, ((768 - frame.width) // 2, (768 - frame.height) // 2))
            canvas.save(destination / f"{name}.png", optimize=True)


def main() -> None:
    extract_pose_grid(
        "archivist_combat_grid.png", ARCHIVIST_GRID_NAMES, 3, "archivist", ARCHIVIST_EDGE_CLEANUP,
    )
    extract_pose_grid("pending_combat_grid.png", PENDING_GRID_NAMES, 4, "pending")
    extract_isolated_overrides()
    extract_icon_atlas()
    extract_trial_assets()
    print("Prepared isolated RPG combat frames in", OUTPUT_DIR)


if __name__ == "__main__":
    main()
