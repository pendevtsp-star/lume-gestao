from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\Users\maxue\Downloads\IMG_3887.PNG")
BUILD_DIR = ROOT / "desktop" / "build"
LINUX_ICON_DIR = BUILD_DIR / "icons"


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        raise SystemExit(f"Imagem nao encontrada: {source}")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    LINUX_ICON_DIR.mkdir(parents=True, exist_ok=True)

    image = Image.open(source).convert("RGBA")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    square = image.crop((left, top, left + side, top + side))

    icon_png = BUILD_DIR / "icon.png"
    square.resize((1024, 1024), Image.LANCZOS).save(icon_png)

    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        square.resize((size, size), Image.LANCZOS).save(LINUX_ICON_DIR / f"{size}x{size}.png")

    square.save(
        BUILD_DIR / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    square.resize((1024, 1024), Image.LANCZOS).save(BUILD_DIR / "icon.icns")
    square.resize((512, 512), Image.LANCZOS).save(BUILD_DIR / "icon-512.png")
    print(f"Icones gerados em {BUILD_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
