"""PSP GIM 텍스처 디코더 -> RGBA (numpy 가속)."""
import struct
import numpy as np

FMT = {0: (16, 'RGBA5650'), 1: (16, 'RGBA5551'), 2: (16, 'RGBA4444'),
       3: (32, 'RGBA8888'), 4: (4, 'Index4'), 5: (8, 'Index8'),
       6: (16, 'Index16'), 7: (32, 'Index32')}


def _blocks(d):
    out = []

    def walk(off, end):
        while off + 16 <= end:
            bid, unk, bsize, nxt, doff = struct.unpack('<HHIII', d[off:off + 16])
            if bsize == 0 or bsize > len(d):
                return
            out.append((bid, off, off + doff, bsize))
            if bid in (0x02, 0x03) and nxt:
                walk(off + nxt, off + bsize)
                return
            if nxt == 0:
                return
            off += nxt
    walk(0x10, len(d))
    return out


def _hdr(d, o):
    hs, unk, fmt, tiled, w, h = struct.unpack('<HHHHHH', d[o:o + 12])
    bpp, palign, halign = struct.unpack('<HHH', d[o + 12:o + 18])
    # +0x18 = 헤더 크기, +0x1C = 픽셀 데이터 시작 오프셋(블록 데이터 기준).
    # 둘이 다르다(48 vs 64). 헤더 크기를 쓰면 16바이트 밀려 줄무늬가 생긴다.
    doff = struct.unpack('<I', d[o + 0x1C:o + 0x20])[0] if hs >= 0x20 else hs
    if not (0 < doff < 0x1000):
        doff = hs
    return dict(hdr=hs, data=doff, fmt=fmt, tiled=tiled, w=w, h=h,
                bpp=bpp, palign=palign or 1, halign=halign or 1)


def _unswizzle(buf, wbytes, h):
    """PSP swizzle 해제: 16x8 바이트 블록 단위."""
    bh = (h + 7) // 8
    bw = max(wbytes // 16, 1)
    need = bw * bh * 128
    if len(buf) < need:
        buf = buf + b'\0' * (need - len(buf))
    a = np.frombuffer(buf[:need], dtype=np.uint8).reshape(bh, bw, 8, 16)
    a = a.transpose(0, 2, 1, 3).reshape(bh * 8, bw * 16)
    return a[:h, :wbytes]


def _pal_rgba(fmt, v):
    v = v.astype(np.uint32)
    if fmt == 0:
        r = (v & 31) * 255 // 31
        g = ((v >> 5) & 63) * 255 // 63
        b = ((v >> 11) & 31) * 255 // 31
        a = np.full_like(r, 255)
    elif fmt == 1:
        r = (v & 31) * 255 // 31
        g = ((v >> 5) & 31) * 255 // 31
        b = ((v >> 10) & 31) * 255 // 31
        a = np.where((v >> 15) & 1, 255, 0)
    elif fmt == 2:
        r = (v & 15) * 17
        g = ((v >> 4) & 15) * 17
        b = ((v >> 8) & 15) * 17
        a = ((v >> 12) & 15) * 17
    else:
        r = v & 255
        g = (v >> 8) & 255
        b = (v >> 16) & 255
        a = (v >> 24) & 255
    return np.stack([r, g, b, a], axis=-1).astype(np.uint8)


def decode(d):
    """-> (w, h, RGBA ndarray[h,w,4]) 또는 None"""
    if d[:11] != b'MIG.00.1PSP':
        return None
    blks = _blocks(d)
    img = next((b for b in blks if b[0] == 0x04), None)
    if not img:
        return None
    _, _, doff, bsize = img
    ih = _hdr(d, doff)
    w, h, fmt = ih['w'], ih['h'], ih['fmt']
    if fmt not in FMT or w == 0 or h == 0 or w > 4096 or h > 4096:
        return None
    bpp = FMT[fmt][0]

    palette = None
    pal = next((b for b in blks if b[0] == 0x05), None)
    if pal:
        ph = _hdr(d, pal[2])
        praw = d[pal[2] + ph['data']:]
        n = ph['w'] or 256
        step = 4 if ph['fmt'] == 3 else 2
        n = min(n, len(praw) // step)
        if n:
            dt = np.uint32 if step == 4 else np.uint16
            vals = np.frombuffer(praw[:n * step], dtype=dt)
            palette = _pal_rgba(ph['fmt'], vals)

    raw = d[doff + ih['data']:doff + bsize]
    wbytes = max(w * bpp // 8, 1)
    # 저장은 pitch(16바이트)·height(8행) 정렬 기준. 무시하면 행이 밀려 줄무늬가 생긴다.
    pa, ha = ih['palign'], ih['halign']
    pitch = -(-wbytes // pa) * pa
    hh = -(-h // ha) * ha
    if ih['tiled']:
        plane = _unswizzle(raw, pitch, hh)
    else:
        need = pitch * hh
        raw = raw + b'\0' * max(0, need - len(raw))
        plane = np.frombuffer(raw[:need], dtype=np.uint8).reshape(hh, pitch)
    plane = plane[:h, :wbytes]          # 정렬 패딩 제거

    if bpp == 4:
        lo = plane & 15
        hi = plane >> 4
        idx = np.empty((h, wbytes * 2), dtype=np.uint8)
        idx[:, 0::2] = lo
        idx[:, 1::2] = hi
        idx = idx[:, :w]
        out = (palette[idx] if palette is not None
               else np.stack([idx * 17] * 3 + [np.full_like(idx, 255)], -1))
    elif bpp == 8:
        idx = plane[:, :w]
        out = (palette[idx] if palette is not None
               else np.stack([idx] * 3 + [np.full_like(idx, 255)], -1))
    elif bpp == 16:
        v = plane.view(np.uint16)[:, :w]
        if fmt == 6 and palette is not None:
            out = palette[np.clip(v, 0, len(palette) - 1)]
        else:
            out = _pal_rgba(fmt, v)
    else:
        v = plane.view(np.uint32)[:, :w]
        out = _pal_rgba(3, v)
    return w, h, out.astype(np.uint8)


def info(d):
    if d[:11] != b'MIG.00.1PSP':
        return None
    img = next((b for b in _blocks(d) if b[0] == 0x04), None)
    if not img:
        return None
    ih = _hdr(d, img[2])
    return dict(w=ih['w'], h=ih['h'], fmt=FMT.get(ih['fmt'], (0, '?'))[1],
                tiled=ih['tiled'])
