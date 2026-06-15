"""Generate EchoLearn macOS icon assets from the source PNG."""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
SOURCE_LOGO = ASSETS_DIR / "echolearn_logo.png"
ICONSET_DIR = ASSETS_DIR / "echolearn.iconset"
OUTPUT_ICON = ASSETS_DIR / "echolearn.icns"

ICONSET_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

ICNS_ENTRIES = [
    ("icp4", "icon_16x16.png"),
    ("icp5", "icon_32x32.png"),
    ("icp6", "icon_32x32@2x.png"),
    ("ic07", "icon_128x128.png"),
    ("ic08", "icon_256x256.png"),
    ("ic09", "icon_512x512.png"),
    ("ic10", "icon_512x512@2x.png"),
]


def main() -> None:
    if not SOURCE_LOGO.exists():
        raise FileNotFoundError(f"Missing source logo: {SOURCE_LOGO}")

    ICONSET_DIR.mkdir(parents=True, exist_ok=True)

    with Image.open(SOURCE_LOGO) as source:
        source = source.convert("RGBA")
        for filename, size in ICONSET_SIZES:
            image = source.resize((size, size), Image.Resampling.LANCZOS)
            image.save(ICONSET_DIR / filename)

    chunks = []
    for icon_type, filename in ICNS_ENTRIES:
        data = (ICONSET_DIR / filename).read_bytes()
        chunks.append(icon_type.encode("ascii") + struct.pack(">I", len(data) + 8) + data)

    body = b"".join(chunks)
    OUTPUT_ICON.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    print(f"Wrote {OUTPUT_ICON}")


if __name__ == "__main__":
    main()
