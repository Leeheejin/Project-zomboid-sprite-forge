"""Contact sheet of vanilla sprites, for picking recreation targets.

Run with:
    uv run --python 3.12 --with pillow python tools/contact_sheet.py <name-substring> [out.png]
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks")


def sprites(substring: str, limit: int = 48):
    out = []
    for pack_name in ("Tiles2x.pack", "Tiles2x.floor.pack"):
        pack = TexturePack.read(PZ / pack_name)
        for page in pack.pages:
            atlas = None
            for e in page.entries:
                if substring not in e.name or (e.ow, e.oh) != (128, 256):
                    continue
                if atlas is None:
                    atlas = Image.open(io.BytesIO(page.png)).convert("RGBA")
                cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
                cell.paste(atlas.crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
                out.append((e.name, cell))
                if len(out) >= limit:
                    return out
    return out


def main() -> None:
    substring = sys.argv[1]
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "build/contact.png")
    found = sprites(substring)
    if not found:
        raise SystemExit(f"no sprites matching {substring!r}")

    cols = 8
    rows = -(-len(found) // cols)
    cw, ch = 128, 200  # crop off the empty top of each cell
    sheet = Image.new("RGBA", (cols * cw, rows * (ch + 12)), (32, 34, 38, 255))
    for i, (_name, cell) in enumerate(found):
        sheet.alpha_composite(cell.crop((0, 256 - ch, 128, 256)),
                              ((i % cols) * cw, (i // cols) * (ch + 12)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)

    print(f"{len(found)} sprites matching {substring!r} -> {out_path}")
    for i, (name, _cell) in enumerate(found):
        print(f"   [{i % cols},{i // cols}] {name}")


if __name__ == "__main__":
    main()
