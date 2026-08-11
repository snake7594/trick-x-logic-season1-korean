"""이미지 번역표를 읽어 한글을 그리고 GIM 으로 되돌린 뒤 아카이브 payload 를 만든다.

번역표: <ROOT>/images/image_text.json
  { "<archive>/<name>": {"ko": "한글", "mode": "h|v"} }
결과:   image_payloads.pkl  { (archive, gim경로): 새 GIM 바이트 }
"""
import paths
import json
import os
import pickle
import numpy as np
from PIL import Image
from isolib import Iso
from sectpack import from_iso, SectPack
from prcs import SCENARIOS
import gim
import gimenc
import imgtext
import vtitle
import atlas
from atlas_maps import MAPS, NOTES

IMG = paths.IMAGES
TXT = os.path.join(IMG, 'image_text.json')

trans = json.load(open(TXT, encoding='utf-8')) if os.path.exists(TXT) else {}
trans = {k: v for k, v in trans.items() if v.get('ko')}
print(f"번역표 {len(trans)}건 / 챕터 타이틀 / UI 아틀라스 {len(MAPS)}종")

iso = Iso()
out = {}
ok = fail = 0
for nm in SCENARIOS + ['common.bin']:
    sp = (SectPack(open('common.bin', 'rb').read()) if nm == 'common.bin'
          else from_iso(iso, nm))
    for e in [x for x in sp.ents if x['name'].endswith('.gim')]:
        base = e['name'].split('/')[-1][:-4]
        key = f"{nm[:-4]}/{base}"
        kind = ('text' if key in trans
                else 'title' if '_bg_title' in base
                else 'atlas' if base in MAPS
                else 'note' if base in NOTES else None)
        if kind is None:
            continue
        t = trans.get(key, {})
        d = sp.get(e)
        r = gim.decode(d)
        if r is None:
            fail += 1
            continue
        w, h, px = r
        try:
            if kind == 'title':
                new_px = vtitle.build(base, px)
            elif kind == 'atlas':
                new_px = atlas.build_all(px, MAPS[base])
            elif kind == 'note':
                ko, reg, cols, sz = NOTES[base]
                new_px, left = atlas.build_note(px, ko, reg, cols, sz)
                if left:
                    print(f"   ! {base}: {left}자 넘침")
            elif t.get('mode') == 'v':
                new_px = imgtext.render_vertical(px, t['ko'])
            elif isinstance(t['ko'], list):
                new_px = imgtext.render_rows(px, t['ko'],
                                             align=t.get('align', 'center'))
            else:
                new_px = imgtext.render(px, t['ko'],
                                        align=t.get('align', 'center'))
            new_gim = gimenc.encode(d, new_px)
        except Exception as ex:
            print(f"   실패 {key}: {ex}")
            fail += 1
            continue
        out[(nm, e['name'])] = new_gim
        # 미리보기
        prev = os.path.join(IMG, '_preview')
        os.makedirs(prev, exist_ok=True)
        w2, h2, px2 = gim.decode(new_gim)
        Image.fromarray(px2, 'RGBA').save(os.path.join(prev, f"{base}.png"))
        ok += 1

pickle.dump(out, open('image_payloads.pkl', 'wb'))
print(f"\n성공 {ok} / 실패 {fail}  -> image_payloads.pkl")
