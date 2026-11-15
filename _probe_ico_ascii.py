# -*- coding: utf-8 -*-
"""Print ASCII previews of our .ico at several sizes to judge small-size legibility."""
import struct, zlib, sys

ICO = r"C:\Users\李亦\Desktop\Adb_Tool\adb_log_gui\adb_Tool.ico"

def png_decode(data):
    pos = 8; idat = b""; w=h=bitd=ctype=None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos+4])[0]
        typ = data[pos+4:pos+8]; chunk = data[pos+8:pos+8+ln]; pos += 12+ln
        if typ == b"IHDR": w,h,bitd,ctype = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT": idat += chunk
        elif typ == b"IEND": break
    raw = zlib.decompress(idat); ch = {0:1,2:3,4:2,6:4}[ctype]
    stride = w*ch; rows=[]; prev=bytearray(stride); p=0
    for y in range(h):
        f=raw[p]; p+=1; line=bytearray(raw[p:p+stride]); p+=stride
        if f==1:
            for i in range(ch,stride): line[i]=(line[i]+line[i-ch])&255
        elif f==2:
            for i in range(stride): line[i]=(line[i]+prev[i])&255
        elif f==3:
            for i in range(stride):
                a=line[i-ch] if i>=ch else 0; line[i]=(line[i]+((a+prev[i])>>1))&255
        elif f==4:
            for i in range(stride):
                a=line[i-ch] if i>=ch else 0; b=prev[i]; c=prev[i-ch] if i>=ch else 0
                pa,pb,pc=abs(b-c),abs(a-c),abs(a+b-2*c)
                pr=a if (pa<=pb and pa<=pc) else (b if pb<=pc else c)
                line[i]=(line[i]+pr)&255
        rows.append([tuple(line[x*ch:x*ch+ch]) for x in range(w)]); prev=line
    return w,h,ch,rows

def main():
    b=open(ICO,'rb').read(); n=struct.unpack('<H',b[4:6])[0]
    entries={}
    for i in range(n):
        w,h,c,r,pl,bc,sz,off=struct.unpack('<BBBBHHII',b[6+i*16:22+i*16])
        w=w or 256
        entries[w]=b[off:off+sz]
    chars=" .:-=+*#%@"
    for size in (16,24,32,48,64):
        w,h,ch,rows=png_decode(entries[size])
        print("\n=== %d x %d ===" % (w,h))
        # print every pixel, 2 rows of text per icon row to keep aspect ~square
        for y in range(h):
            line=""
            for x in range(w):
                r,g,bb,a = rows[y][x] + ((255,) if ch==3 else ())
                lum=(r*299+g*587+bb*114)//1000
                if a<60: line+=" "
                else: line+=chars[min(9,lum*10//256)]
            print(line)

main()
