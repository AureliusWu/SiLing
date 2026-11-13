"""Write a deterministic Windows ICO using the standard library."""

import struct
from pathlib import Path

size = 32
pixels = bytearray()
for y in range(size - 1, -1, -1):
    for x in range(size):
        inside = (x - 15.5) ** 2 + (y - 15.5) ** 2 < 220
        pixels.extend((87, 115, 42, 255) if inside else (0, 0, 0, 0))
mask = bytes(((size + 31) // 32) * 4 * size)
bitmap = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0)
bitmap += bytes(pixels) + mask
icon = struct.pack("<HHH", 0, 1, 1)
icon += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(bitmap), 22) + bitmap
target = Path("apps/desktop/src-tauri/icons/icon.ico")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(icon)
