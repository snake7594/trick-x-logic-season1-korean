"""지도에 적은 상자가 원본 글자를 다 덮는지 전수 검사한다.

`atlas.py` 는 상자 **안쪽만** 지우므로, 원본 글자가 상자 밖으로 몇 픽셀이라도
삐져나와 있으면 그만큼 일본어가 화면에 남는다. 실제로 스토리 선택 화면의
`練習問題` 가 4px 모자라 아래쪽 획이 남아 있었다.

방법: 상자를 조금 넓힌 영역에서 글자 화소를 연결 성분으로 묶고, **상자 안에
걸쳐 있으면서 상자 밖으로도 뻗은** 성분을 찾는다. 그 성분의 상자 밖 픽셀 수가
곧 '남을 일본어'다.

    python ../tools/boxaudit.py            # 전체
    python ../tools/boxaudit.py 이미지이름  # 하나만
"""
import paths
import os
import sys
import numpy as np
from PIL import Image
from scipy import ndimage

import atlas
from atlas_maps import MAPS

PAD = 10          # 상자 둘레 몇 px 까지 살펴볼지
MIN_OUT = 6       # 이만큼 넘게 삐져나오면 보고


def boxes_of(spec):
    """지도에서 좌표를 직접 준 상자만 뽑는다 — [(키, kind, x0, x1, y0, y1)]."""
    passes = spec if isinstance(spec, list) else [('dark', spec)]
    out = []
    for kind, m in passes:
        if not isinstance(m, dict):
            continue
        for k, v in m.items():
            if (isinstance(v, tuple) and len(v) == 5
                    and all(isinstance(n, int) for n in v[1:])):
                out.append((k, kind, v[1], v[2], v[3], v[4]))
    return out


def leak(px, box):
    """상자 밖으로 새는 글자 픽셀 수와 그 범위."""
    x0, x1, y0, y1 = box
    ex0, ex1 = max(0, x0 - PAD), min(px.shape[1], x1 + PAD)
    ey0, ey1 = max(0, y0 - PAD), min(px.shape[0], y1 + PAD)

    m = atlas.local_ink(px, (x0, y0, x1, y1))[0]
    if not m.any():
        return 0, None
    # 상자 안에서 정한 밝기 기준을 넓힌 영역에 그대로 적용한다
    lum = px[..., :3].astype(np.float32) @ [0.299, 0.587, 0.114]
    op = px[..., 3] > 100
    vin = lum[m]
    inner = lum[y0:y1, x0:x1][px[y0:y1, x0:x1, 3] > 100]
    if vin.mean() > inner.mean():
        sel = (lum >= vin.min()) & op          # 밝은 글자
    else:
        sel = (lum <= vin.max()) & op          # 어두운 글자

    reg = np.zeros_like(sel)
    reg[ey0:ey1, ex0:ex1] = sel[ey0:ey1, ex0:ex1]
    lab, n = ndimage.label(reg, np.ones((3, 3), bool))
    if not n:
        return 0, None
    ids = set(np.unique(lab[y0:y1, x0:x1])) - {0}
    if not ids:
        return 0, None
    comp = np.isin(lab, list(ids))
    comp[y0:y1, x0:x1] = False
    cnt = int(comp.sum())
    if not cnt:
        return 0, None
    ys, xs = np.where(comp)
    return cnt, (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max()))


def main(only=None):
    bad = 0
    for name, spec in sorted(MAPS.items()):
        if only and only != name:
            continue
        path = None
        for d in os.listdir(paths.IMAGES):
            p = os.path.join(paths.IMAGES, d, name + '.png')
            if os.path.exists(p):
                path = p
                break
        if not path:
            print(f"  ! {name}: 원본 PNG 없음")
            continue
        px = np.asarray(Image.open(path).convert('RGBA'))
        rows = []
        for key, kind, x0, x1, y0, y1 in boxes_of(spec):
            cnt, rng = leak(px, (x0, x1, y0, y1))
            if cnt >= MIN_OUT:
                rows.append((key, (x0, x1, y0, y1), cnt, rng))
        if rows:
            bad += len(rows)
            print(f"\n{name}")
            for key, box, cnt, rng in sorted(rows, key=lambda r: -r[2]):
                print(f"  {key:<6} 상자 x{box[0]}..{box[1]} y{box[2]}..{box[3]}"
                      f"  밖으로 {cnt:>4}px  범위 x{rng[0]}..{rng[1]} y{rng[2]}..{rng[3]}")
    print(f"\n상자 밖으로 새는 곳 {bad}건 (기준 {MIN_OUT}px 초과)")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
