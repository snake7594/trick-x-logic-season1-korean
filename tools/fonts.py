import os
import struct
from PIL import Image, ImageDraw

OUT = 'font_out'
os.makedirs(OUT, exist_ok=True)


def lzss(src, outsize):
    """LZ77 used by Trick x Logic .dat files.
       Control byte, MSB-first, bit 1 = literal byte.
       Match (2 bytes): len = (b0 & 0x0F) + 3,
                        dist = ((b0 >> 4) << 8) | b1,
       copied from outpos-dist; bytes before the stream start read as 0."""
    out = bytearray()
    i = 0
    while len(out) < outsize and i < len(src):
        ctrl = src[i]
        i += 1
        for bit in range(8):
            if len(out) >= outsize or i >= len(src):
                break
            if ctrl & (0x80 >> bit):
                out.append(src[i])
                i += 1
            else:
                if i + 1 >= len(src):
                    break
                b0, b1 = src[i], src[i + 1]
                i += 2
                ln = (b0 & 0x0F) + 3
                dist = ((b0 >> 4) << 8) | b1
                for _ in range(ln):
                    q = len(out) - dist
                    out.append(out[q] if 0 <= q < len(out) else 0)
                    if len(out) >= outsize:
                        break
    return bytes(out)


def load(path):
    d = open(path, 'rb').read()
    if d[:4] == b'SIR0':
        return d, 'raw'
    dec_size, comp_size = struct.unpack('<II', d[:8])
    out = lzss(d[8:8 + comp_size], dec_size)
    ok = len(out) == dec_size and out[:4] == b'SIR0'
    print(f"   LZSS {os.path.basename(path)}: want {dec_size:,} got {len(out):,} "
          f"magic={out[:4]!r} -> {'OK' if ok else 'FAIL'}")
    return out, 'lzss'


def glyphs(d):
    sub, ptr = struct.unpack('<II', d[4:12])
    cnt = struct.unpack('<I', d[sub:sub + 4])[0]
    offs = struct.unpack(f'<{cnt}I', d[sub + 8:sub + 8 + cnt * 4])
    out = []
    for i in range(cnt):
        s = offs[i]
        e = offs[i + 1] if i + 1 < cnt else sub
        rec = d[s:e]
        code = rec[0] | (rec[1] << 8)
        flag = rec[2]
        w, h, x0, y0, x1, y1 = rec[4:10]
        vw, vh = rec[10], rec[11]
        stride = (w + 1) // 2
        need = stride * h
        bmp = rec[16:16 + need]
        vert, vneed = None, 0
        if flag == 0:
            vs = (vw + 1) // 2
            vneed = vs * vh
            vert = (vw, vh, vs, rec[16 + need:16 + need + vneed])
        calc = (16 + need + vneed + 3) & ~3
        out.append(dict(i=i, code=code, flag=flag, w=w, h=h, x0=x0, y0=y0,
                        x1=x1, y1=y1, bmp=bmp, stride=stride, vert=vert,
                        reclen=len(rec), calc=calc))
    return out


def to_img(w, h, stride, bmp):
    im = Image.new('L', (max(w, 1), max(h, 1)), 0)
    px = im.load()
    for y in range(h):
        row = bmp[y * stride:(y + 1) * stride]
        for x in range(w):
            if x // 2 >= len(row):
                break
            b = row[x // 2]
            v = (b & 0x0F) if (x % 2 == 0) else (b >> 4)
            px[x, y] = v * 17
    return im


def atlas(gl, name, cols=64):
    cw = max(g['w'] for g in gl) + 2
    ch = max(g['h'] for g in gl) + 2
    rows = (len(gl) + cols - 1) // cols
    W, H = cols * cw, rows * ch

    raw = Image.new('LA', (W, H), (255, 0))
    prev = Image.new('RGB', (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(prev)
    for r in range(rows + 1):
        dr.line([(0, r * ch), (W, r * ch)], fill=(220, 220, 230))
    for c in range(cols + 1):
        dr.line([(c * cw, 0), (c * cw, H)], fill=(220, 220, 230))

    for n, g in enumerate(gl):
        if g['w'] == 0 or g['h'] == 0:
            continue
        gi = to_img(g['w'], g['h'], g['stride'], g['bmp'])
        X, Y = (n % cols) * cw + 1, (n // cols) * ch + 1
        raw.paste(Image.merge('LA', (Image.new('L', gi.size, 255), gi)), (X, Y))
        dark = Image.new('L', gi.size, 0)
        prev.paste(Image.merge('RGB', (dark, dark, dark)), (X, Y), gi)

    raw.save(f'{OUT}/{name}_atlas.png')
    prev.save(f'{OUT}/{name}_preview.png')
    print(f"   atlas {W}x{H} cell {cw}x{ch} -> {name}_atlas.png / {name}_preview.png")
    return cw, ch


FONTS = [('NovelFontList.dat', 'NovelFont'),
         ('NovelRubyFontList.dat', 'NovelRubyFont'),
         ('AdvFontList.dat', 'AdvFont')]

if __name__ != '__main__':
    FONTS = []

for fn, name in FONTS:
    print(f"=== {fn}")
    d, kind = load('out/' + fn)
    open(f'{OUT}/{name}.sir0', 'wb').write(d)
    gl = glyphs(d)
    mism = [g for g in gl if g['calc'] != g['reclen']]
    print(f"   {len(gl)} glyphs, codes 0x{min(g['code'] for g in gl):04X}"
          f"-0x{max(g['code'] for g in gl):04X}, "
          f"w {min(g['w'] for g in gl)}-{max(g['w'] for g in gl)}, "
          f"h {min(g['h'] for g in gl)}-{max(g['h'] for g in gl)}, "
          f"vertical-variant glyphs: {sum(1 for g in gl if g['flag']==0)}, "
          f"size mismatches: {len(mism)}")
    atlas(gl, name)
    print()
