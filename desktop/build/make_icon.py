"""
Make the application icon (app.ico, 16-256 px) and the tray picture (tray.png) from the profile's logo.

    python desktop/build/make_icon.py [--profile default]

The logo can be SVG (drawn with PyMuPDF) or PNG. Build tool only: the installed app does not need it.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def load_logo(path: Path, size: int = 512):
    """The logo as a square RGBA Pillow image."""
    from PIL import Image

    if path.suffix.lower() == ".svg":
        import fitz  # PyMuPDF

        document = fitz.open(str(path))
        page = document[0]
        zoom = size / max(page.rect.width, page.rect.height)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
        image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGBA")
    else:
        image = Image.open(path).convert("RGBA")

    canvas = Image.new("RGBA", (max(image.size),) * 2, (0, 0, 0, 0))
    canvas.paste(image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2))
    return canvas


def make_icons(logo_path: Path, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    logo = load_logo(logo_path)
    ico, tray = out_dir / "app.ico", out_dir / "tray.png"
    logo.save(ico, format="ICO", sizes=ICON_SIZES)
    logo.resize((64, 64)).save(tray)
    return ico, tray


def main(argv=None) -> int:
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="default")
    args = parser.parse_args(argv)
    profile_dir = ROOT / "profiles" / args.profile
    profile = yaml.safe_load((profile_dir / "profile.yaml").read_text(encoding="utf-8"))
    ico, tray = make_icons(profile_dir / "assets" / profile.get("logo", "logo.svg"), ROOT / "desktop" / "assets")
    print(f"wrote {ico} and {tray}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
