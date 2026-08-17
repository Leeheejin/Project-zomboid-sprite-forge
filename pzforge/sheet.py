"""Turn rendered tile cells into a tilesheet PNG and a packed ``.pack`` atlas.

A PZ tilesheet is a dense ``cols x rows`` grid of fixed-size cells; a sprite's id is
``<sheetname>_<row * cols + col>``. The ``.pack`` stores the same sprites trimmed to
their opaque bounding box, remembering where each sat in its cell -- so the grid and
the atlas have to agree on indices exactly, which is what this module guarantees.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .packfile import PackEntry, PackPage, TexturePack

#: Vanilla builds its packs at 1024x1024 (see B42ChunkCaching2x.txt).
DEFAULT_PAGE_SIZE = 1024
DEFAULT_COLUMNS = 8


@dataclass
class Cell:
    """One rendered tile, together with where it belongs in the sheet."""

    image: Image.Image
    facing: str = "S"
    x: int = 0
    y: int = 0
    index: int = -1
    source: str = ""
    #: Position of this cell's facing in the manifest, so facings stay contiguous.
    facing_order: int = 0


@dataclass
class Sheet:
    name: str
    cell_w: int
    cell_h: int
    cols: int
    cells: list[Cell] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return max(1, -(-len(self.cells) // self.cols))

    def sprite_name(self, index: int) -> str:
        return f"{self.name}_{index}"

    def image(self) -> Image.Image:
        """The dense grid PNG that the ``.tiles`` file names."""
        sheet = Image.new("RGBA", (self.cols * self.cell_w, self.rows * self.cell_h),
                          (0, 0, 0, 0))
        for cell in self.cells:
            col, row = cell.index % self.cols, cell.index // self.cols
            sheet.paste(cell.image, (col * self.cell_w, row * self.cell_h))
        return sheet


def build_sheet(name: str, cells: list[Cell], cell_size: tuple[int, int],
                cols: int = DEFAULT_COLUMNS) -> Sheet:
    """Assign sequential grid indices to cells, keeping facings contiguous."""
    ordered = sorted(cells, key=lambda c: (c.facing_order, c.y, c.x))
    for i, cell in enumerate(ordered):
        cell.index = i
        if cell.image.size != cell_size:
            raise ValueError(
                f"cell {cell.source or i} is {cell.image.size}, expected {cell_size}"
            )
    return Sheet(name, cell_size[0], cell_size[1], cols, ordered)


def _trim(img: Image.Image) -> tuple[Image.Image, int, int] | None:
    box = img.getbbox()
    if box is None:
        return None
    left, upper, right, lower = box
    return img.crop(box), left, upper


def pack_sheet(sheet: Sheet, page_size: int = DEFAULT_PAGE_SIZE,
               padding: int = 1) -> TexturePack:
    """Shelf-pack the sheet's non-empty cells into one or more atlas pages."""
    trimmed = []
    for cell in sheet.cells:
        result = _trim(cell.image)
        if result is None:
            continue  # fully transparent cells simply get no pack entry
        crop, ox, oy = result
        trimmed.append((sheet.sprite_name(cell.index), crop, ox, oy))

    if not trimmed:
        raise ValueError("every cell is empty -- nothing to pack")

    oversized = [n for n, c, _, _ in trimmed
                 if c.width + padding > page_size or c.height + padding > page_size]
    if oversized:
        raise ValueError(
            f"sprite(s) {oversized[:3]} exceed the {page_size}px page; raise --page-size"
        )

    # Tallest first: shelf packing wastes far less space that way.
    trimmed.sort(key=lambda t: (-t[1].height, -t[1].width))

    pages: list[PackPage] = []
    canvas = Image.new("RGBA", (page_size, page_size), (0, 0, 0, 0))
    entries: list[PackEntry] = []
    cursor_x = cursor_y = shelf_h = 0

    def flush() -> None:
        nonlocal canvas, entries, cursor_x, cursor_y, shelf_h
        if not entries:
            return
        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        pages.append(PackPage(f"{sheet.name}{len(pages)}", buf.getvalue(), entries))
        canvas = Image.new("RGBA", (page_size, page_size), (0, 0, 0, 0))
        entries = []
        cursor_x = cursor_y = shelf_h = 0

    for name, crop, ox, oy in trimmed:
        w, h = crop.size
        if cursor_x + w > page_size:
            cursor_x = 0
            cursor_y += shelf_h + padding
            shelf_h = 0
        if cursor_y + h > page_size:
            flush()
        canvas.paste(crop, (cursor_x, cursor_y))
        entries.append(PackEntry(name, cursor_x, cursor_y, w, h, ox, oy,
                                 sheet.cell_w, sheet.cell_h))
        cursor_x += w + padding
        shelf_h = max(shelf_h, h)

    flush()
    # Restore sheet order so the pack reads the same way the grid does.
    for page in pages:
        page.entries.sort(key=lambda e: int(e.name.rsplit("_", 1)[1]))
    return TexturePack(pages=pages)


def load_cells(directory: Path, manifest: dict) -> list[Cell]:
    """Read the cells listed in a render manifest written by the Blender addon."""
    facing_rank = {f: i for i, f in enumerate(manifest.get("facings", ["S"]))}
    cells = []
    for record in manifest["cells"]:
        path = directory / record["file"]
        if not path.exists():
            raise FileNotFoundError(f"manifest lists {record['file']} but it is missing")
        cell = Cell(Image.open(path).convert("RGBA"), record.get("facing", "S"),
                    record.get("x", 0), record.get("y", 0), source=record["file"])
        cell.facing_order = facing_rank.get(cell.facing, 0)
        cells.append(cell)
    return cells
