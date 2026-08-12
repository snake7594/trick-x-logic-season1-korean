"""대충 찍은 영역을 그 안 글자에 딱 맞게 좁힌다.

도면 라벨은 절반이 판 없이 지도 위에 얇게 얹혀 있어 전역 임계값으로는
안 잡힌다. 눈으로 ±5px 안에 영역을 주면 `local_ink` 로 상자 안에서만
밝기를 갈라 글자 경계를 되돌려 준다. 상자를 원본 글자 범위 밖으로 넓히면
옆 그림을 덮어쓰므로, 좌표는 반드시 이렇게 재서 쓴다.

    python ../tools/snap.py file_figure_MH0  x0 y0 x1 y1  [x0 y0 x1 y1 ...]
"""
import sys
import numpy as np
import detect
import atlas


def _band(cnt, frac=0.3):
    """잉크가 많은 연속 구간 — 글자 줄만 남기고 화살표·괘선을 뗀다.

    도면 라벨 옆에는 가리키는 화살표가 같은 색으로 그려져 있다. 잉크가 있는
    줄을 다 담으면 화살표까지 상자에 들어가고, 그러면 지울 때 화살표도
    같이 지워져 도면 정보가 사라진다."""
    if not cnt.any():
        return None
    thr = cnt.max() * frac
    best = cur = None
    for i, v in enumerate(cnt):
        if v >= thr:
            cur = (i, i) if cur is None else (cur[0], i)
            if best is None or cur[1] - cur[0] > best[1] - best[0]:
                best = cur
        else:
            cur = None
    return best


def snap(px, box, pad=0, frac=0.3, vert=False):
    """(x0, y0, x1, y1) — 글자 잉크에 딱 맞춘 상자. 못 찾으면 None.

    vert=True 면 세로쓰기 — 줄이 아니라 **칸**으로 띠를 잡는다. 가로 규칙을
    그대로 쓰면 글자 사이 빈 줄에서 끊겨 마지막 한 글자만 남는다."""
    x0, y0, x1, y1 = box
    lm, col, _, _ = atlas.local_ink(px, (x0, y0, x1, y1))
    sub = lm[y0:y1, x0:x1]
    if sub.sum() < 8:
        return None
    if vert:
        # 세로는 축을 바꿔 같은 규칙을 적용한 뒤 되돌린다
        r = _snap_axis(sub.T, frac)
        if r is None:
            return None
        (a0, a1), (b0, b1) = r
        return (x0 + a0 - pad, y0 + b0 - pad,
                x0 + a1 + 1 + pad, y0 + b1 + 1 + pad)
    r = _snap_axis(sub, frac)
    if r is None:
        return None
    (a0, a1), (b0, b1) = r
    return (x0 + b0 - pad, y0 + a0 - pad,
            x0 + b1 + 1 + pad, y0 + a1 + 1 + pad)


def _snap_axis(sub, frac):
    """((줄 시작, 줄 끝), (칸 시작, 칸 끝)) — 가로쓰기 기준."""
    rows = sub.sum(1)
    yb = _band(rows, frac)
    if yb is None:
        return None
    # 핵심 구간을 잡은 뒤 위아래로 조금 더 — 획이 가는 줄(카타카나 윗변 등)이
    # 잘려 나가지 않게. 화살표 쪽으로는 잉크가 뚝 끊겨 더 안 번진다.
    lo, hi = yb
    edge = rows.max() * 0.08
    while lo > 0 and rows[lo - 1] >= edge:
        lo -= 1
    while hi + 1 < len(rows) and rows[hi + 1] >= edge:
        hi += 1
    yb = (lo, hi)
    sub = sub[yb[0]:yb[1] + 1]
    # 가로는 글자 사이 빈칸(≤5px)을 메우고 가장 긴 덩어리 — 옆에 붙은
    # 화살표는 5px 넘게 떨어져 있어 이렇게 떨어져 나간다
    col = sub.any(0)
    for k in range(1, 6):
        col[k:] |= sub.any(0)[:-k]
        col[:-k] |= sub.any(0)[k:]
    xb = _band(col.astype(int), 0.5)
    if xb is None:
        return None
    xs = np.where(sub[:, xb[0]:xb[1] + 1].any(0))[0]
    return yb, (xb[0] + int(xs[0]), xb[0] + int(xs[-1]))


def remeasure(px, box, pad=6, vert=False):
    """이미 잡아 둔 상자를 **넉넉한 창에서 다시** 재서 넓힌다.

    `local_ink` 는 상자 안만 보므로, 상자가 글자에 딱 붙어 있으면 표본이
    거의 글자뿐이라 임계값이 밀려 획 가장자리를 놓친다. 그 상태로 지우면
    후광이 남아 흰 판처럼 보인다(厨房·講堂·西森修治). 둘레까지 넣고 재면
    바탕이 표본에 들어와 경계가 제대로 잡힌다."""
    x0, y0, x1, y1 = box
    H, W = px.shape[:2]
    win = (max(0, x0 - pad), max(0, y0 - pad),
           min(W, x1 + pad), min(H, y1 + pad))
    s = snap(px, win, vert=vert)
    if s is None:
        return box
    # 원래 상자를 감싸는 방향으로만 넓힌다 — 줄어들면 일본어가 남는다
    return (min(x0, s[0]), min(y0, s[1]), max(x1, s[2]), max(y1, s[3]))


if __name__ == '__main__':
    name = sys.argv[1]
    args = sys.argv[2:]
    vert = '-v' in args
    px = detect.load(name)
    v = [int(a) for a in args if a != '-v']
    for i in range(0, len(v), 4):
        box = tuple(v[i:i + 4])
        s = snap(px, box, vert=vert)
        if s is None:
            print(f"  {box} -> 글자 없음")
        else:
            lm, col, _, _ = atlas.local_ink(px, box)
            print(f"  {box} -> ({s[0]}, {s[2]}, {s[1]}, {s[3]})"
                  f"   {s[2]-s[0]}x{s[3]-s[1]}  색 {col}")
