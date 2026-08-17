"""Byte-exact round-trip check of the pack/tiles codecs against shipped game+mod files."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pzforge.packfile import TexturePack
from pzforge.tiledef import TileDefinitions

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid")
WS = Path(r"C:\PZServer\steamapps\workshop\content\108600")


def check(path: Path, kind: str) -> tuple[bool, str]:
    raw = path.read_bytes()
    try:
        obj = (TexturePack if kind == "pack" else TileDefinitions).loads(raw)
        out = obj.dumps()
    except Exception as ex:
        return False, f"{type(ex).__name__}: {ex}"
    if out != raw:
        n = next((i for i, (a, b) in enumerate(zip(out, raw)) if a != b), min(len(out), len(raw)))
        return False, f"mismatch at byte {n} (len {len(out)} vs {len(raw)})"
    if kind == "pack":
        pages = obj.pages
        detail = (f"{len(pages)} page(s), {sum(len(p.entries) for p in pages)} sprites, "
                  f"cells={sorted({(e.ow, e.oh) for p in pages for e in p.entries})[:4]}")
    else:
        detail = ", ".join(f"{t.name} {t.cols}x{t.rows} id={t.id}" for t in obj.tilesets[:3])
    return True, detail


def main() -> int:
    seen: set[Path] = set()
    targets: list[tuple[Path, str]] = []
    for pat, kind in (("*.pack", "pack"), ("*.tiles", "tiles")):
        for root in (PZ / "media", WS):
            for p in root.rglob(pat):
                if ".git" in p.parts or p in seen or p.stat().st_size > 400_000_000:
                    continue
                seen.add(p)
                targets.append((p, kind))

    ok = bad = 0
    failures = []
    for path, kind in targets:
        good, msg = check(path, kind)
        if good:
            ok += 1
            if ok <= 6 or "Tiles2x" in path.name:
                print(f"  PASS {path.name:<42} {msg}")
        else:
            bad += 1
            failures.append(f"  FAIL {path.name:<42} {msg}   [{path}]")
    print("\n".join(failures[:20]))
    print(f"\nround-trip: {ok} exact, {bad} failed, {len(targets)} files")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
