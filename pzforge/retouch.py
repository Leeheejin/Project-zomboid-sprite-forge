"""Layered export for the hand-retouch round trip.

Every pipeline that reaches vanilla quality ends the same way -- Factorio's
sprites go through Photoshop masks, Project Zomboid's own tiles are painted-over
renders -- so the last mile is a first-class stage here, not an afterthought.
The build can write a retouch folder holding, per cell:

* ``<cell>.png``          -- the styled sprite, THE file the artist edits
* ``<cell>.ora``          -- the same plus every underlay, as OpenRaster layers
                             (Krita and GIMP open it natively)
* ``layers/<cell>/*.png`` -- the underlays as loose files for any other editor:
                             beauty render, light pass, recovered paint,
                             element id map, normal pass, vanilla reference

plus the copied ``manifest.json``, so the folder is itself a valid cells
directory: after editing, package it verbatim with

    pzforge build <retouch dir> --mod-id <Mod> --no-style

The one hard rule is printed into the folder's README: **never change the alpha
channel** -- the trimmed sprite offsets the game uses are derived from it, and a
changed silhouette shifts the tile in game.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from PIL import Image


def _linear(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _srgb(v: float) -> float:
    if v <= 0.0031308:
        return 12.92 * v
    return 1.055 * (v ** (1 / 2.4)) - 0.055


_L8 = [_linear(i / 255.0) for i in range(256)]


def recover_paint(beauty: Image.Image, light: Image.Image) -> Image.Image:
    """albedo = beauty / light, the artist's flat-colour underlay."""
    beauty = beauty.convert("RGBA")
    light = light.convert("RGBA")
    out = []
    for b, l in zip(beauty.getdata(), light.getdata()):
        if b[3] == 0:
            out.append((0, 0, 0, 0))
            continue
        px = []
        for c in range(3):
            lv = max(_L8[l[c]], 1e-4)
            px.append(min(255, round(_srgb(min(1.0, _L8[b[c]] / lv)) * 255)))
        out.append((*px, b[3]))
    img = Image.new("RGBA", beauty.size)
    img.putdata(out)
    return img


def _write_ora(path: Path, layers: list[tuple[str, Image.Image]]) -> None:
    """Minimal OpenRaster writer: first layer in ``layers`` is topmost."""
    w = max(img.width for _n, img in layers)
    h = max(img.height for _n, img in layers)
    entries = "\n".join(
        f'    <layer name="{name}" src="data/{k}.png" x="0" y="0" '
        f'opacity="1.0" visibility="visible"/>'
        for k, (name, _img) in enumerate(layers))
    stack = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<image w="{w}" h="{h}" version="0.0.3">\n  <stack>\n'
             f'{entries}\n  </stack>\n</image>\n')
    merged = layers[0][1].convert("RGBA")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("mimetype", "image/openraster")
        z.writestr("stack.xml", stack)
        for k, (_name, img) in enumerate(layers):
            from io import BytesIO
            buf = BytesIO()
            img.convert("RGBA").save(buf, "PNG")
            z.writestr(f"data/{k}.png", buf.getvalue())
        from io import BytesIO
        buf = BytesIO()
        merged.save(buf, "PNG")
        z.writestr("mergedimage.png", buf.getvalue())
        thumb = merged.copy()
        thumb.thumbnail((256, 256))
        buf = BytesIO()
        thumb.save(buf, "PNG")
        z.writestr("Thumbnails/thumbnail.png", buf.getvalue())


README = """PZ Sprite Forge -- 덧칠(리터치) 폴더
=====================================

이 폴더의 최상위 <셀이름>.png 가 편집 대상입니다 (스타일 패스까지 끝난 결과).
같은 이름의 .ora 를 Krita/GIMP로 열면 아래 참고 레이어가 함께 열립니다:

  retouch  (빈 레이어 -- 여기에 덧칠한 뒤 병합해도 됩니다)
  styled   (현재 결과물)
  vanilla  (레퍼런스 스프라이트 -- 목표 스타일)
  paint    (광원을 나눠 복원한 순수 페인트색)
  light    (리그의 광원장)
  beauty   (원시 렌더)
  elements (부품별 ID 색 -- 영역 선택용)
  normal   (면 방향 -- 파란색이 강할수록 윗면)

규칙 하나: **알파(실루엣)는 절대 바꾸지 마세요.** 게임이 쓰는 트림 오프셋이
알파에서 나오므로, 실루엣이 변하면 인게임에서 타일이 밀립니다.

편집을 마치면 이 폴더째로 패키징합니다:

    uv run --python 3.12 --with pillow python -m pzforge.cli build <이 폴더> \\
        --mod-id <모드ID> --no-style
"""


def write_export(out_dir: Path, cells_dir: Path, manifest: dict,
                 entries: list[dict]) -> None:
    """Write the retouch folder. ``entries``: per-cell dicts with keys
    ``name`` (cell filename), ``styled`` (PIL image), and optional PIL images
    ``beauty``, ``light``, ``normal``, ``elements``, ``vanilla``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    import json
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "README.txt").write_text(README, encoding="utf-8")

    for e in entries:
        name = e["name"]
        stem = name[:-4] if name.endswith(".png") else name
        styled = e["styled"]
        styled.save(out_dir / name)

        layer_dir = out_dir / "layers" / stem
        layer_dir.mkdir(parents=True, exist_ok=True)
        layers = [("retouch", Image.new("RGBA", styled.size, (0, 0, 0, 0))),
                  ("styled", styled)]
        for key in ("vanilla", "beauty", "light", "elements", "normal"):
            img = e.get(key)
            if img is not None:
                img = img.convert("RGBA")
                img.save(layer_dir / f"{key}.png")
                layers.append((key, img))
        if e.get("beauty") is not None and e.get("light") is not None:
            paint = recover_paint(e["beauty"], e["light"])
            paint.save(layer_dir / "paint.png")
            layers.insert(3, ("paint", paint))
        _write_ora(out_dir / f"{stem}.ora", layers)
