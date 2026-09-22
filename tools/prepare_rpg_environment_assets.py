"""Pad generated four-frame scenery sheets for safe runtime sampling."""

from __future__ import annotations

from pathlib import Path
import argparse

from PIL import Image


ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "rpg" / "environment"
FRAME_COUNT = 4
FRAME_PADDING = 32


def prepare_sheet(source: Path) -> Path:
    image = Image.open(source).convert("RGBA")
    if image.width % FRAME_COUNT:
        remainder = image.width % FRAME_COUNT
        if remainder > 3:
            raise ValueError(f"Sprite sheet width must divide into {FRAME_COUNT} frames: {source}")
        image = image.crop((0, 0, image.width - remainder, image.height))
    frame_width = image.width // FRAME_COUNT
    padded_frames = []
    for index in range(FRAME_COUNT):
        frame = image.crop((index * frame_width, 0, (index + 1) * frame_width, image.height))
        padded = Image.new(
            "RGBA",
            (frame_width + FRAME_PADDING * 2, image.height + FRAME_PADDING * 2),
            (0, 0, 0, 0),
        )
        padded.alpha_composite(frame, (FRAME_PADDING, FRAME_PADDING))
        padded_frames.append(padded)

    output = source.with_name(source.stem.replace("_sheet", "_runtime_sheet") + source.suffix)
    atlas = Image.new(
        "RGBA",
        (padded_frames[0].width * FRAME_COUNT, padded_frames[0].height),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(padded_frames):
        atlas.alpha_composite(frame, (index * frame.width, 0))
    atlas.save(output, optimize=True)
    return output


def lock_lunar_geometry(source: Path, output: Path) -> Path:
    """Keep the first-frame seal rigid while retaining cyan VFX animation."""
    image = Image.open(source).convert("RGBA")
    if image.width % FRAME_COUNT:
        remainder = image.width % FRAME_COUNT
        if remainder > 3:
            raise ValueError(f"Sprite sheet width must divide into {FRAME_COUNT} frames: {source}")
        image = image.crop((0, 0, image.width - remainder, image.height))
    frame_width = image.width // FRAME_COUNT
    frames = [image.crop((index * frame_width, 0, (index + 1) * frame_width, image.height)) for index in range(FRAME_COUNT)]
    base = frames[0]
    stabilized = []
    for frame in frames:
        result = base.copy()
        source_pixels = frame.load()
        target_pixels = result.load()
        for y in range(frame.height):
            for x in range(frame.width):
                red, green, blue, alpha = source_pixels[x, y]
                is_cyan_vfx = alpha > 12 and blue > red * 1.12 and green > red * 1.05 and green + blue > 180
                if is_cyan_vfx:
                    target_pixels[x, y] = (red, green, blue, alpha)
                base_red, base_green, base_blue, base_alpha = base.getpixel((x, y))
                is_brass_geometry = (
                    base_alpha > 32
                    and base_red > 82
                    and base_red > base_blue * 1.08
                    and base_green > base_blue * 0.72
                )
                if is_brass_geometry:
                    target_pixels[x, y] = (base_red, base_green, base_blue, base_alpha)
        stabilized.append(result)
    atlas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for index, frame in enumerate(stabilized):
        atlas.alpha_composite(frame, (index * frame_width, 0))
    atlas.save(output, optimize=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--lock-lunar", action="store_true")
    args = parser.parse_args()
    if args.source:
        source = args.source.resolve()
        if args.lock_lunar:
            locked = source.with_name(source.stem.replace("_sheet", "_locked_sheet") + source.suffix)
            source = lock_lunar_geometry(source, locked)
        print(prepare_sheet(source))
        return
    sources = sorted(ASSET_ROOT.rglob("*_idle_sheet.png"))
    if not sources:
        raise RuntimeError(f"No environment sprite sources found below {ASSET_ROOT}")
    for source in sources:
        print(prepare_sheet(source))


if __name__ == "__main__":
    main()
