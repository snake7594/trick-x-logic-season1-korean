"""이미지 분류를 확정하고 한글화 대상 목록·시트를 만든다."""
import paths
import csv
import json
import os
import re
import shutil
from collections import Counter
from PIL import Image, ImageDraw

IMG = paths.IMAGES
idx = json.load(open(os.path.join(IMG, '_index.json'), encoding='utf-8'))
SPRITE = re.compile(r'^(yos|kao|mar|tuk|yam|its)_')

# 육안 확인으로 확정
TEXT_PAT = [
    r'^inspect_title', r'^inspect_caption', r'^stuff_credit(?!_bg)',
    r'_result_(bad|good)$', r'^system_help', r'^tutorial_figure_\d',
    r'_bg_title', r'^ol_title', r'^silver_hira_mekuri',
    r'^scenario_menu', r'^detective_mode', r'^common_scenario',
    r'^file_profile', r'^file_figure', r'^file_hint', r'^file_progress',
    r'^introduction_note', r'^detective_chosho', r'^menu', r'^game_title',
    r'^op_seq', r'^question_advice(?!_bg)', r'^adv_hint(?!_bg)',
    r'^adv_common(?!_bg)', r'^detective_menu', r'^information', r'^window',
    r'^adv_hint_bg_',   # 이름은 _bg 지만 일본어 간판 텍스트 (육안 확인)
    r'^ondoku_mode', r'^answer_score', r'^common\d', r'^eula',
]
# 육안 확인 결과 텍스트가 아닌 것 (규칙 예외)
NOT_TEXT = [r'^file_extra_gold', r'^bridge', r'^common_ex']
BG_PAT = [r'_bg(_?\w*)?$', r'_ol(_?\d*)?$', r'_ans(_?\d*)?$',
          r'_seq(_?\d*)?$', r'_curtain', r'_back_image$']

text_re = [re.compile(p) for p in TEXT_PAT]
not_re = [re.compile(p) for p in NOT_TEXT]
bg_re = [re.compile(p) for p in BG_PAT]

need, bg = [], []
for i in idx:
    n = i['name']
    if SPRITE.match(n) or i['archive'] == 'character.bin':
        bg.append(i)
    elif any(r.search(n) for r in not_re):
        bg.append(i)
    elif any(r.search(n) for r in text_re):
        need.append(i)
    elif any(r.search(n) for r in bg_re):
        bg.append(i)
    else:
        bg.append(i)

# 크레딧은 별도 표시(스태프 이름 나열이라 우선순위 낮음)
for i in need:
    i['category'] = ('credit' if i['name'].startswith('stuff_credit')
                     else 'ui_text')

cred = [i for i in need if i['category'] == 'credit']
ui = [i for i in need if i['category'] == 'ui_text']
print(f"한글화 대상 {len(need)}  (UI/본문 {len(ui)} + 크레딧 {len(cred)})")
print(f"배경·스프라이트 {len(bg)}")

# 목록 저장
with open(os.path.join(IMG, 'translate_list.csv'), 'w', newline='',
          encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['category', 'archive', 'name', 'path', 'w', 'h'])
    for i in sorted(need, key=lambda x: (x['category'], x['archive'], x['name'])):
        w.writerow([i['category'], i['archive'], i['name'], i['path'],
                    i['w'], i['h']])

# 대상만 따로 복사
dst = os.path.join(IMG, '_translate')
if os.path.isdir(dst):
    shutil.rmtree(dst)
for i in need:
    sub = os.path.join(dst, i['category'], i['archive'][:-4])
    os.makedirs(sub, exist_ok=True)
    shutil.copy(os.path.join(IMG, i['path']),
                os.path.join(sub, i['name'] + '.png'))

print("\nUI 대상 그룹:")


def grp(n):
    return re.sub(r'[\d_]+$', '', re.sub(r'_\d+.*$', '', n))


for g, c in Counter(grp(i['name']) for i in ui).most_common(24):
    print(f"   {g:<28}{c:>5}")

json.dump({"need": [i['path'] for i in need],
           "ui_text": [i['path'] for i in ui],
           "credit": [i['path'] for i in cred],
           "background": [i['path'] for i in bg]},
          open(os.path.join(IMG, '_classify.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print(f"\n-> translate_list.csv / _translate/ ({len(need)}장 복사)")
