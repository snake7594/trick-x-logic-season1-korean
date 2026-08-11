"""불투명 배경 위에 그려진 밝은 글자를 지우고 배경을 메운다.

챕터 타이틀(`*_bg_title`)처럼 알파 채널이 없는 이미지용.
글자는 배경(어두운 회갈색)·핏자국(어두운 붉은색)보다 훨씬 밝으므로
밝기로 골라내고, 주변 색을 확산시켜 메운 뒤 고주파 질감을 되살린다.
"""
import numpy as np


def _dilate(m, r=1):
    o = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            o |= np.roll(np.roll(m, dy, 0), dx, 1)
    return o


def text_mask(px, thr=120, grow=2):
    """밝기 thr 이상인 화소를 글자로 본다."""
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    return _dilate(lum >= thr, grow)


def fill(px, mask, iters=60):
    """mask 영역을 주변 색의 확산으로 메운다."""
    img = px[..., :3].astype(np.float32)
    known = (~mask).astype(np.float32)
    acc = img * known[..., None]
    for _ in range(iters):
        if known.min() > 0:
            break
        na = acc.copy()
        nk = known.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            w = 1.0 if dy == 0 or dx == 0 else 0.5
            na += w * np.roll(np.roll(acc, dy, 0), dx, 1)
            nk += w * np.roll(np.roll(known, dy, 0), dx, 1)
        upd = (known == 0) & (nk > 0)
        acc[upd] = na[upd] / nk[upd][..., None]
        known[upd] = 1.0
    out = img.copy()
    out[mask] = acc[mask]
    return out


def retexture(orig, filled, mask, shift=(0, 96)):
    """메운 영역이 매끈해 보이지 않도록 다른 위치의 고주파 질감을 얹는다."""
    src = np.roll(np.roll(orig[..., :3].astype(np.float32),
                          shift[0], 0), shift[1], 1)
    smask = _dilate(text_mask(np.roll(np.roll(orig, shift[0], 0), shift[1], 1),
                              120, 2), 1)
    lo = src.copy()
    for _ in range(3):                       # 3x3 박스 블러 3회 ≈ 저주파
        s = lo.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s += np.roll(np.roll(lo, dy, 0), dx, 1)
        lo = s / 5.0
    hi = np.clip(src - lo, -18, 18)
    hi[smask] = 0                            # 원본 글자가 있던 자리는 질감 제외
    out = filled.copy()
    out[mask] += hi[mask]
    return np.clip(out, 0, 255)


def erase(px, thr=120, grow=2):
    """글자를 지운 RGBA 배열과 글자 마스크를 돌려준다."""
    m = text_mask(px, thr, grow)
    f = fill(px, m)
    f = retexture(px, f, m)
    out = px.copy()
    out[..., :3] = f.astype(np.uint8)
    return out, m


def _bands(proj, gap):
    out, s, run = [], None, 0
    for i in range(len(proj) + 1):
        on = i < len(proj) and proj[i] > 0
        if on:
            if s is None:
                s = i
            run = 0
        elif s is not None:
            run += 1
            if run > gap or i == len(proj):
                out.append((s, i - run + 1))
                s = None
    return out


def runs(mask, xgap=6, ygap=9, minpx=120, minh=18):
    """세로쓰기 글자 덩어리를 열 → 덩어리로 나눈다.

    [(x0,y0,x1,y1)] — 오른쪽 열부터, 열 안에서는 위부터."""
    out = []
    for x0, x1 in _bands(mask.sum(0), xgap):
        sub = mask[:, x0:x1]
        for y0, y1 in _bands(sub.sum(1), ygap):
            blk = sub[y0:y1]
            if blk.sum() < minpx or (y1 - y0) < minh:
                continue
            xs = np.where(blk.any(0))[0]
            out.append((x0 + int(xs[0]), y0, x0 + int(xs[-1]) + 1, y1))
    out.sort(key=lambda b: (-b[0], b[1]))
    return out


def ink(px, mask, box):
    """글자 색 = 상자 안 글자 화소 중 밝은 쪽 평균."""
    x0, y0, x1, y1 = box
    m = mask[y0:y1, x0:x1]
    c = px[y0:y1, x0:x1, :3][m].astype(np.float32)
    if len(c) == 0:
        return (255, 245, 230)
    lum = c @ [0.299, 0.587, 0.114]
    sel = c[lum >= np.percentile(lum, 70)]
    return tuple(int(v) for v in sel.mean(0))
