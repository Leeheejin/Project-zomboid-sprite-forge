"""Reader/writer for Project Zomboid ``.pack`` texture packs (PZPK format).

Layout (little-endian throughout)::

    char[4]  "PZPK"
    int32    version          (1)
    int32    numPages
    page[numPages]:
        int32  len, bytes     page name, e.g. "waterpipes0"
        int32  numEntries
        int32  hasAlpha       (always 1 in shipped packs)
        entry[numEntries]:
            int32 len, bytes  entry name, e.g. "waterpipes_01_0"
            int32 x, y        position of the trimmed sprite on the page
            int32 w, h        size of the trimmed sprite
            int32 ox, oy      offset of the trimmed sprite inside its original cell
            int32 ow, oh      original (untrimmed) cell size, e.g. 128x256
        int32  pngLength
        bytes  pngLength      the page image, PNG encoded

Trimming matters: PZ stores only the non-transparent bounding box of each tile and
records where it sat in the original cell. Getting ``ox/oy/ow/oh`` wrong makes a
sprite render offset in-game, which is the single most common failure mode when
hand-rolling a pack.

Some older shipped packs (UI.pack, JumboTrees*.pack, Mechanics.pack ...) omit the
magic and version, start straight at ``numPages``, and store each page's PNG with
no length prefix (its end is found by walking PNG chunks to IEND) followed by a
``0xDEADBEEF`` sentinel. Those are read transparently and re-written in whichever
form they came in.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

MAGIC = b"PZPK"
VERSION = 1
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: End-of-page sentinel used by the legacy headerless variant.
PAGE_SENTINEL = 0xDEADBEEF


def png_size(data: bytes, offset: int = 0) -> int:
    """Length in bytes of the PNG starting at ``offset``, found by walking chunks."""
    if data[offset:offset + 8] != PNG_SIGNATURE:
        raise ValueError(f"no PNG signature at offset {offset}")
    p = offset + 8
    while True:
        (length,) = struct.unpack_from(">I", data, p)
        ctype = data[p + 4:p + 8]
        p += 12 + length  # length + type + data + crc
        if ctype == b"IEND":
            return p - offset


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.d = data
        self.p = 0

    def i32(self) -> int:
        (v,) = struct.unpack_from("<i", self.d, self.p)
        self.p += 4
        return v

    def string(self) -> str:
        n = self.i32()
        if not 0 <= n <= 4096:
            raise ValueError(f"implausible string length {n} at offset {self.p - 4}")
        v = self.d[self.p:self.p + n].decode("utf-8")
        self.p += n
        return v

    def png(self) -> bytes:
        """Read a page image, whether length-prefixed or bare."""
        if self.d[self.p:self.p + 8] == PNG_SIGNATURE:
            n = png_size(self.d, self.p)
        else:
            n = self.i32()
            if self.d[self.p:self.p + 8] != PNG_SIGNATURE:
                raise ValueError(f"expected a PNG at offset {self.p}")
        v = self.d[self.p:self.p + n]
        if len(v) != n:
            raise ValueError(f"truncated page image: wanted {n}, got {len(v)}")
        self.p += n
        return v


class _Writer:
    def __init__(self) -> None:
        self.b = BytesIO()

    def i32(self, v: int) -> None:
        self.b.write(struct.pack("<i", int(v)))

    def string(self, s: str) -> None:
        raw = s.encode("utf-8")
        self.i32(len(raw))
        self.b.write(raw)

    def blob(self, v: bytes) -> None:
        self.i32(len(v))
        self.b.write(v)

    def raw(self, v: bytes) -> None:
        self.b.write(v)


@dataclass
class PackEntry:
    """One sprite on a page."""

    name: str
    x: int
    y: int
    w: int
    h: int
    ox: int = 0
    oy: int = 0
    ow: int = 0
    oh: int = 0

    def __post_init__(self) -> None:
        if not self.ow:
            self.ow = self.w + self.ox
        if not self.oh:
            self.oh = self.h + self.oy


@dataclass
class PackPage:
    """A single atlas page: a PNG plus the sprite rectangles cut out of it."""

    name: str
    png: bytes
    entries: list[PackEntry] = field(default_factory=list)
    has_alpha: int = 1


@dataclass
class TexturePack:
    pages: list[PackPage] = field(default_factory=list)
    version: int = VERSION
    #: False for the legacy headerless variant, which starts straight at numPages.
    has_header: bool = True

    # ---------------------------------------------------------------- reading

    @classmethod
    def read(cls, path: str | Path) -> "TexturePack":
        return cls.loads(Path(path).read_bytes())

    @classmethod
    def loads(cls, data: bytes) -> "TexturePack":
        r = _Reader(data)
        has_header = data[:4] == MAGIC
        if has_header:
            r.p = 4
            version = r.i32()
        else:
            version = VERSION
        num_pages = r.i32()
        if not 0 < num_pages < 4096:
            raise ValueError(f"not a PZ texture pack (numPages={num_pages})")
        pages: list[PackPage] = []
        for _ in range(num_pages):
            name = r.string()
            num_entries = r.i32()
            has_alpha = r.i32()
            entries = [
                PackEntry(r.string(), *(r.i32() for _ in range(8)))
                for _ in range(num_entries)
            ]
            png = r.png()
            if not has_header:
                sentinel = r.i32() & 0xFFFFFFFF
                if sentinel != PAGE_SENTINEL:
                    raise ValueError(f"bad page sentinel {sentinel:#x} after page {name!r}")
            pages.append(PackPage(name, png, entries, has_alpha))
        if r.p != len(data):
            raise ValueError(f"trailing data: {len(data) - r.p} bytes unread")
        return cls(pages=pages, version=version, has_header=has_header)

    # ---------------------------------------------------------------- writing

    def dumps(self) -> bytes:
        w = _Writer()
        if self.has_header:
            w.raw(MAGIC)
            w.i32(self.version)
        w.i32(len(self.pages))
        for page in self.pages:
            w.string(page.name)
            w.i32(len(page.entries))
            w.i32(page.has_alpha)
            for e in page.entries:
                w.string(e.name)
                for v in (e.x, e.y, e.w, e.h, e.ox, e.oy, e.ow, e.oh):
                    w.i32(v)
            if self.has_header:
                w.blob(page.png)
            else:
                w.raw(page.png)
                w.b.write(struct.pack("<I", PAGE_SENTINEL))
        return w.b.getvalue()

    def write(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.dumps())
        return path
