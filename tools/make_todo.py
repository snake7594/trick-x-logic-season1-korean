"""남은 이미지의 번역 작업 파일과 판독용 시트를 만든다."""
import paths
import json
import os
import re
import numpy as np
from PIL import Image, ImageDraw
import imgtext

IMG = paths.IMAGES
cl = json.load(open(os.path.join(IMG, '_classify.json'), encoding='utf-8'))
idx = {i['path']: i for i in
       json.load(open(os.path.join(IMG, '_index.json'), encoding='utf-8'))}
done = json.load(open(os.path.join(IMG, 'image_text.json'), encoding='utf-8'))

# 이름 기준 중복 제거 (같은 이미지가 여러 시나리오에 존재)
byname = {}
for p in cl['ui_text']:
    n = p.split('/')[-1][:-4]
    byname.setdefault(n, []).append(p)

todo = {}
for n, paths in sorted(byname.items()):
    key0 = f"{paths[0].split('/')[0]}/{n}"
    if key0 in done:
        continue
    p = paths[0]
    a = np.asarray(Image.open(os.path.join(IMG, p)).convert('RGBA'))
    rows = imgtext.text_rows(a)
    i = idx[p]
    todo[n] = {
        "paths": paths,
        "size": [i['w'], i['h']],
        "rows": len(rows),
        "ja": ["" for _ in range(max(len(rows), 1))],
        "ko": ["" for _ in range(max(len(rows), 1))],
        "mode": "h",
    }

json.dump(todo, open(os.path.join(IMG, 'image_text_todo.json'), 'w',
                     encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"남은 이미지 {len(todo)}종 (파일 {sum(len(v['paths']) for v in todo.values())}장)")

# 판독용 시트 (그룹별, 확대)
os.makedirs(os.path.join(IMG, '_read'), exist_ok=True)
items = sorted(todo.items())
PER = 12
for s in range(0, len(items), PER):
    chunk = items[s:s + PER]
    CW, CH = 800, 130
    sh = Image.new('RGB', (CW, len(chunk) * (CH + 20)), (20, 20, 24))
    dr = ImageDraw.Draw(sh)
    for k, (n, v) in enumerate(chunk):
        im = Image.open(os.path.join(IMG, v['paths'][0])).convert('RGBA')
        bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert('RGB')
        sc = min((CW - 8) / im.width, (CH - 8) / im.height, 3)
        im = im.resize((max(int(im.width * sc), 1), max(int(im.height * sc), 1)),
                       Image.LANCZOS)
        y = k * (CH + 20)
        sh.paste(im, (4, y + 18))
        dr.text((4, y + 3), f"{n}  ({v['size'][0]}x{v['size'][1]}, {v['rows']}행)",
                fill=(255, 240, 120))
    sh.save(os.path.join(IMG, '_read', f'sheet_{s//PER+1:02d}.png'))
print(f"판독 시트 {(len(items)+PER-1)//PER}장 -> images/_read/")
