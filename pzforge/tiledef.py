"""Reader/writer for Project Zomboid ``.tiles`` tile-definition files (tdef format).

Layout (little-endian ints, newline-terminated strings)::

    char[4]  "tdef"
    int32    version        (1)
    int32    numTilesets
    tileset[numTilesets]:
        str    name         "waterpipes_01\\n"
        str    imageName    "waterpipes_01.png\\n"
        int32  cols, rows    tilesheet grid, e.g. 8 x 4
        int32  id            tileset id
        int32  numTiles      always cols*rows; tiles are implicit in row-major order
        tile[numTiles]:
            int32 numProps
            (str key, str value)[numProps]     value may be empty (flag-style property)

Empty cells are written with ``numProps = 0`` — the grid is always dense.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

MAGIC = b"tdef"
VERSION = 1


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.d = data
        self.p = 0

    def i32(self) -> int:
        (v,) = struct.unpack_from("<i", self.d, self.p)
        self.p += 4
        return v

    def string(self) -> str:
        end = self.d.index(b"\n", self.p)
        v = self.d[self.p:end].decode("utf-8")
        self.p = end + 1
        return v


@dataclass
class Tile:
    """One cell of a tilesheet. ``props`` maps property name -> value ('' = flag)."""

    props: dict[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.props


@dataclass
class Tileset:
    name: str
    image: str
    cols: int
    rows: int
    id: int = 1
    tiles: list[Tile] = field(default_factory=list)

    def __post_init__(self) -> None:
        want = self.cols * self.rows
        if not self.tiles:
            self.tiles = [Tile() for _ in range(want)]
        elif len(self.tiles) != want:
            raise ValueError(
                f"tileset {self.name}: {len(self.tiles)} tiles for a {self.cols}x{self.rows} grid"
            )

    def at(self, col: int, row: int) -> Tile:
        return self.tiles[row * self.cols + col]

    def sprite_name(self, col: int, row: int) -> str:
        """PZ sprite id for a cell, e.g. ``waterpipes_01_5``."""
        return f"{self.name}_{row * self.cols + col}"


@dataclass
class TileDefinitions:
    tilesets: list[Tileset] = field(default_factory=list)
    version: int = VERSION

    # ---------------------------------------------------------------- reading

    @classmethod
    def read(cls, path: str | Path) -> "TileDefinitions":
        return cls.loads(Path(path).read_bytes())

    @classmethod
    def loads(cls, data: bytes) -> "TileDefinitions":
        if data[:4] != MAGIC:
            raise ValueError(f"not a tdef file (magic={data[:4]!r})")
        r = _Reader(data)
        r.p = 4
        version = r.i32()
        count = r.i32()
        tilesets = []
        for _ in range(count):
            name = r.string()
            image = r.string()
            cols, rows, tid = r.i32(), r.i32(), r.i32()
            num_tiles = r.i32()
            tiles = []
            for _ in range(num_tiles):
                nprops = r.i32()
                props = {}
                for _ in range(nprops):
                    key = r.string()
                    props[key] = r.string()
                tiles.append(Tile(props))
            tilesets.append(Tileset(name, image, cols, rows, tid, tiles))
        if r.p != len(data):
            raise ValueError(f"trailing data: {len(data) - r.p} bytes unread")
        return cls(tilesets=tilesets, version=version)

    # ---------------------------------------------------------------- writing

    def dumps(self) -> bytes:
        b = BytesIO()
        b.write(MAGIC)
        b.write(struct.pack("<ii", self.version, len(self.tilesets)))
        for ts in self.tilesets:
            b.write(ts.name.encode("utf-8") + b"\n")
            b.write(ts.image.encode("utf-8") + b"\n")
            b.write(struct.pack("<iiii", ts.cols, ts.rows, ts.id, len(ts.tiles)))
            for tile in ts.tiles:
                b.write(struct.pack("<i", len(tile.props)))
                for key, value in tile.props.items():
                    b.write(key.encode("utf-8") + b"\n")
                    b.write(value.encode("utf-8") + b"\n")
        return b.getvalue()

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.dumps())
        return path

    # ----------------------------------------------------------- readable form

    def to_text(self) -> str:
        """Render in the same shape as PZ's shipped ``.tiles.txt`` companions."""
        out = [f"version = {self.version}"]
        for ts in self.tilesets:
            out += ["tileset", "{",
                    f"    file = {ts.name}",
                    f"    size = {ts.cols},{ts.rows}",
                    f"    id = {ts.id}"]
            for i, tile in enumerate(ts.tiles):
                if tile.empty:
                    continue
                out += [f"    // {ts.name}_{i}", "    tile", "    {",
                        f"        xy = {i % ts.cols},{i // ts.cols}"]
                out += [f"        {k} = {v}" for k, v in tile.props.items()]
                out.append("    }")
            out.append("}")
        return "\n".join(out) + "\n"
