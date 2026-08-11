"""이미지 속 텍스트를 한글로 다시 그린다 (대사와 같은 SeoulHangangEB).

투명 배경 + 텍스트 구조인 이미지는 텍스트만 지우고 새로 그리면 된다.
원본 텍스트의 색·굵기·위치를 그대로 따라간다.
"""
import paths
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TTF = paths.TTF


def text_bbox(a, thr=64):
    """불투명 픽셀의 경계 상자."""
    al = a[:, :, 3]
    ys, xs = np.nonzero(al > thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def main_colors(a, thr=200):
    """텍스트 본체 색과 테두리 색을 추정한다."""
    al = a[:, :, 3]
    px = a[al > thr][:, :3]
    if len(px) == 0:
        return (255, 255, 255), None
    cols, cnt = np.unique(px.reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(-cnt)
    fill = tuple(int(v) for v in cols[order[0]])
    outline = None
    # 밝기가 가장 다른 색을 테두리 후보로
    if len(order) > 1:
        lum = cols.astype(np.int32).sum(axis=1)
        f = int(np.array(fill, dtype=np.int32).sum())
        k = int(np.argmax(np.abs(lum - f) * (cnt > cnt.max() * 0.05)))
        if abs(int(lum[k]) - f) > 180:
            outline = tuple(int(v) for v in cols[k])
    return fill, outline


def fit_font(text, box_w, box_h, max_size=None):
    """상자에 들어가는 가장 큰 폰트 크기."""
    hi = max_size or box_h + 8
    for size in range(hi, 5, -1):
        f = ImageFont.truetype(TTF, size)
        l, t, r, b = f.getbbox(text)
        if (r - l) <= box_w and (b - t) <= box_h:
            return f, (r - l), (b - t), l, t
    f = ImageFont.truetype(TTF, 6)
    l, t, r, b = f.getbbox(text)
    return f, (r - l), (b - t), l, t


def render(orig_rgba, text, align='center', pad=1):
    """원본과 같은 크기의 RGBA 를 만들어 한글 텍스트를 그린다."""
    h, w = orig_rgba.shape[:2]
    bb = text_bbox(orig_rgba)
    fill, outline = main_colors(orig_rgba)
    if bb is None:
        bx0, by0, bx1, by1 = 0, 0, w, h
    else:
        bx0, by0, bx1, by1 = bb
    bw = max(bx1 - bx0, 8)
    bh = max(by1 - by0, 8)

    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    f, tw, th, lx, ty = fit_font(text, bw, bh)
    if align == 'center':
        x = bx0 + (bw - tw) // 2 - lx
    elif align == 'right':
        x = bx1 - tw - lx
    else:
        x = bx0 - lx
    y = by0 + (bh - th) // 2 - ty
    if outline:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    dr.text((x + dx, y + dy), text, font=f,
                            fill=outline + (255,))
    dr.text((x, y), text, font=f, fill=fill + (255,))
    return np.asarray(im)


def text_rows(a, thr=64, gap=4):
    """불투명 픽셀의 수평 투영으로 텍스트 '행' 구간을 나눈다."""
    al = a[:, :, 3]
    rows = (al > thr).sum(axis=1)
    on = rows > max(1, rows.max() * 0.02)
    out, s = [], None
    for y, v in enumerate(on):
        if v and s is None:
            s = y
        elif not v and s is not None:
            out.append((s, y))
            s = None
    if s is not None:
        out.append((s, len(on)))
    # 간격이 좁은 구간은 합친다
    merged = []
    for r in out:
        if merged and r[0] - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(list(r) if False else (r[0], r[1]))
    return [r for r in merged if r[1] - r[0] >= 4]


def render_rows(orig_rgba, texts, align='center'):
    """행별로 나눠 그린다. texts 는 행 수와 같은 길이의 리스트."""
    h, w = orig_rgba.shape[:2]
    rows = text_rows(orig_rgba)
    if not rows:
        return render(orig_rgba, ' '.join(t for t in texts if t))
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    n = min(len(rows), len(texts))
    for i in range(n):
        y0, y1 = rows[i]
        band = orig_rgba[y0:y1]
        t = texts[i]
        if not t:
            continue
        bb = text_bbox(band)
        if bb is None:
            continue
        bx0, _, bx1, _ = bb
        fill, outline = main_colors(band)
        bw, bh = max(bx1 - bx0, 8), max(y1 - y0, 8)
        f, tw, th, lx, ty = fit_font(t, bw, bh)
        if align == 'center':
            x = bx0 + (bw - tw) // 2 - lx
        else:
            x = bx0 - lx
        y = y0 + (bh - th) // 2 - ty
        if outline:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        dr.text((x + dx, y + dy), t, font=f,
                                fill=outline + (255,))
        dr.text((x, y), t, font=f, fill=fill + (255,))
    return np.asarray(im)


def render_vertical(orig_rgba, text):
    """세로쓰기 이미지용 (한 글자씩 세로로)."""
    h, w = orig_rgba.shape[:2]
    bb = text_bbox(orig_rgba)
    fill, outline = main_colors(orig_rgba)
    bx0, by0, bx1, by1 = bb if bb else (0, 0, w, h)
    bw, bh = max(bx1 - bx0, 8), max(by1 - by0, 8)
    n = max(len(text), 1)
    cell = bh // n
    size = min(bw, cell)
    f = ImageFont.truetype(TTF, max(size, 6))
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for i, ch in enumerate(text):
        l, t, r, b = f.getbbox(ch)
        x = bx0 + (bw - (r - l)) // 2 - l
        y = by0 + i * cell + (cell - (b - t)) // 2 - t
        if outline:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        dr.text((x + dx, y + dy), ch, font=f,
                                fill=outline + (255,))
        dr.text((x, y), ch, font=f, fill=fill + (255,))
    return np.asarray(im)
