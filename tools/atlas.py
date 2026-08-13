"""UI 아틀라스(512x512 등)의 일본어 글자 상자를 찾아 한글로 바꾼다.

글자는 대체로 '어두운 잉크'이고 배경은 투명하거나 밝은 버튼이다.
행 → 행 안의 덩어리 순서로 상자를 매기고, 그 번호에 한글을 붙인다.
"""
import paths
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
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
    if kind.startswith(('local', 'clear', 'photo')):
        return ink(px) | ink_light(px)
    return ink(px)


def _ring_lum(px, box, ring=4):
    """상자 바로 바깥 테두리의 밝기 중앙값 — 정의상 '바탕'이다."""
    h, w = px.shape[:2]
    x0, y0, x1, y1 = box
    a0, b0 = max(0, x0 - ring), max(0, y0 - ring)
    a1, b1 = min(w, x1 + ring), min(h, y1 + ring)
    sel = np.zeros((h, w), bool)
    sel[b0:b1, a0:a1] = True
    sel[y0:y1, x0:x1] = False
    sel &= px[..., 3] > 100
    if sel.sum() < 12:
        return None
    return float(np.median(px[..., :3][sel].astype(np.float32)
                           @ [0.299, 0.587, 0.114]))


def local_ink(px, box, ring=4, by_ring=False):
    """상자 안에서만 밝기로 글자를 가른다(버튼처럼 대비가 낮은 자리용).

    (글자마스크, 글자색, 외곽선색, 둘레마스크).

    둘레마스크는 **상자 안에서 정한 같은 기준**을 상자 둘레 ring px 까지
    적용한 것이다. 지울 때 배경색 표본을 고르는 데 쓴다. 전역 기준(`ink`)은
    '어두우면 글자'로 보기 때문에, 어두운 판 위 중간톤 글자에서는 판까지
    글자로 몰아 배경 표본이 하나도 안 남고 결국 투명·검정으로 칠해진다."""
    x0, y0, x1, y1 = box
    sub = px[y0:y1, x0:x1]
    lum = sub[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    op = sub[..., 3] > 100
    if op.sum() < 20:
        z = np.zeros(px.shape[:2], bool)
        return z, (255, 255, 255), None, z
    v = lum[op]
    # 글자는 상자 안에서 '적은 쪽'이다 — 흰 말풍선의 검은 글자도 이걸로 가른다
    bright_n = int((v >= v.max() - 45).sum())
    dark_n = int((v <= v.min() + 45).sum())
    dark_text = dark_n < bright_n
    if by_ring:
        # 상자가 글자에 딱 붙는 도면 라벨은 위 규칙이 뒤집힌다 — 흰 획이
        # 상자를 가득 채워 '많은 쪽'이 돼 버린다(厨房 이 흰 판이 됐다).
        # 둘레는 정의상 바탕이므로, 밝은 쪽과 어두운 쪽 중 **둘레에서 더 먼**
        # 쪽을 글자로 본다. 판 위 흰 글자(車で1時間)도 이걸로 맞는다.
        rb = _ring_lum(px, box)
        if rb is not None:
            hi, lo = np.percentile(v, 90), np.percentile(v, 10)
            dark_text = abs(lo - rb) > abs(hi - rb)
    if dark_text:                               # 밝은 바탕 위 어두운 글자
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

    h, w = px.shape[:2]
    ex0, ey0 = max(0, x0 - ring), max(0, y0 - ring)
    ex1, ey1 = min(w, x1 + ring), min(h, y1 + ring)
    el = px[ey0:ey1, ex0:ex1, :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    eop = px[ey0:ey1, ex0:ex1, 3] > 100
    ring_m = np.zeros(px.shape[:2], bool)
    ring_m[ey0:ey1, ex0:ex1] = ((el <= thr) if dark_text
                                else (el >= thr)) & eop
    return lm, tuple(int(c) for c in col), st, ring_m


def build_all(px, spec):
    """spec 이 dict 면 어두운 가로 글자만.

    리스트면 [(종류, 번역표), ...] — 종류는 dark/light/local/clear, 뒤에
    '-v' 를 붙이면 세로쓰기."""
    if isinstance(spec, dict):
        spec = [('dark', spec)]
    orig, plans = px, []
    for kind, mp in spec:                 # 상자 번호는 반드시 '원본'에서 매긴다
        m = mask(orig, kind)
        vert = kind.endswith('-v')
        bs = (None if kind.startswith(('local', 'clear', 'photo'))
              else (boxes_v(orig, m) if vert else boxes(orig, m)))
        plans.append((kind, mp, m, vert, bs))
    for kind, mp, m, vert, bs in plans:
        if kind.startswith('photo'):
            px = build_photo(px, mp, vert)
        elif kind.startswith('clear'):
            px = build_clear(px, mp, vert)
        elif kind.startswith('local'):
            px = build_local(px, mp, m, vert)
        else:
            px = build(px, mp, m=m, bs=bs, vert=vert)
    return px


def build_photo(px, mapping, vert, grow=1):
    """**사진 위에 구워진 글자**용 (`tutorial_figure_03`).

    `erase_box_v` 는 한 줄을 배경색 하나로 칠한다. 사진 위에서는 그 줄이
    통째로 납작해져 세로 줄무늬가 남는다. 여기서는 `inpaint.fill` 로 상자
    **바깥 색을 흘려 넣는다** — 번지긴 해도 어차피 그 자리에 글자를 다시
    그리므로 티가 안 난다.

    글자 획만 골라 지우는 방법은 안 된다. 이 사진은 밝기가 0~255 로 널려
    있어 흰 획(밝기 225)과 밝은 벽이 안 갈린다 — 획 조각이 얼룩으로 남았다.

    글줄이 원본보다 짧아지면 **위에서부터** 그린다. `draw_v` 는 상자 가운데
    맞춤이라, 지우는 상자를 그대로 쓰면 문단이 아래로 처져 보인다."""
    px = px.copy()
    jobs = [((t[1], t[3], t[2], t[4]), t[0]) for t in mapping.values()]
    mask = np.zeros(px.shape[:2], bool)
    for (x0, y0, x1, y1), _ in jobs:
        mask[y0:y1, x0:x1] = True
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    hi = lum[mask] >= np.percentile(lum[mask], 92)
    lo = lum[mask] <= np.percentile(lum[mask], 8)
    col = np.median(px[..., :3][mask][hi], axis=0)
    st = tuple(int(c) for c in np.median(px[..., :3][mask][lo], axis=0))
    px[..., :3] = inpaint.fill(px[..., :3].copy(),
                               inpaint._dilate(mask, grow), iters=200)
    for (x0, y0, x1, y1), t in jobs:
        if vert:                       # 필요한 만큼만 위에서 잘라 쓴다
            cw = x1 - x0
            need = round(cw * sum(0.45 if c == ' ' else 1.0 for c in t))
            y1 = min(y1, y0 + need)
        px = (draw_v if vert else draw)(px, (x0, y0, x1, y1), t, col, stroke=st)
    return px


def build_clear(px, mapping, vert, pad=3):
    """바탕이 **완전 투명**한 그림(스태프롤)용.

    이런 그림에는 지울 배경색이랄 게 없다. `erase_box_v` 는 상자 좌우 3px
    를 배경 표본으로 삼는데, 여기서는 그 자리가 글자 그늘(검정·알파 10~30)
    이라 상자가 통째로 뿌옇게 칠해진다. 그래서 그냥 **투명하게 비운다**.

    원본 획은 흰색이 아니라 연회색(183)에 검은 테가 둘러져 있고, 그 바깥에
    알파 10 안팎의 검은 번짐이 넓게 깔려 있다. 같은 모양으로 다시 그린다."""
    px = px.copy()
    op = px[..., 3] > 200
    col = (np.median(px[..., :3][op], axis=0) if op.any()
           else np.array([255.] * 3))
    jobs = [((t[1], t[3], t[2], t[4]), t[0]) for t in mapping.values()]
    h, w = px.shape[:2]
    for (x0, y0, x1, y1), _ in jobs:
        sub = px[max(0, y0 - pad):min(h, y1 + pad),
                 max(0, x0 - pad):min(w, x1 + pad)]
        sub[..., :3] = 255
        sub[..., 3] = 0
    for box, t in jobs:
        px = (draw_v if vert else draw)(px, box, t, col,
                                        stroke=(0, 0, 0), glow=2)
    return px


def build_local(px, mapping, m, vert):
    """좌표를 직접 준 상자만 처리한다. 글자색은 상자 안 대비로 정한다."""
    px = px.copy()
    jobs = []
    for _, t in mapping.items():
        box = (t[1], t[3], t[2], t[4])   # (x0,x1,y0,y1) -> (x0,y0,x1,y1)
        # 6번째 자리에 'ring' 을 적으면 글자·바탕 판정과 배경색을 모두
        # **상자 둘레 기준**으로 구한다.
        force = len(t) > 5 and t[5] == 'ring'
        lm, col, st, ring_m = local_ink(px, box, by_ring=force)
        jobs.append((box, t[0], col, st, ring_m, force))
    for box, t, col, st, ring_m, force in jobs:
        px = (erase_box_v if vert else erase_box)(px, box, m, excl=ring_m,
                                                  force=force)
    for box, t, col, st, ring_m, force in jobs:
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


def _inside_bg(px, x0, y0, x1, y1, both):
    """상자 안의 '글자가 아닌 불투명 화소' 중앙값. 없으면 None.

    스프라이트가 빽빽하게 붙어 있어 상자 둘레가 통째로 투명한 자리에서
    쓰는 마지막 수단이다. 이게 없으면 이름표 바탕이 검게 칠해진다.

    **상자가 통째로 불투명할 때만** 쓴다(이름표·판). 투명 위에 글자만 있는
    스프라이트에 적용하면 안티에일리어싱 가장자리 색으로 상자를 채워
    회색 네모가 생긴다."""
    a = px[y0:y1, x0:x1, 3]
    area = max(a.size, 1)
    op = a >= 40
    k = (~both[y0:y1, x0:x1]) & op
    if op.sum() < 0.97 * area or k.sum() < max(4, 0.25 * area):
        return None
    return np.median(px[y0:y1, x0:x1].astype(np.int16)[k], axis=0)


def _pick(src, bt, n, opaque_only=True):
    """줄마다 '글자가 아닌 화소' 중앙값. (값, 구했는지)

    opaque_only 면 불투명 화소만 표본으로 쓴다. 끄면 예전 규칙 그대로 —
    투명 화소까지 넣으므로 둘레가 투명한 자리는 통째로 투명해진다(투명 위에
    글자만 있는 스프라이트에서는 그게 맞다)."""
    out = np.zeros((n, 4), np.int16)
    ok = np.zeros(n, bool)
    for i in range(n):
        line = src[i] if src.ndim == 3 and src.shape[0] == n else src[:, i]
        b = bt[i] if bt.ndim == 2 and bt.shape[0] == n else bt[:, i]
        k = (~b) & (line[:, 3] >= 40) if opaque_only else ~b
        if k.sum() >= 2:
            out[i] = np.median(line[k], axis=0)
            ok[i] = True
        elif not opaque_only:
            out[i] = np.median(line, axis=0)
            ok[i] = True
    return out, ok


def _bg_lines(ring, both, n, fallback, inner=None, inner_both=None,
              opaque_only=True):
    """줄(열)마다 배경색을 정한다 — **불투명 화소만** 표본으로 쓴다.

    ① 상자 **안쪽**의 글자 사이 배경 ② 상자 둘레 ③ 가장 가까운 채워진 줄
    ④ 상자 전체 배경 ⑤ 투명 순으로 고른다.

    안쪽을 먼저 보는 이유: 둘레에는 칸을 나누는 줄이나 테두리가 섞여 있어
    그 색이 그대로 사각형으로 남는다. 예전에는 투명 화소까지 중앙값에 넣어
    둘레가 투명한 버튼은 바탕이 아예 검게 변했다."""
    out, ok = (_pick(inner, inner_both, n) if inner is not None
               else (np.zeros((n, 4), np.int16), np.zeros(n, bool)))
    ro, rok = _pick(ring, both, n, opaque_only)
    use = rok & ~ok
    out[use], ok[use] = ro[use], True
    if ok.any():
        idx = np.where(ok)[0]
        for i in np.where(~ok)[0]:
            out[i] = out[idx[np.argmin(np.abs(idx - i))]]
    elif fallback is not None:
        out[:] = fallback
    out[out[:, 3] < 40] = 0
    return out


def _repair(px, x0, y0, x1, y1, lines, excl, vert, force=False):
    """예전 규칙이 판을 투명·검정으로 칠했을 때만 다시 계산한다.

    상자가 통째로 불투명한 '판'(이름표·버튼)인데 결과가 투명하거나 판보다
    한참 어두우면 배경 표본을 잘못 고른 것이다. 이때만 상자 안쪽·둘레의
    **불투명 화소**로 다시 구한다. 그 밖의 자리는 한 화소도 건드리지 않는다.

    force 는 지도에서 그 상자 하나에만 켜는 표시다. 어두운 바탕(도면의 갈색 방)
    위 흰 글자에 후광이 두꺼우면 전역 기준이 바탕까지 글자로 몰아, 남는 표본이
    후광뿐이라 상자가 흰 판으로 칠해진다(西森修治). 밝기로 자동 판정하게
    넓혔더니 낭독 화면 제목에 회색 띠가 생겨서, **손으로 지정하는 쪽**을 골랐다."""
    a = px[y0:y1, x0:x1, 3]
    if excl is None:
        return None
    if force:
        # 2px 로 부풀린다. 1px 로는 획의 안티에일리어싱 가장자리가 남아
        # 그 중간톤이 배경 표본으로 뽑히고, 열 하나가 통째로 어둡게 칠해져
        # 세로 막대가 생긴다(臙脂色の絨毯 앞의 「‖」).
        return inpaint._dilate(excl, 2)
    if (a >= 40).mean() < 0.97:
        return None
    ref = np.median(px[y0:y1, x0:x1, :3][a >= 40], axis=0) @ [0.299, .587, .114]
    lum = lines[:, :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    if not ((lines[:, 3] < 40) | (lum + 40 < ref)).any():
        return None
    return inpaint._dilate(excl, 1)


def erase_box_v(px, box, m, pad=1, excl=None, force=False):
    """세로쓰기 상자를 지운다. 배경색은 가로 한 줄씩 따로 구한다."""
    h, w = px.shape[:2]
    x0 = max(0, box[0] - pad)
    y0 = max(0, box[1] - pad)
    x1 = min(w, box[2] + pad)
    y1 = min(h, box[3] + pad)
    glob = inpaint._dilate(ink(px) | ink_light(px), 1)
    cs = ([c for c in range(max(0, x0 - 3), x0)] +
          [c for c in range(x1, min(w, x1 + 3))])     # 글자 열 좌우만 표본
    if not cs:
        px[y0:y1, x0:x1] = 0
        return px
    ring = px[y0:y1, cs].astype(np.int16)
    rows = _bg_lines(ring, glob[y0:y1, cs], y1 - y0, None, opaque_only=False)
    ex = _repair(px, x0, y0, x1, y1, rows, excl, True, force)
    if ex is not None:
        fb = _inside_bg(px, x0, y0, x1, y1, ex)
        rows = _bg_lines(px[y0:y1, cs].astype(np.int16), ex[y0:y1, cs],
                         y1 - y0, fb, px[y0:y1, x0:x1].astype(np.int16),
                         ex[y0:y1, x0:x1])
    px[y0:y1, x0:x1] = rows[:, None, :].astype(np.uint8)
    return px


def draw_v(px, box, text, color, grow=None, minsize=8, stroke=None, glow=0):
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
    if glow:                      # 원본처럼 글자 뒤에 옅게 번지는 검은 그늘
        g = lay.split()[3].filter(ImageFilter.GaussianBlur(glow))
        sh = Image.new('RGBA', im.size, (0, 0, 0, 0))
        sh.putalpha(g.point(lambda v: int(v * 0.45)))
        im.alpha_composite(sh)
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


def erase_box(px, box, m, pad=1, excl=None, force=False):
    """상자를 통째로 지운다.

    배경색은 세로 한 줄씩 따로 구한다(가로 그라데이션·형광 띠 보존).
    글자가 아닌 화소가 없는 열은 옆 열 색을 가져다 쓴다."""
    h, w = px.shape[:2]
    x0 = max(0, box[0] - pad)
    y0 = max(0, box[1] - pad)
    x1 = min(w, box[2] + pad)
    y1 = min(h, box[3] + pad)
    glob = inpaint._dilate(ink(px) | ink_light(px), 1)
    rs = ([r for r in range(max(0, y0 - 3), y0)] +
          [r for r in range(y1, min(h, y1 + 3))])     # 글자 줄 위아래만 표본
    if not rs:
        px[y0:y1, x0:x1] = 0
        return px
    ring = px[rs, x0:x1].astype(np.int16)
    cols = _bg_lines(ring, glob[rs, x0:x1], x1 - x0, None, opaque_only=False)
    ex = _repair(px, x0, y0, x1, y1, cols, excl, False, force)
    if ex is not None:
        fb = _inside_bg(px, x0, y0, x1, y1, ex)
        cols = _bg_lines(px[rs, x0:x1].astype(np.int16), ex[rs, x0:x1],
                         x1 - x0, fb, px[y0:y1, x0:x1].astype(np.int16),
                         ex[y0:y1, x0:x1])
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


def build_note(px, text, region, cols, size, color=None, thr=110,
               wipe=(), marks=()):
    """세로쓰기 한 페이지(도입 안내문)를 통째로 다시 짠다.

    region: (x0,y0,x1,y1) 글자 영역, cols: [열 중심 x] 오른쪽부터,
    size: 글자 크기.
    wipe:  글자 영역 **밖**을 통째로 지울 사각형들. 한자 읽기(루비)와
           분홍 글자 뒤의 번진 빛은 밝기 기준으로는 안 지워져 그대로 남는다.
    marks: [(부분문자열, (r,g,b))] — 원문에서 분홍색이던 낱말을 같은 색으로,
           뒤에 흐린 빛까지 얹어 그린다."""
    x0, y0, x1, y1 = region
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    m = np.zeros(px.shape[:2], bool)
    m[y0:y1, x0:x1] = lum[y0:y1, x0:x1] >= thr
    if color is None:
        c = px[..., :3][inpaint._dilate(m, 0)]
        color = tuple(int(v) for v in np.percentile(c, 75, axis=0))
    m = inpaint._dilate(m, 2)
    for wx0, wy0, wx1, wy1 in wipe:
        m[wy0:wy1, wx0:wx1] = True
    filled = inpaint.fill(px, m)
    out = px.copy()
    out[..., :3] = filled.astype(np.uint8)

    hi = {}
    for sub, col in marks:
        j = text.find(sub)
        while j >= 0:
            for t in range(j, j + len(sub)):
                hi[t] = col
            j = text.find(sub, j + 1)

    f = ImageFont.truetype(FONT, size)
    im = Image.fromarray(out, 'RGBA')
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
    glow = Image.new('RGBA', im.size, (0, 0, 0, 0))
    dr, dg = ImageDraw.Draw(lay), ImageDraw.Draw(glow)
    ci, y, i = 0, float(y0), 0
    while i < len(text) and ci < len(cols):
        ch = text[i]
        col = hi.get(i, color)
        i += 1
        if ch == ' ':
            if y > y0:
                y += size * 0.45
        else:
            b = f.getbbox(ch)
            pos = (cols[ci] - (b[0] + b[2]) / 2,
                   y + (size - (b[1] + b[3])) / 2)
            # 글자는 늘 본문 색(흰색)으로 그리고, **뒤에 깔리는 빛만** 분홍이다.
            # 글자까지 분홍으로 칠했더니 분홍 덩어리로 뭉개져 안 읽혔다.
            dr.text(pos, ch, font=f, fill=tuple(color) + (255,))
            if col is not color:
                dg.text(pos, ch, font=f, fill=tuple(col) + (255,),
                        stroke_width=3, stroke_fill=tuple(col) + (255,))
            y += size
        if y + size > y1:
            ci += 1
            y = float(y0)
    if hi:
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(3)))
    im.alpha_composite(lay)
    return np.asarray(im).copy(), (len(text) - i)
