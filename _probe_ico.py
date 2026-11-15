# -*- coding: utf-8 -*-
"""Inspect the .ico and verify which of its entries are embedded in adb_Tool.exe.

No Pillow: parse ICO/BMP manually and print a coarse ASCII preview so we can
tell "black tile with white glyph" from "white square with dark glyph".
"""
import struct, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
ICO = os.path.join(ROOT, "adb_log_gui", "adb_Tool.ico")
EXE = os.path.join(ROOT, "adb_log_gui", "dist", "adb_Tool.exe")


def parse_ico(path):
    b = open(path, "rb").read()
    if b[:4] != b"\x00\x00\x01\x00":
        raise SystemExit("not an ico: " + path)
    n = struct.unpack("<H", b[4:6])[0]
    out = []
    for i in range(n):
        w, h, c, r, pl, bc, sz, off = struct.unpack("<BBBBHHII", b[6 + i * 16: 22 + i * 16])
        out.append(dict(w=w or 256, h=h or 256, bpp=bc, size=sz,
                        off=off, data=b[off:off + sz]))
    return out


def decode_bmp(data):
    """32bpp ICO entry -> (w, h, rows of (b,g,r,a) top-down)."""
    hdr = struct.unpack("<IiiHHIIiiII", data[:40])
    w, h2, bpp = hdr[1], hdr[2], hdr[4]
    h = h2 // 2
    px_off = 40 + hdr[9] if False else 40
    rows = []
    stride = w * 4
    for y in range(h - 1, -1, -1):
        base = px_off + y * stride
        row = []
        for x in range(w):
            bl, g, r, a = data[base + x * 4: base + x * 4 + 4]
            row.append((r, g, b, a))
        rows.append(row)
    return w, h, rows


def preview(w, h, rows, cols=24):
    step = max(1, w // cols)
    chars = " .:-=+*#%@"
    lines = []
    for y in range(0, h, step * 2):
        line = ""
        for x in range(0, w, step):
            r, g, b, a = rows[y][x]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if a < 40:
                line += "."
            else:
                line += chars[min(9, lum * 10 // 256)]
        lines.append(line)
    return lines


def stats(rows):
    n = 0
    satmax = 0
    nonzero = 0
    for row in rows:
        for r, g, b, a in row:
            if a < 40:
                continue
            n += 1
            s = max(r, g, b) - min(r, g, b)
            if s > satmax:
                satmax = s
            if s > 6:
                nonzero += 1
    return n, satmax, (100.0 * nonzero / n if n else 0)


def main():
    entries = parse_ico(ICO)
    exe = open(EXE, "rb").read() if os.path.exists(EXE) else b""
    print("ico =", ICO)
    print("exe =", EXE, len(exe), "bytes\n")
    for e in entries:
        emb = exe.count(e["data"][:64]) > 0 if exe else None
        line = "  %3dx%-3d %5dB  embedded=%s" % (e["w"], e["h"], e["size"], emb)
        if e["bpp"] == 32 and e["data"][:8] != b"\x89PNG\r\n\x1a\n":
            w, h, rows = decode_bmp(e["data"])
            n, satmax, pct = stats(rows)
            line += "  satmax=%d nonGray=%.1f%%" % (satmax, pct)
        print(line)
    # ASCII preview of the 32x32 entry
    for e in entries:
        if e["w"] == 32 and e["data"][:8] != b"\x89PNG\r\n\x1a\n":
            w, h, rows = decode_bmp(e["data"])
            print("\n--- 32x32 preview (blank = transparent/dark, @ = white) ---")
            for ln in preview(w, h, rows):
                print("   |" + ln + "|")
            break


if __name__ == "__main__":
    main()
