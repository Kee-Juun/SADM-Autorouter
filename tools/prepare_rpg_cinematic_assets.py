"""Normalize generated RPG sheets into equal, tightly framed runtime cells."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RPG = ROOT / "assets" / "rpg"


def normalized_sheet(source: Path, destination: Path, count: int, cell_size: tuple[int, int]) -> None:
    image = Image.open(source).convert("RGBA")
    source_width = image.width / count
    output = Image.new("RGBA", (cell_size[0] * count, cell_size[1]), (0, 0, 0, 0))
    for index in range(count):
        left = round(index * source_width)
        right = round((index + 1) * source_width)
        frame = image.crop((left, 0, right, image.height))
        alpha_box = frame.getchannel("A").point(lambda value: 255 if value > 12 else 0).getbbox()
        if not alpha_box:
            continue
        frame = frame.crop(alpha_box)
        scale = min((cell_size[0] - 16) / frame.width, (cell_size[1] - 16) / frame.height)
        size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
        frame = frame.resize(size, Image.Resampling.LANCZOS)
        x = index * cell_size[0] + (cell_size[0] - frame.width) // 2
        y = cell_size[1] - frame.height - 8
        output.alpha_composite(frame, (x, y))
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.save(destination)


def normalized_grid_sheet(
    source: Path,
    destination: Path,
    columns: int,
    rows: int,
    cell_size: tuple[int, int],
    content_height: int | None = None,
) -> None:
    """Flatten a separated grid while preserving one shared scale and baseline."""
    image = Image.open(source).convert("RGBA")
    source_width = image.width / columns
    source_height = image.height / rows
    frame_count = columns * rows
    frames = []
    max_width = 1
    max_height = 1
    for index in range(frame_count):
        column = index % columns
        row = index // columns
        frame = image.crop((
            round(column * source_width),
            round(row * source_height),
            round((column + 1) * source_width),
            round((row + 1) * source_height),
        ))
        alpha_box = frame.getchannel("A").point(lambda value: 255 if value > 12 else 0).getbbox()
        if alpha_box:
            frame = frame.crop(alpha_box)
            max_width = max(max_width, frame.width)
            max_height = max(max_height, frame.height)
        frames.append(frame)
    scale = min((cell_size[0] - 16) / max_width, (cell_size[1] - 16) / max_height)
    output = Image.new("RGBA", (cell_size[0] * frame_count, cell_size[1]), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        frame_scale = scale
        if content_height is not None:
            frame_scale = min(content_height / frame.height, (cell_size[0] - 16) / frame.width)
        frame = frame.resize(
            (max(1, round(frame.width * frame_scale)), max(1, round(frame.height * frame_scale))),
            Image.Resampling.LANCZOS,
        )
        x = index * cell_size[0] + (cell_size[0] - frame.width) // 2
        y = cell_size[1] - frame.height - 8
        output.alpha_composite(frame, (x, y))
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.save(destination)


def normalized_icon(source: Path, destination: Path, size: int = 512) -> None:
    image = Image.open(source).convert("RGBA")
    alpha_box = image.getchannel("A").getbbox()
    if alpha_box:
        image = image.crop(alpha_box)
    scale = min((size - 32) / image.width, (size - 32) / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    output.save(destination)


def main() -> None:
    normalized_grid_sheet(
        RPG / "last_clerk_directional_walk_sheet_v2.png",
        RPG / "last_clerk_directional_walk_runtime_sheet.png",
        4,
        3,
        (280, 260),
        content_height=236,
    )
    normalized_grid_sheet(
        RPG / "last_clerk_back_walk_sheet_v2.png",
        RPG / "last_clerk_back_walk_runtime_sheet.png",
        4,
        1,
        (280, 260),
        content_height=236,
    )
    normalized_grid_sheet(
        RPG / "last_clerk_idle_actions_sheet_v2.png",
        RPG / "last_clerk_idle_actions_runtime_sheet.png",
        4,
        3,
        (280, 260),
        content_height=236,
    )
    normalized_grid_sheet(
        RPG / "last_clerk_back_idle_actions_sheet_v1.png",
        RPG / "last_clerk_back_idle_actions_runtime_sheet.png",
        4,
        3,
        (280, 260),
        content_height=236,
    )
    normalized_sheet(RPG / "dialogue/mara_closeup_idle_sheet.png", RPG / "dialogue/mara_closeup_idle_runtime_sheet.png", 4, (340, 430))
    normalized_sheet(RPG / "dialogue/archivist_closeup_idle_sheet.png", RPG / "dialogue/archivist_closeup_idle_runtime_sheet.png", 4, (340, 430))
    normalized_sheet(RPG / "combat/pending_minion/minion_sheet.png", RPG / "combat/pending_minion/minion_runtime_sheet.png", 4, (280, 360))
    normalized_sheet(RPG / "cinematics/pending_throne_summon_sheet.png", RPG / "cinematics/pending_throne_summon_runtime_sheet.png", 6, (360, 430))
    normalized_sheet(RPG / "cinematics/archivist_confrontation_sheet.png", RPG / "cinematics/archivist_confrontation_runtime_sheet.png", 6, (300, 390))
    normalized_sheet(RPG / "cinematics/mara_rescue_sheet.png", RPG / "cinematics/mara_rescue_runtime_sheet.png", 4, (500, 430))
    normalized_sheet(RPG / "cinematics/pending_victory_sheet.png", RPG / "cinematics/pending_victory_runtime_sheet.png", 4, (500, 430))
    normalized_icon(RPG / "quest/icons/vault_key_relic.png", RPG / "quest/icons/vault_key_relic_runtime.png")
    normalized_icon(RPG / "quest/icons/pending_codex.png", RPG / "quest/icons/pending_codex_runtime.png")


if __name__ == "__main__":
    main()
