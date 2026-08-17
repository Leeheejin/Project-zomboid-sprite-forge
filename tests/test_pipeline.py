"""End-to-end: cells on disk -> mod folder -> read the mod back and verify it.

Real vanilla sprites stand in for Blender renders, so the test also proves the
pipeline preserves pixels the engine would actually draw.

Run with:  uv run --python 3.12 --with pillow python tests/test_pipeline.py
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pzforge import modgen
from pzforge.cli import main as cli_main
from pzforge.packfile import TexturePack
from pzforge.style import (bleed_edges, edge_relief, load_profile, match_tone,
                           measure, measure_relief, snap_alpha)
from pzforge.tiledef import TileDefinitions

PZ = Path(r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\texturepacks")
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  -- ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(label)


def make_cells(dst: Path, count: int = 6) -> dict:
    """Write real vanilla sprites out as if the Blender addon had rendered them."""
    pack = TexturePack.read(PZ / "Tiles2x.pack")
    picked = []
    for page in pack.pages:
        atlas = None
        for e in page.entries:
            if (e.ow, e.oh) != (128, 256) or e.w < 60 or e.h < 100:
                continue
            if atlas is None:
                atlas = Image.open(io.BytesIO(page.png)).convert("RGBA")
            cell = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
            cell.paste(atlas.crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
            picked.append(cell)
            if len(picked) >= count:
                break
        if len(picked) >= count:
            break

    dst.mkdir(parents=True, exist_ok=True)
    records = []
    for i, img in enumerate(picked):
        name = f"forgetest_S_x{i % 3}_y{i // 3}.png"
        img.save(dst / name)
        records.append({"file": name, "facing": "S", "x": i % 3, "y": i // 3})
    manifest = {"sheet": "forgetest_01", "cell": [128, 256], "scale": "2x",
                "footprint": [3, 2], "facings": ["S"], "cells": records}
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def test_style() -> None:
    print("\n== style pass ==")
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    img.putpixel((8, 8), (220, 40, 40, 255))
    img.putpixel((9, 8), (220, 40, 40, 3))  # sub-threshold dust

    snapped = snap_alpha(img, 8)
    check("dust below the alpha floor is cleared", snapped.getpixel((9, 8))[3] == 0)
    check("solid pixels keep full alpha", snapped.getpixel((8, 8))[3] == 255)

    bled = bleed_edges(snapped, passes=1)
    neighbour = bled.getpixel((7, 8))
    check("colour bleeds into transparent neighbours",
          neighbour[:3] != (0, 0, 0) and neighbour[3] == 0,
          f"neighbour={neighbour}")
    check("bleeding never changes alpha",
          [p[3] for p in bled.getdata()] == [p[3] for p in snapped.getdata()])

    # A blown-out, over-saturated render should come back inside the vanilla band.
    hot = Image.new("RGBA", (32, 32), (255, 30, 10, 255))
    toned = match_tone(hot, strength=1.0)
    r, g, b, _ = toned.getpixel((0, 0))
    check("over-bright render is pulled toward the vanilla band",
          max(r, g, b) < 255, f"got {(r, g, b)}")
    check("style pass is a no-op at strength 0",
          list(match_tone(hot, strength=0.0).getdata()) == list(hot.getdata()))

    # Regression: histogram matching used to stretch a low-contrast sprite across the
    # whole tileset's range, amplifying 8-bit steps into speckle. A sprite already
    # inside the vanilla band must come back untouched.
    profile = load_profile()
    calm = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for y in range(64):
        for x in range(64):
            # A muted brown with a gentle gradient: spread ~0.1, well inside vanilla.
            v = 90 + (x + y) // 8
            calm.putpixel((x, y), (v, int(v * 0.70), int(v * 0.42), 255))
    before = measure(calm)
    after = measure(match_tone(calm, strength=1.0))
    lo, hi = profile["value_spread"]["p10"], profile["value_spread"]["p90"]
    check("test sprite starts inside the vanilla contrast band",
          lo <= before["value_spread"] <= hi, f"spread={before['value_spread']:.3f}")
    check("in-band sprite is left untouched by tone matching",
          abs(after["value_spread"] - before["value_spread"]) < 0.01
          and abs(after["median_value"] - before["median_value"]) < 0.01,
          f"spread {before['value_spread']:.3f}->{after['value_spread']:.3f}, "
          f"value {before['median_value']:.3f}->{after['median_value']:.3f}")
    check("tone matching never inflates contrast beyond the vanilla ceiling",
          after["value_spread"] <= max(hi, before["value_spread"]) + 1e-6,
          f"{after['value_spread']:.3f} vs ceiling {hi:.3f}")

    # Edge relief: a reference whose painter accents below its horizontal lines must
    # produce an accent below -- and only below -- the render's own lines. Both
    # sprites are mid-grey fills with one dark horizontal line through the middle;
    # the reference carries a painted bright row under its line.
    def lined(accent_below: int) -> Image.Image:
        sp = Image.new("RGBA", (32, 32), (128, 128, 128, 255))
        for x in range(32):
            sp.putpixel((x, 15), (60, 60, 60, 255))
            if accent_below:
                sp.putpixel((x, 16), (min(255, 128 + accent_below), ) * 3 + (255,))
        return sp

    deltas = measure_relief(lined(accent_below=40))
    check("relief measurement finds the accent below horizontal lines",
          deltas.get(("horiz", "D"), 0.0) > 0.05,
          f"D={deltas.get(('horiz', 'D'), 0.0):+.3f}")
    check("relief measurement leaves the unaccented side near zero",
          abs(deltas.get(("horiz", "U"), 0.0)) < 0.02,
          f"U={deltas.get(('horiz', 'U'), 0.0):+.3f}")

    plain = lined(accent_below=0)
    accented = edge_relief(plain, deltas)
    below = accented.getpixel((16, 16))[0]
    above = accented.getpixel((16, 14))[0]
    check("relief brightens the measured side of the render's lines",
          below > 133, f"below={below}")
    check("relief leaves the other side alone", above == 128, f"above={above}")
    check("relief is a no-op at strength 0",
          list(edge_relief(plain, deltas, strength=0.0).getdata())
          == list(plain.getdata()))

    # Element finishing: a small fitting on a body must come out lit on top,
    # shaded underneath, and the body row right below it must catch the lit lip.
    from pzforge.finish import finish
    # 30x30 so the body is above the small-fitting threshold and gets no drift.
    base = Image.new("RGBA", (30, 30), (128, 128, 128, 255))
    labels = ["body"] * (30 * 30)
    for y in range(8, 13):
        for x in range(6, 14):
            labels[y * 30 + x] = "fitting"
    finished = finish(base, labels, strength=1.0)

    def val(x, y):
        return finished.getpixel((x, y))[0]

    check("fitting top edge is lit", val(10, 8) > 128, f"top={val(10, 8)}")
    check("fitting underside is shaded", val(10, 12) < 128, f"bottom={val(10, 12)}")
    check("body below the fitting catches a lit lip", val(10, 13) > 128,
          f"lip={val(10, 13)}")
    check("body far from any boundary is untouched", val(3, 3) == 128)
    check("finishing is a no-op at strength 0",
          list(finish(base, labels, strength=0.0).getdata())
          == list(base.getdata()))

    # Tone blocking: a small fitting carrying a smooth ramp must collapse to its
    # measured budget of 2 tones at full strength.
    from pzforge.finish import tone_block
    ramp = Image.new("RGBA", (30, 30), (128, 128, 128, 255))
    ramp_labels = ["body"] * (30 * 30)
    for y in range(10, 18):
        for x in range(10, 18):
            ramp_labels[y * 30 + x] = "knob"
            v = 90 + (x - 10) * 12
            ramp.putpixel((x, y), (v, v, v, 255))
    blocked = tone_block(ramp, ramp_labels, strength=1.0)
    knob_values = {blocked.getpixel((x, y))[0]
                   for y in range(10, 18) for x in range(10, 18)}
    check("small fitting collapses to its 2-tone budget", len(knob_values) <= 3,
          f"{len(knob_values)} distinct values")
    check("tone blocking leaves other elements alone",
          blocked.getpixel((3, 3))[:3] == (128, 128, 128))
    check("tone blocking is a no-op at strength 0",
          list(tone_block(ramp, ramp_labels, strength=0.0).getdata())
          == list(ramp.getdata()))

    # Relight: constant paint under a smooth light ramp must come back as that
    # paint under *stepped* light -- few distinct values, mean level preserved.
    from pzforge.relight import relight, _linear, _srgb
    W = 24
    paint_lin = 0.30
    light_img = Image.new("RGBA", (W, W))
    beauty_img = Image.new("RGBA", (W, W))
    for y in range(W):
        for x in range(W):
            light_lin = 0.9 - 0.6 * x / (W - 1)
            lv = round(_srgb(light_lin) * 255)
            light_img.putpixel((x, y), (lv, lv, lv, 255))
            bv = round(_srgb(paint_lin * light_lin) * 255)
            beauty_img.putpixel((x, y), (bv, bv, bv, 255))
    recipes_stub = {"window_tones": {"median": 3, "window_px": 12}}
    relit = relight(beauty_img, light_img, ["a"] * (W * W), recipes_stub,
                    paint_flatten=0.0, light_steps=1.0)
    row = [relit.getpixel((x, 10))[0] for x in range(W)]
    original_row = [beauty_img.getpixel((x, 10))[0] for x in range(W)]
    # 3 clusters plus 8-bit division residue: a handful of values, not a ramp.
    check("relight steps a smooth light ramp into the tone budget",
          len(set(row)) <= 6 < len(set(original_row)),
          f"{len(set(original_row))} values -> {len(set(row))}")
    check("relight preserves the overall light level",
          abs(sum(row) - sum(original_row)) / sum(original_row) < 0.08,
          f"mean {sum(original_row) / W:.0f} -> {sum(row) / W:.0f}")


def test_pipeline(tmp: Path) -> None:
    print("\n== build pipeline ==")
    cells = tmp / "cells"
    manifest = make_cells(cells)
    out = tmp / "dist"

    rc = cli_main(["build", str(cells), "--out", str(out), "--mod-id", "ForgeTest",
                   "--mod-name", "Forge Test Tiles", "--preset", "furniture",
                   "--prop", "CustomName=Test Bench", "--tiledef-id", "9911",
                   "--no-style"])
    check("build exits cleanly", rc == 0, f"rc={rc}")

    root = out / "ForgeTest" / "42"
    pack_path = root / "media" / "texturepacks" / "forgetest_01.pack"
    tiles_path = root / "media" / "forgetest_01.tiles"
    check("pack written", pack_path.exists())
    check("tiles written", tiles_path.exists())
    check("grid sheet written", (root / "media" / "forgetest_01.png").exists())

    info = (root / "mod.info").read_text()
    check("mod.info declares the tiledef", "tiledef=forgetest_01 9911" in info, info.strip())
    check("mod.info declares the pack", "pack=forgetest_01" in info)

    # --- the pack must survive a round trip through the game's own format ---
    raw = pack_path.read_bytes()
    pack = TexturePack.read(pack_path)
    check("generated pack re-encodes byte-exactly", pack.dumps() == raw)
    check("generated pack uses the modern PZPK header", pack.has_header)

    entries = {e.name: e for p in pack.pages for e in p.entries}
    check("one entry per rendered cell", len(entries) == len(manifest["cells"]),
          f"{len(entries)} entries")
    check("sprites are named <sheet>_<index>",
          set(entries) == {f"forgetest_01_{i}" for i in range(len(manifest["cells"]))},
          ", ".join(sorted(entries)[:3]))
    check("every entry records the 128x256 cell",
          all((e.ow, e.oh) == (128, 256) for e in entries.values()))
    check("trimmed rect always fits inside its cell",
          all(e.ox + e.w <= e.ow and e.oy + e.oh >= e.oy + e.h
              for e in entries.values()))

    # --- pixels must be identical to what went in ---
    atlas_by_page = {id(p): Image.open(io.BytesIO(p.png)).convert("RGBA")
                     for p in pack.pages}
    mismatch = []
    for page in pack.pages:
        atlas = atlas_by_page[id(page)]
        for e in page.entries:
            index = int(e.name.rsplit("_", 1)[1])
            record = manifest["cells"][index]
            original = Image.open(cells / record["file"]).convert("RGBA")
            rebuilt = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
            rebuilt.paste(atlas.crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
            if list(rebuilt.getdata()) != list(original.getdata()):
                mismatch.append(e.name)
    check("unpacking reproduces the source cells pixel for pixel",
          not mismatch, f"differs: {mismatch[:3]}")

    # With the style pass on, colour may legitimately move but the silhouette must
    # not -- a changed alpha channel means a changed collision/render footprint.
    styled_out = tmp / "dist_styled"
    cli_main(["build", str(cells), "--out", str(styled_out), "--mod-id", "ForgeStyled",
              "--tiledef-id", "9912", "--style-strength", "0.6"])
    styled = TexturePack.read(styled_out / "ForgeStyled" / "42" / "media" /
                              "texturepacks" / "forgetest_01.pack")
    alpha_changed = []
    for page in styled.pages:
        atlas = Image.open(io.BytesIO(page.png)).convert("RGBA")
        for e in page.entries:
            index = int(e.name.rsplit("_", 1)[1])
            original = Image.open(cells / manifest["cells"][index]["file"]).convert("RGBA")
            rebuilt = Image.new("RGBA", (e.ow, e.oh), (0, 0, 0, 0))
            rebuilt.paste(atlas.crop((e.x, e.y, e.x + e.w, e.y + e.h)), (e.ox, e.oy))
            got = [p[3] for p in rebuilt.getdata()]
            want = [0 if p[3] < 8 else p[3] for p in original.getdata()]
            if got != want:
                alpha_changed.append(e.name)
    check("style pass leaves the silhouette untouched",
          not alpha_changed, f"differs: {alpha_changed[:3]}")

    # --- tile definitions ---
    tdefs = TileDefinitions.read(tiles_path)
    check("generated tiles re-encodes byte-exactly",
          tdefs.dumps() == tiles_path.read_bytes())
    ts = tdefs.tilesets[0]
    check("grid is dense", len(ts.tiles) == ts.cols * ts.rows,
          f"{ts.cols}x{ts.rows} = {len(ts.tiles)} tiles")
    check("tiles file names the sheet PNG", ts.image == "forgetest_01.png")
    defined = [t for t in ts.tiles if not t.empty]
    check("one defined tile per sprite", len(defined) == len(manifest["cells"]))
    check("preset properties applied", defined[0].props.get("IsMoveAble") == "",
          str(sorted(defined[0].props)[:6]))
    check("--prop override applied", defined[0].props.get("CustomName") == "Test Bench")
    check("multi-tile footprint records SpriteGridPos",
          defined[0].props.get("SpriteGridPos") == "0,0",
          defined[0].props.get("SpriteGridPos", "<missing>"))
    check("single facing writes no Facing property", "Facing" not in defined[0].props)
    check("text companion mentions the tileset", "file = forgetest_01" in tdefs.to_text())


def test_ids() -> None:
    print("\n== tiledef ids ==")
    taken = modgen.used_tiledef_ids()
    check("scanned installed mods for claimed ids", len(taken) > 0, f"{len(taken)} found")
    free = modgen.free_tiledef_id()
    check("chosen id is genuinely free", free not in taken, f"picked {free}")
    check("chosen id is above the reserved floor", free >= modgen.TILEDEF_ID_FLOOR)


if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp(prefix="pzforge_"))
    try:
        test_style()
        test_pipeline(tmp)
        test_ids()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'ALL PASS' if not FAILURES else 'FAILED: ' + ', '.join(FAILURES)}")
    raise SystemExit(1 if FAILURES else 0)
