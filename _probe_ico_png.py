# -*- coding: utf-8 -*-
"""Minimal PNG decoder (enough for our own ico entries) + ASCII preview.

Our .ico stores every size as PNG. This decodes IHDR/IDAT, undoes the 5 PNG
filters, and prints a coarse ASCII view so we can confirm the glyph is a white
mark on a near-black tile rather than a white square.
"""
import struct, zlib, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))
ICO = os.path.join(ROOT, "adb_log_gui", "adb_Tool.ico")


def png_decode(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    idat = b""
    w = h = bitd = ctype = None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, bitd, ctype = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    stride = w * ch
    rows = []
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        rows.append([tuple(line[x * ch:x * ch + ch]) for x in range(w)])
        prev = line
    return w, h, ch, rows


def main(ico=ICO):
    b = open(ico, "rb").read()
    n = struct.unpack("<H", b[4:6])[0]
    for i in range(n):
        w, h, c, r, pl, bc, sz, off = struct.unpack("<BBBBHHII", b[6 + i * 16: 22 + i * 16])
        w = w or 256
        data = b[off:off + sz]
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            print("%dx%d bmp entry, skipped" % (w, h))
            continue
        pw, ph, ch, rows = png_decode(data)
        # stats: corner colour, glyph colour, saturation
        def px(x, y):
            v = rows[y][x]
            return tuple(v[:3]) + ((v[3] if ch == 4 else 255),)
        corners = [px(1, 1), px(pw - 2, 1), px(1, ph - 2), px(pw - 2, ph - 2)]
        lum = [(r * 299 + g * 587 + bb * 114) // 1000 for r, g, bb, a in
               [px(x, y) for y in range(ph) for x in range(pw)]]
        dark = sum(1 for v in lum if v < 60)
        light = sum(1 for v in lum if v > 200)
        tot = len(lum)
        satmax = max((max(px(x, y)[:3]) - min(px(x, y)[:3])) for y in range(ph) for x in range(pw))
        print("%3dx%-3d  corner=%s  dark=%.0f%% light=%.0f%%  satmax=%d"
              % (pw, ph, corners[0][:3], 100.0 * dark / tot, 100.0 * light / tot, satmax))
        if pw == 24:
            chars = " .:-=+*#%@"
            step = 1
            print("   --- 24x24 ---")
            for y in range(0, ph, step):
                line = "".join(chars[min(9, lum[y * pw + x] * 10 // 256)] for x in range(0, pw, step))
                print("   |" + line + "|")


if __name__ == "__main__":
    main(*sys.argv[1:])
