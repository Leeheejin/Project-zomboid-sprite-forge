"""Assemble a loadable Project Zomboid mod around a generated pack and tiledef.

A tile mod is only three things beyond the art: the ``.pack``, the ``.tiles``, and a
``mod.info`` that points at both::

    name=My Tiles
    id=MyTiles
    tiledef=mytiles 2282
    pack=mytiles

The number after ``tiledef`` is a global id. Two enabled mods sharing one will fight
over the same tile range and one of them loses its sprites, so :func:`free_tiledef_id`
scans what is already installed rather than picking a number and hoping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: Where installed mods live on a default Windows install.
MOD_SEARCH_PATHS = [
    Path.home() / "Zomboid" / "mods",
    Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\108600"),
    Path(r"C:\PZServer\steamapps\workshop\content\108600"),
]

#: Ids below this are vanilla/reserved territory; community mods sit well above.
TILEDEF_ID_FLOOR = 2000

_TILEDEF_LINE = re.compile(r"^\s*tiledef\s*=\s*(\S+)\s+(\d+)", re.MULTILINE)


def used_tiledef_ids(search_paths: list[Path] | None = None) -> dict[int, list[str]]:
    """Map every tiledef id already claimed by an installed mod to the mods using it."""
    found: dict[int, list[str]] = {}
    for root in (search_paths or MOD_SEARCH_PATHS):
        if not root.exists():
            continue
        for info in root.rglob("mod.info"):
            try:
                text = info.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, raw in _TILEDEF_LINE.findall(text):
                found.setdefault(int(raw), []).append(f"{info.parent.name}:{name}")
    return found


def free_tiledef_id(search_paths: list[Path] | None = None,
                    start: int = TILEDEF_ID_FLOOR) -> int:
    """Lowest id at or above ``start`` that no installed mod claims."""
    taken = used_tiledef_ids(search_paths)
    candidate = start
    while candidate in taken:
        candidate += 1
    return candidate


@dataclass
class ModInfo:
    id: str
    name: str
    description: str = ""
    author: str = ""
    poster: str = "poster.png"
    tiledef: str = ""
    tiledef_id: int = TILEDEF_ID_FLOOR
    pack: str = ""
    require: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"name={self.name}", f"id={self.id}"]
        if self.description:
            lines.append(f"description={self.description}")
        if self.author:
            lines.append(f"author={self.author}")
        if self.poster:
            lines.append(f"poster={self.poster}")
        if self.tiledef:
            lines.append(f"tiledef={self.tiledef} {self.tiledef_id}")
        if self.pack:
            lines.append(f"pack={self.pack}")
        for req in self.require:
            lines.append(f"require={req}")
        return "\n".join(lines) + "\n"


@dataclass
class ModLayout:
    """Resolved paths inside a mod folder, for B41-style and B42-style layouts."""

    root: Path
    media: Path
    texturepacks: Path

    @classmethod
    def create(cls, out_dir: Path, mod_id: str, build: str | None = "42") -> "ModLayout":
        # B42 loads a versioned subfolder; B41 reads the mod root directly.
        root = out_dir / mod_id / build if build else out_dir / mod_id
        media = root / "media"
        texturepacks = media / "texturepacks"
        texturepacks.mkdir(parents=True, exist_ok=True)
        return cls(root, media, texturepacks)
