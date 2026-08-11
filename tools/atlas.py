"""UI 아틀라스(512x512 등)의 일본어 글자 상자를 찾아 한글로 바꾼다.

글자는 대체로 '어두운 잉크'이고 배경은 투명하거나 밝은 버튼이다.
행 → 행 안의 덩어리 순서로 상자를 매기고, 그 번호에 한글을 붙인다.
"""
import paths
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import inpaint

FONT = paths.TTF


def ink(px, lum_max=120, a_min=100):
    """어두운 글자 화소."""
    a = px[..., 3]
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    return (a >= a_min) & (lum <= lum_max)


def ink_light(px, lum_min=168, a_min=100):
    """어두운 판 위의 밝은 글자 화소."""
    a = px[..., 3]
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    return (a >= a_min) & (lum >= lum_min)


def mask(px, kind='dark'):
    if kind.startswith('light'):
        return ink_light(px)
    if kind.startswith('local'):
        return ink(px) | ink_light(px)
    return ink(px)


def local_ink(px, box):
    """상자 안에서만 밝기로 글자를 가른다(버튼처럼 대비가 낮은 자리용).

    (글자마스크, 글자색, 외곽선색) — 외곽선이 없으면 색은 None."""
    x0, y0, x1, y1 = box
    sub = px[y0:y1, x0:x1]
    lum = sub[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    op = sub[..., 3] > 100
    if op.sum() < 20:
        return np.zeros(px.shape[:2], bool), (255, 255, 255), None
    v = lum[op]
    # 글자는 상자 안에서 '적은 쪽'이다 — 흰 말풍선의 검은 글자도 이걸로 가른다
    bright_n = int((v >= v.max() - 45).sum())
    dark_n = int((v <= v.min() + 45).sum())
    if dark_n < bright_n:                       # 밝은 바탕 위 어두운 글자
        thr = min(np.percentile(v, 32), v.min() + 55)
        ink_sel = (lum <= thr) & op
        other = (lum >= np.percentile(v, 82)) & op
    else:                                       # 어두운 바탕 위 밝은 글자
        thr = max(np.percentile(v, 68), v.max() - 55)
        ink_sel = (lum >= thr) & op
        other = (lum <= np.percentile(v, 18)) & op
    lm = np.zeros(px.shape[:2], bool)
    lm[y0:y1, x0:x1] = ink_sel
    col = (np.median(px[..., :3][lm], axis=0) if lm.any()
           else np.array([255.] * 3))
    st = None
    if v.max() - v.min() > 70 and other.sum() > 0.15 * max(int(ink_sel.sum()), 1):
        st = tuple(int(c) for c in np.median(sub[..., :3][other], axis=0))
    return lm, tuple(int(c) for c in col), st


def build_all(px, spec):
    """spec 이 dict 면 어두운 가로 글자만.

    리스트면 [(종류, 번역표), ...] — 종류는 dark/light, 뒤에 '-v' 를 붙이면
    세로쓰기."""
    if isinstance(spec, dict):
        spec = [('dark', spec)]
    orig, plans = px, []
    for kind, mp in spec:                 # 상자 번호는 반드시 '원본'에서 매긴다
        m = mask(orig, kind)
        vert = kind.endswith('-v')
        bs = (None if kind.startswith('local')
              else (boxes_v(orig, m) if vert else boxes(orig, m)))
        plans.append((kind, mp, m, vert, bs))
    for kind, mp, m, vert, bs in plans:
        if kind.startswith('local'):
            px = build_local(px, mp, m, vert)
        else:
            px = build(px, mp, m=m, bs=bs, vert=vert)
    return px


def build_local(px, mapping, m, vert):
    """좌표를 직접 준 상자만 처리한다. 글자색은 상자 안 대비로 정한다."""
    px = px.copy()
    jobs = []
    for _, t in mapping.items():
        box = (t[1], t[3], t[2], t[4])   # (x0,x1,y0,y1) -> (x0,y0,x1,y1)
        lm, col, st = local_ink(px, box)
        jobs.append((box, t[0], col, st))
    for box, t, col, st in jobs:
        px = (erase_box_v if vert else erase_box)(px, box, m)
    for box, t, col, st in jobs:
        if vert:
            px = draw_v(px, box, t, col, stroke=st)
        else:
            px = draw(px, box, t, col, align='center', stroke=st)
    return px


def boxes(px, m=None, join=4, minpx=40, minw=10, minh=8, maxh=30):
    """글자 덩어리 [(x0,y0,x1,y1)] — 위 행부터, 행 안에서는 왼쪽부터.

    글자를 가로로 이어 붙여(join) 연결 요소를 잡고, 같은 줄에서 가까운
    덩어리끼리 다시 합친다."""
    from scipy import ndimage
    if m is None:
        m = ink(px)
    d = ndimage.binary_dilation(m, np.ones((1, join * 2 + 1), bool))
    lab, n = ndimage.label(d, np.ones((3, 3), bool))
    cand = []
    for y, x in ndimage.find_objects(lab):
        blk = m[y, x]
        h, w = y.stop - y.start, x.stop - x.start
        if blk.sum() < minpx or w < minw or h < minh or h > maxh:
            continue
        xs = np.where(blk.any(0))[0]
        ys = np.where(blk.any(1))[0]
        cand.append([x.start + int(xs[0]), y.start + int(ys[0]),
                     x.start + int(xs[-1]) + 1, y.start + int(ys[-1]) + 1])
    cand.sort(key=lambda b: (b[1] // 8, b[0]))
    out = []
    for b in cand:
        if out:
            a = out[-1]
            same = (min(a[3], b[3]) - max(a[1], b[1])) > 0.6 * min(
                a[3] - a[1], b[3] - b[1])
            if same and 0 <= b[0] - a[2] <= 14:
                a[0], a[1] = min(a[0], b[0]), min(a[1], b[1])
                a[2], a[3] = max(a[2], b[2]), max(a[3], b[3])
                continue
        out.append(b)
    out.sort(key=lambda b: (b[1], b[0]))
    return [tuple(b) for b in out]


def boxes_v(px, m=None, join=5, minpx=40, minw=8, minh=14, maxw=44):
    """세로쓰기 글자 덩어리. 세로로 이어 붙여 연결 요소를 잡는다."""
    from scipy import ndimage
    if m is None:
        m = ink(px)
    d = ndimage.binary_dilation(m, np.ones((join * 2 + 1, 1), bool))
    lab, _ = ndimage.label(d, np.ones((3, 3), bool))
    cand = []
    for y, x in ndimage.find_objects(lab):
        blk = m[y, x]
        h, w = y.stop - y.start, x.stop - x.start
        if blk.sum() < minpx or w < minw or w > maxw or h < minh:
            continue
        xs = np.where(blk.any(0))[0]
        ys = np.where(blk.any(1))[0]
        cand.append([x.start + int(xs[0]), y.start + int(ys[0]),
                     x.start + int(xs[-1]) + 1, y.start + int(ys[-1]) + 1])
    cand.sort(key=lambda b: (b[0] // 8, b[1]))
    out = []
    for b in cand:
        if out:
            a = out[-1]
            same = (min(a[2], b[2]) - max(a[0], b[0])) > 0.6 * min(
                a[2] - a[0], b[2] - b[0])
            if same and 0 <= b[1] - a[3] <= 14:
                a[0], a[1] = min(a[0], b[0]), min(a[1], b[1])
                a[2], a[3] = max(a[2], b[2]), max(a[3], b[3])
                continue
        out.append(b)
    out.sort(key=lambda b: (-b[0], b[1]))
    return [tuple(b) for b in out]


def erase_box_v(px, box, m, pad=1):
    """세로쓰기 상자를 지운다. 배경색은 가로 한 줄씩 따로 구한다."""
    h, w = px.shape[:2]
    x0 = max(0, box[0] - pad)
    y0 = max(0, box[1] - pad)
    x1 = min(w, box[2] + pad)
    y1 = min(h, box[3] + pad)
    cs = ([c for c in range(max(0, x0 - 3), x0)] +
          [c for c in range(x1, min(w, x1 + 3))])     # 글자 열 좌우만 표본
    if not cs:
        px[y0:y1, x0:x1] = 0
        return px
    ring = px[y0:y1, cs].astype(np.int16)
    both = inpaint._dilate(ink(px) | ink_light(px), 1)[y0:y1, cs]
    rows = np.zeros((y1 - y0, 4), np.int16)
    for i in range(y1 - y0):
        k = ~both[i]
        rows[i] = np.median(ring[i][k] if k.sum() >= 2 else ring[i], axis=0)
    rows[rows[:, 3] < 40] = 0
    px[y0:y1, x0:x1] = rows[:, None, :].astype(np.uint8)
    return px


def draw_v(px, box, text, color, grow=None, minsize=8, stroke=None):
    """상자에 세로쓰기. 공백은 반 칸. grow 는 아래로 늘릴 수 있는 한계 y."""
    x0, y0, x1, y1 = box
    cw = x1 - x0
    slots = [0.45 if c == ' ' else 1.0 for c in text]
    total = sum(slots)
    hmax = (grow if grow else y1) - y0
    size = max(minsize, int(min(cw, hmax / total)))
    f = ImageFont.truetype(FONT, size)
    used = size * total
    cy = y0 + max(0.0, ((y1 - y0) - used) / 2)
    cx = (x0 + x1) / 2
    im = Image.fromarray(px, 'RGBA')
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    for c, s in zip(text, slots):
        if c != ' ':
            b = f.getbbox(c)
            kw = ({} if stroke is None
                  else {'stroke_width': max(1, round(size / 14)),
                        'stroke_fill': tuple(int(v) for v in stroke) + (255,)})
            dr.text((cx - (b[0] + b[2]) / 2, cy + (size - (b[1] + b[3])) / 2),
                    c, font=f, fill=tuple(int(v) for v in color) + (255,), **kw)
        cy += size * s
    im.alpha_composite(lay)
    return np.asarray(im).copy()


def debug(px, bs, path, scale=2):
    im = Image.fromarray(px, 'RGBA')
    bg = Image.new('RGBA', im.size, (252, 252, 250, 255))
    im = Image.alpha_composite(bg, im).convert('RGB')
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    dr = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 11 * scale // 2 + 4)
    for i, (x0, y0, x1, y1) in enumerate(bs):
        dr.rectangle([x0 * scale, y0 * scale, x1 * scale - 1, y1 * scale - 1],
                     outline=(230, 30, 30))
        dr.text((x0 * scale + 1, y0 * scale - 12), str(i),
                fill=(0, 110, 230), font=f)
    im.save(path)


def _bg_color(px, box, m):
    """상자 주변 배경색(글자가 아닌 화소의 중앙값). 투명하면 None."""
    x0, y0, x1, y1 = box
    p = 3
    sy = slice(max(0, y0 - p), min(px.shape[0], y1 + p))
    sx = slice(max(0, x0 - p), min(px.shape[1], x1 + p))
    sub = px[sy, sx]
    sm = m[sy, sx]
    keep = (~sm) & (sub[..., 3] > 200)
    if keep.sum() < 12:
        return None
    return np.median(sub[..., :3][keep], axis=0).astype(np.uint8)


def erase_box(px, box, m, pad=1):
    """상자를 통째로 지운다.

    배경색은 세로 한 줄씩 따로 구한다(가로 그라데이션·형광 띠 보존).
    글자가 아닌 화소가 없는 열은 옆 열 색을 가져다 쓴다."""
    h, w = px.shape[:2]
    x0 = max(0, box[0] - pad)
    y0 = max(0, box[1] - pad)
    x1 = min(w, box[2] + pad)
    y1 = min(h, box[3] + pad)
    rows = ([r for r in range(max(0, y0 - 3), y0)] +
            [r for r in range(y1, min(h, y1 + 3))])   # 글자 줄 위아래만 표본
    if not rows:
        px[y0:y1, x0:x1] = 0
        return px
    ring = px[rows, x0:x1].astype(np.int16)
    both = inpaint._dilate(ink(px) | ink_light(px), 1)[rows, x0:x1]
    cols = np.zeros((x1 - x0, 4), np.int16)
    for i in range(x1 - x0):
        k = ~both[:, i]
        cols[i] = np.median(ring[:, i][k] if k.sum() >= 2 else ring[:, i],
                            axis=0)                   # 표본이 없으면 그대로
    cols[cols[:, 3] < 40] = 0
    px[y0:y1, x0:x1] = cols[None, :, :].astype(np.uint8)
    return px


def _stroke(px, box, m, color):
    """글자 안쪽에 반대 색이 충분히 있으면 (외곽선색, 두께비) 를 돌려준다."""
    x0, y0, x1, y1 = box
    other = ink_light(px) if _is_dark(color) else ink(px)
    o = other[y0:y1, x0:x1] & ~m[y0:y1, x0:x1]
    n = m[y0:y1, x0:x1].sum()
    if n == 0 or o.sum() < 0.30 * n:
        return None
    c = px[y0:y1, x0:x1, :3][o]
    return tuple(int(v) for v in np.median(c, axis=0))


def _is_dark(color):
    return (color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114) < 128


def draw(px, box, text, color, grow=None, align='left', minsize=8,
         stroke=None):
    """상자 왼쪽(또는 가운데)에 맞춰 한 줄 한글을 그린다.

    글자 크기는 원본 글자 높이에서 시작하고, 폭이 grow 를 넘으면 줄인다."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    wmax = (grow if grow else x1) - x0
    size, b = minsize, None
    for s in range(h + 3, minsize - 1, -1):
        f = ImageFont.truetype(FONT, s)
        bb = f.getbbox(text)
        if (bb[2] - bb[0]) <= wmax and (bb[3] - bb[1]) <= h + 2:
            size, b = s, bb
            break
    f = ImageFont.truetype(FONT, size)
    if b is None:
        b = f.getbbox(text)
    im = Image.fromarray(px, 'RGBA')
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    tx = (x0 - b[0] if align == 'left'
          else x0 + ((x1 - x0) - (b[2] - b[0])) / 2 - b[0])
    ty = y0 + (h - (b[3] - b[1])) / 2 - b[1]
    kw = ({} if stroke is None
          else {'stroke_width': max(1, round(size / 14)),
                'stroke_fill': tuple(int(c) for c in stroke) + (255,)})
    dr.text((tx, ty), text, font=f,
            fill=tuple(int(c) for c in color) + (255,), **kw)
    im.alpha_composite(lay)
    return np.asarray(im).copy()


def _grow_limit(box, bs, width):
    """같은 줄에서 오른쪽에 있는 다른 상자 앞까지 늘릴 수 있다."""
    lim = width - 4
    for o in bs:
        if o[0] <= box[0]:
            continue
        if (min(o[3], box[3]) - max(o[1], box[1])) > 0.5 * (box[3] - box[1]):
            lim = min(lim, o[0] - 6)
    return max(lim, box[2])


def gaps(m, box, mingap=5):
    """상자 안의 빈 열 구간 — 아이콘과 글자가 붙어 잡혔을 때 자를 위치."""
    x0, y0, x1, y1 = box
    col = m[y0:y1, x0:x1].sum(0)
    out, s = [], None
    for i in range(len(col) + 1):
        z = i < len(col) and col[i] == 0
        if z and s is None:
            s = i
        elif not z and s is not None:
            if i - s >= mingap:
                out.append((x0 + s, x0 + i))
            s = None
    return out


def report(px, path):
    """상자 목록과 내부 빈칸을 찍고 확인용 그림을 남긴다."""
    m = ink(px)
    bs = boxes(px, m)
    for i, b in enumerate(bs):
        g = gaps(m, b)
        gs = ('  틈 ' + ' '.join(f'{a}-{c}' for a, c in g)) if g else ''
        print(f"{i:>3} x{b[0]:>3}..{b[2]:>3} y{b[1]:>3}..{b[3]:>3} "
              f"{b[2]-b[0]:>3}x{b[3]-b[1]:>2}{gs}")
    debug(px, bs, path)
    return m, bs


def _list(px, kind, tag):
    m = mask(px, kind)
    bs = boxes(px, m)
    for i, b in enumerate(bs):
        g = gaps(m, b)
        gs = ('  틈 ' + ' '.join(f'{a}-{c}' for a, c in g)) if g else ''
        print(f"{tag}{i:<3} x{b[0]:>3}..{b[2]:>3} y{b[1]:>3}..{b[3]:>3} "
              f"{b[2]-b[0]:>3}x{b[3]-b[1]:>2}{gs}")
    return bs


def report2(items, path, scale=2, bgc=(150, 150, 155)):
    """여러 장을 가로로 이어 붙여 어두운(d)·밝은(L) 글자 상자를 함께 표시.

    items: [(이름, px)]"""
    ims, all_bs = [], []
    for name, px in items:
        print("=====", name)
        d = _list(px, 'dark', 'd')
        L = _list(px, 'light', 'L')
        all_bs.append((d, L))
        im = Image.fromarray(px, 'RGBA')
        bg = Image.new('RGBA', im.size, bgc + (255,))
        ims.append(Image.alpha_composite(bg, im).convert('RGB'))
    W = sum(i.width for i in ims) + 8 * (len(ims) - 1)
    H = max(i.height for i in ims)
    sh = Image.new('RGB', (W * scale, H * scale + 16), (25, 25, 30))
    dr = ImageDraw.Draw(sh)
    f = ImageFont.truetype(FONT, 12)
    ox = 0
    for (name, _), im, (d, L) in zip(items, ims, all_bs):
        sh.paste(im.resize((im.width * scale, im.height * scale),
                           Image.LANCZOS), (ox * scale, 16))
        dr.text((ox * scale + 2, 2), name, fill=(255, 235, 110), font=f)
        for tag, bs, col in (('d', d, (230, 30, 30)), ('L', L, (30, 120, 255))):
            for i, (x0, y0, x1, y1) in enumerate(bs):
                dr.rectangle([(ox + x0) * scale, y0 * scale + 16,
                              (ox + x1) * scale - 1, y1 * scale + 15],
                             outline=col)
                dr.text(((ox + x0) * scale + 1, y0 * scale + 5),
                        f"{tag}{i}", fill=col, font=f)
        ox += im.width + 8
    sh.save(path)


def wrap(text, font, width):
    """폭에 맞춰 줄바꿈. 공백이 없으면 글자 단위로 자른다."""
    lines, cur = [], ''
    for w in text.split(' '):
        t = (cur + ' ' + w) if cur else w
        if font.getbbox(t)[2] - font.getbbox(t)[0] <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:                       # 한 낱말이 너무 길면 강제로 자른다
        while font.getbbox(ln)[2] - font.getbbox(ln)[0] > width and len(ln) > 1:
            k = len(ln)
            while k > 1 and font.getbbox(ln[:k])[2] - \
                    font.getbbox(ln[:k])[0] > width:
                k -= 1
            out.append(ln[:k])
            ln = ln[k:]
        out.append(ln)
    return out


def build_para(px, bxs, text, m, color, x0=None):
    """여러 줄짜리 문단을 지우고 한글로 다시 흘려 넣는다."""
    x0 = x0 if x0 is not None else min(b[0] for b in bxs)
    x1 = max(b[2] for b in bxs)
    y0 = min(b[1] for b in bxs)
    hs = [b[3] - b[1] for b in bxs]
    lh = int(np.median(hs))
    pitch = (bxs[1][1] - bxs[0][1]) if len(bxs) > 1 else lh + 11
    for b in bxs:
        px = erase_box(px, b, m)
    size = min(lh + 2, max(10, int(pitch * 0.62)))
    f = ImageFont.truetype(FONT, size)
    lines = wrap(text, f, x1 - x0)
    while len(lines) > len(bxs) and size > 9:
        size -= 1
        f = ImageFont.truetype(FONT, size)
        lines = wrap(text, f, x1 - x0)
    im = Image.fromarray(px, 'RGBA')
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    for i, ln in enumerate(lines):
        b = f.getbbox(ln)
        dr.text((x0 - b[0], y0 + i * pitch + (lh - (b[3] - b[1])) / 2 - b[1]),
                ln, font=f, fill=tuple(int(c) for c in color) + (255,))
    im.alpha_composite(lay)
    return np.asarray(im).copy()


def build(px, mapping, m=None, bs=None, vert=False):
    """mapping: {상자번호: '한글' | ('한글', x0[, x1[, y0[, y1]]])}.

    상자번호가 None 이면 좌표를 모두 지정한 새 상자로 본다."""
    px = px.copy()
    if m is None:
        m = ink(px)
    if bs is None:
        bs = boxes(px, m)
    jobs, paras = [], []
    for i, t in mapping.items():
        if isinstance(i, tuple):                    # 여러 줄 문단
            bxs = [bs[k] for k in i]
            px0 = None
            if isinstance(t, tuple):
                t, px0 = t[0], t[1]
            col = px[bxs[0][1]:bxs[0][3], bxs[0][0]:bxs[0][2], :3][
                m[bxs[0][1]:bxs[0][3], bxs[0][0]:bxs[0][2]]]
            paras.append((bxs, t,
                          np.median(col, axis=0) if len(col)
                          else np.array([32, 26, 22]), px0))
            continue
        box = list(bs[i]) if isinstance(i, int) else [0, 0, 0, 0]
        exact = False
        if isinstance(t, tuple):
            exact = len(t) == 5 and all(v is not None for v in t[1:])
            for k, j in enumerate((0, 2, 1, 3)):
                if len(t) > k + 1 and t[k + 1] is not None:
                    box[j] = t[k + 1]
            t = t[0]
        sub = m[box[1]:box[3], box[0]:box[2]]      # 지정 영역 안 실제 글자로 조임
        if sub.any() and not exact:
            ys = np.where(sub.any(1))[0]
            xs = np.where(sub.any(0))[0]
            box = [box[0] + int(xs[0]), box[1] + int(ys[0]),
                   box[0] + int(xs[-1]) + 1, box[1] + int(ys[-1]) + 1]
        box = tuple(box)
        sub = m[box[1]:box[3], box[0]:box[2]]
        col = px[box[1]:box[3], box[0]:box[2], :3][sub]
        col = np.median(col, axis=0) if len(col) else np.array([32, 26, 22])
        btn = _bg_color(px, box, m) is not None
        jobs.append((box, t, col, btn, _stroke(px, box, m, col)))
    for bxs, t, col, px0 in paras:
        px = build_para(px, bxs, t, m, col, px0)
    for box, t, col, btn, st in jobs:
        px = (erase_box_v if vert else erase_box)(px, box, m)
    for box, t, col, btn, st in jobs:
        if vert:
            px = draw_v(px, box, t, col, stroke=st)
        elif btn:
            px = draw(px, box, t, col, align='center', stroke=st)
        else:
            px = draw(px, box, t, col, stroke=st,
                      grow=_grow_limit(box, bs, px.shape[1]), align='left')
    return px


def build_note(px, text, region, cols, size, color=None, thr=110):
    """세로쓰기 한 페이지(도입 안내문)를 통째로 다시 짠다.

    region: (x0,y0,x1,y1) 글자 영역, cols: [열 중심 x] 오른쪽부터,
    size: 글자 크기."""
    x0, y0, x1, y1 = region
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    m = np.zeros(px.shape[:2], bool)
    m[y0:y1, x0:x1] = lum[y0:y1, x0:x1] >= thr
    if color is None:
        c = px[..., :3][inpaint._dilate(m, 0)]
        color = tuple(int(v) for v in np.percentile(c, 75, axis=0))
    m = inpaint._dilate(m, 2)
    filled = inpaint.fill(px, m)
    out = px.copy()
    out[..., :3] = filled.astype(np.uint8)

    per = int((y1 - y0) / size)
    f = ImageFont.truetype(FONT, size)
    im = Image.fromarray(out, 'RGBA')
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(lay)
    ci, y, i = 0, float(y0), 0
    while i < len(text) and ci < len(cols):
        ch = text[i]
        i += 1
        if ch == ' ':
            if y > y0:
                y += size * 0.45
        else:
            b = f.getbbox(ch)
            dr.text((cols[ci] - (b[0] + b[2]) / 2, y + (size - (b[1] + b[3])) / 2),
                    ch, font=f, fill=tuple(color) + (255,))
            y += size
        if y + size > y1:
            ci += 1
            y = float(y0)
    im.alpha_composite(lay)
    return np.asarray(im).copy(), (len(text) - i)
