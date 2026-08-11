"""모든 아카이브의 GIM 텍스처를 PNG 로 추출한다."""
import paths
import json
import os
import time
import numpy as np
from PIL import Image
from isolib import Iso
from sectpack import from_iso, SectPack
from prcs import SCENARIOS
import gim

OUT = paths.IMAGES
ARCHS = SCENARIOS + ['common.bin', 'character.bin']

os.makedirs(OUT, exist_ok=True)
iso = Iso()
index = []
t0 = time.time()
ok = fail = 0

for nm in ARCHS:
    try:
        sp = (SectPack(open('common.bin', 'rb').read()) if nm == 'common.bin'
              else from_iso(iso, nm))
    except Exception as e:
        print(f"  {nm}: {e}")
        continue
    gims = [e for e in sp.ents if e['name'].endswith('.gim')]
    if not gims:
        continue
    sub = os.path.join(OUT, nm[:-4])
    os.makedirs(sub, exist_ok=True)
    n_ok = 0
    for e in gims:
        d = sp.get(e)
        base = e['name'].split('/')[-1][:-4]
        try:
            r = gim.decode(d)
        except Exception:
            r = None
        if r is None:
            fail += 1
            continue
        w, h, px = r
        Image.fromarray(px, 'RGBA').save(os.path.join(sub, base + '.png'))
        # 텍스트 판별용 통계
        a = px[:, :, 3]
        rgb = px[:, :, :3].astype(np.int16)
        opaque = int((a > 8).sum())
        # 인접 픽셀 밝기 차이 = 에지량 (글자는 에지가 많다)
        g = rgb.mean(axis=2)
        edge = float(np.abs(np.diff(g, axis=1)).mean() +
                     np.abs(np.diff(g, axis=0)).mean()) / 2
        index.append({
            "archive": nm, "name": base, "path": f"{nm[:-4]}/{base}.png",
            "w": w, "h": h, "opaque_ratio": round(opaque / (w * h), 4),
            "edge": round(edge, 2),
        })
        n_ok += 1
        ok += 1
    print(f"  {nm:<14} {n_ok}/{len(gims)}")

with open(os.path.join(OUT, '_index.json'), 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, indent=1)
print(f"\n성공 {ok} / 실패 {fail}  ({time.time()-t0:.0f}초)")
print(f"-> {OUT}")
