import struct
import sys
from pathlib import Path

d = Path(sys.argv[1]).read_bytes()
start = int(sys.argv[2])
end = int(sys.argv[3])
print(f"file={Path(sys.argv[1]).name} size={len(d)}  window {start}..{end}")
for off in range(start, min(end, len(d)), 16):
    row = d[off:off + 16]
    hx = " ".join(f"{b:02x}" for b in row)
    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
    ints = ""
    if (off - start) % 16 == 0 and off + 16 <= len(d):
        ints = " | " + " ".join(f"{v:>10}" for v in struct.unpack_from("<4i", d, off))
    print(f"{off:6d}  {hx:<48} {asc}{ints}")
