"""조서 이름표: 한 글자가 한 칸인 스프라이트 격자를 읽어낸다.

칸(글자) → 열 → 이름 순으로 묶어서 좌표를 돌려준다.
"""
import numpy as np
from scipy import ndimage
import detect


def cells(px, thr=145, minpx=60):
    """개별 글자 칸 [(x0,y0,x1,y1)]."""
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    m = (px[..., 3] > 100) & (lum <= thr)
    lab, _ = ndimage.label(ndimage.binary_dilation(m, np.ones((3, 3), bool)),
                           np.ones((3, 3), bool))
    out = []
    for y, x in ndimage.find_objects(lab):
        blk = m[y, x]
        h, w = y.stop - y.start, x.stop - x.start
        if blk.sum() < 34 or w < 8 or h < 4 or w > 42 or h > 42:
            continue
        xs = np.where(blk.any(0))[0]
        ys = np.where(blk.any(1))[0]
        out.append([x.start + int(xs[0]), y.start + int(ys[0]),
                    x.start + int(xs[-1]) + 1, y.start + int(ys[-1]) + 1])
    # 같은 글자가 조각나면 합친다 (겹치거나 4px 이내)
    out.sort(key=lambda b: (b[0] // 20, b[1]))
    merged = []
    for b in out:
        hit = None
        for a in merged:
            if (min(a[2], b[2]) - max(a[0], b[0]) > -5 and
                    min(a[3], b[3]) - max(a[1], b[1]) > -5):
                hit = a
                break
        if hit:
            hit[0], hit[1] = min(hit[0], b[0]), min(hit[1], b[1])
            hit[2], hit[3] = max(hit[2], b[2]), max(hit[3], b[3])
        else:
            merged.append(b)
    return merged


def groups(cs, xtol=14, ygap=35):
    """열별로 묶고, 세로 간격이 크면 다른 이름으로 나눈다."""
    cols = {}
    for b in cs:
        cx = (b[0] + b[2]) // 2
        key = next((k for k in cols if abs(k - cx) <= xtol), cx)
        cols.setdefault(key, []).append(b)
    out = []
    for key in sorted(cols, reverse=True):          # 오른쪽 열부터
        col = sorted(cols[key], key=lambda b: b[1])
        cur = [col[0]]
        for b in col[1:]:
            if b[1] - cur[-1][3] > ygap:
                out.append((key, cur))
                cur = [b]
            else:
                cur.append(b)
        out.append((key, cur))
    # 짧은 덩어리가 가까이 이어지면 한 이름으로 본다(가운데 글자가 안 잡힌 경우)
    merged = []
    for key, g in out:
        if merged and merged[-1][0] == key:
            pk, pg = merged[-1]
            ph = pg[-1][3] - pg[0][1]
            if ph < 100 and g[0][1] - pg[-1][3] < 90:
                merged[-1] = (pk, pg + g)
                continue
        merged.append((key, g))
    return merged


def split(name, k):
    """한글 이름을 칸 수 k 로 나눈다. 앞 칸부터 한 음절씩 더 준다."""
    t = name.replace(' ', '')
    n = len(t)
    sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
    out, i = [], 0
    for s in sizes:
        out.append(t[i:i + s])
        i += s
    return out


if __name__ == '__main__':
    import sys
    for n in sys.argv[1:]:
        px = detect.load(n)
        cs = cells(px)
        print("=====", n, px.shape[1], 'x', px.shape[0], "칸", len(cs))
        for key, g in groups(cs):
            box = [min(b[0] for b in g), g[0][1],
                   max(b[2] for b in g), g[-1][3]]
            print(f"  열x{key:<4} 칸{len(g)}  전체 x{box[0]}..{box[2]} "
                  f"y{box[1]}..{box[3]}   " +
                  ' / '.join(f"({b[0]},{b[1]},{b[2]},{b[3]})" for b in g))
