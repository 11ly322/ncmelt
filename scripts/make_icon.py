"""Create the ncmelt application icon."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ASSETS = ROOT / "ncmelt" / "assets"

BG = "#1E232B"
BORDER = "#323A47"
BLUE = "#3D7DFF"
STEEL = "#7487A8"
ORANGE = "#FFA64D"
WHITE = "#F7F9FC"


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size * 4, size * 4), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (0, 0, size * 4 - 1, size * 4 - 1), radius=radius * 4, fill=255
    )
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def make_icon(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = rounded_mask(size, int(size * 0.22))
    body = Image.new("RGBA", (size, size), BG)
    image.paste(body, (0, 0), mask)

    draw = ImageDraw.Draw(image)
    # Thin flat border, like a desktop tile.
    draw.rounded_rectangle(
        (4, 4, size - 5, size - 5),
        radius=int(size * 0.22),
        outline=BORDER,
        width=max(2, size // 180),
    )

    # Orange sun behind the arrow's shoulder.
    sun_r = size * 0.125
    sun_cx, sun_cy = size * 0.665, size * 0.300
    draw.ellipse(
        (sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r),
        fill=ORANGE,
    )

    # A big geometric down arrow, split into a steel-blue left face and a
    # vivid blue right face.
    split = size * 0.505
    head_y = size * 0.475
    tip_y = size * 0.800
    left_x = size * 0.245
    right_x = size * 0.755
    shaft_left = size * 0.410
    shaft_right = size * 0.600
    shaft_top = size * 0.205

    # Shaft, split down the centre.
    draw.rectangle(
        (shaft_left, shaft_top, split, head_y),
        fill=STEEL,
    )
    draw.rectangle(
        (split, shaft_top, shaft_right, head_y),
        fill=BLUE,
    )
    # Arrow head, split down the centre.
    draw.polygon(
        [(left_x, head_y), (split, head_y), (split, tip_y)],
        fill=STEEL,
    )
    draw.polygon(
        [(split, head_y), (right_x, head_y), (split, tip_y)],
        fill=BLUE,
    )

    # Output tray line.
    tray_y = size * 0.875
    draw.rounded_rectangle(
        (size * 0.285, tray_y, size * 0.715, tray_y + size * 0.022),
        radius=size * 0.011,
        fill=WHITE,
    )
    return image


def main() -> None:
    PACKAGE_ASSETS.mkdir(parents=True, exist_ok=True)
    icon = make_icon(1024)
    icon.save(PACKAGE_ASSETS / "app.png")
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(
        PACKAGE_ASSETS / "app-256.png"
    )
    icon.resize((128, 128), Image.Resampling.LANCZOS).save(
        PACKAGE_ASSETS / "app-128.png"
    )
    icon.resize((64, 64), Image.Resampling.LANCZOS).save(PACKAGE_ASSETS / "app-64.png")
    icon.save(
        PACKAGE_ASSETS / "app.ico",
        format="ICO",
        sizes=[
                (16, 16),
                (24, 24),
                (32, 32),
                (48, 48),
                (64, 64),
                (128, 128),
                (256, 256),
            ],
        )


if __name__ == "__main__":
    main()
