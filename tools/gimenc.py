"""RGBA 이미지를 원본 GIM 구조 그대로 다시 써 넣는 인코더.

원본 팔레트를 그대로 재사용하고 픽셀만 교체하므로 색 문제가 없다.
크기·포맷·블록 구조는 원본과 동일하게 유지한다.
"""
import struct
import numpy as np
import gim


def _swizzle(plane, pitch, hh):
    """unswizzle 의 역연산 (16x8 바이트 블록)."""
    bw, bh = max(pitch // 16, 1), max(hh // 8, 1)
    a = plane[:bh * 8, :bw * 16].reshape(bh, 8, bw, 16)
    return a.transpose(0, 2, 1, 3).reshape(-1)


def encode(orig_gim, rgba):
    """원본 GIM 바이트 + 새 RGBA(ndarray h,w,4) -> 새 GIM 바이트."""
    d = bytearray(orig_gim)
    blks = gim._blocks(bytes(d))
    img = next(b for b in blks if b[0] == 0x04)
    pal = next((b for b in blks if b[0] == 0x05), None)
    ih = gim._hdr(bytes(d), img[2])
    w, h, fmt = ih['w'], ih['h'], ih['fmt']
    if fmt != 5:
        raise ValueError(f'지원하지 않는 포맷 {fmt} (Index8 만 지원)')
    if rgba.shape[0] != h or rgba.shape[1] != w:
        raise ValueError(f'크기 불일치 {rgba.shape[1]}x{rgba.shape[0]} != {w}x{h}')
    if pal is None:
        raise ValueError('팔레트 블록 없음')

    # 원본 팔레트 (RGBA8888 256색)
    ph = gim._hdr(bytes(d), pal[2])
    pstart = pal[2] + ph['data']
    step = 4 if ph['fmt'] == 3 else 2
    n = min(ph['w'] or 256, (pal[2] + pal[3] - pstart) // step)
    dt = np.uint32 if step == 4 else np.uint16
    vals = np.frombuffer(bytes(d[pstart:pstart + n * step]), dtype=dt)
    palette = gim._pal_rgba(ph['fmt'], vals).astype(np.int16)   # (n,4)

    # 각 픽셀을 팔레트에서 가장 가까운 색으로 (알파 포함 가중)
    px = rgba.astype(np.int16).reshape(-1, 4)
    idx = np.empty(px.shape[0], dtype=np.uint8)
    CH = 65536
    W = np.array([1, 1, 1, 2], dtype=np.int32)      # 알파를 조금 더 중시
    for s in range(0, px.shape[0], CH):
        blk = px[s:s + CH]
        diff = (blk[:, None, :].astype(np.int32) -
                palette[None, :, :].astype(np.int32))
        dist = ((diff * diff) * W).sum(axis=2)
        idx[s:s + CH] = np.argmin(dist, axis=1).astype(np.uint8)
    plane = idx.reshape(h, w)

    # pitch/height 정렬 + swizzle
    wb = w * ih['bpp'] // 8
    pitch = -(-wb // ih['palign']) * ih['palign']
    hh = -(-h // ih['halign']) * ih['halign']
    buf = np.zeros((hh, pitch), dtype=np.uint8)
    buf[:h, :wb] = plane
    body = (_swizzle(buf, pitch, hh).tobytes() if ih['tiled']
            else buf.tobytes())

    start = img[2] + ih['data']
    end = img[2] + img[3]
    room = end - start
    if len(body) > room:
        raise ValueError(f'데이터가 원본보다 큼 {len(body)} > {room}')
    d[start:start + len(body)] = body
    return bytes(d)
