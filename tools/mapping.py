"""번역에 쓰인 한글을 원본 한자 코드에 배정한다."""
import paths
import json
import os
from collections import Counter
from fonts import load, glyphs

TEXT = paths.TEXT
KANJI0 = 0x889F
OUT = os.path.join(TEXT, '_hangul_codes.json')

idx = json.load(open(os.path.join(TEXT, '_index.json'), encoding='utf-8'))

# 1) 번역에 실제로 쓰인 문자 수집
used = Counter()
nontext = Counter()
for meta in idx['files']:
    doc = json.load(open(os.path.join(TEXT, meta['file']), encoding='utf-8'))
    for r in doc['entries']:
        for ch in r['ko']:
            if '가' <= ch <= '힣':
                used[ch] += 1
            else:
                nontext[ch] += 1
print(f"쓰인 한글 {len(used):,}종 (연 {sum(used.values()):,}자)")
print(f"한글 외 문자 {len(nontext)}종: {''.join(sorted(nontext))[:80]}")

# 2) 두 폰트의 한자 코드
codes = {}
for name, fn in (('NovelFont', 'NovelFontList.dat'), ('AdvFont', 'AdvFontList.dat')):
    d, _ = load('out/' + fn)
    gl = glyphs(d)
    codes[name] = {g['code'] for g in gl if g['code'] >= KANJI0}
    print(f"{name}: 한자 슬롯 {len(codes[name]):,}")

both = sorted(codes['NovelFont'] & codes['AdvFont'])
print(f"두 폰트 공통 한자 코드: {len(both):,}  "
      f"(0x{both[0]:04X} ~ 0x{both[-1]:04X})")

# 3) 한글 외 문자가 폰트에 다 있는지 확인
import struct


def sjis_of(ch):
    try:
        b = ch.encode('cp932')
    except Exception:
        return None
    return b[0] if len(b) == 1 else (b[0] << 8) | b[1]


nonkanji = {g['code'] for g in glyphs(load('out/NovelFontList.dat')[0])
            if g['code'] < KANJI0}
nonkanji &= {g['code'] for g in glyphs(load('out/AdvFontList.dat')[0])
             if g['code'] < KANJI0}
missing = [c for c in nontext if sjis_of(c) not in nonkanji]
print(f"폰트에 없는 비한글 문자: {len(missing)}개 {missing[:20]}")

assert len(used) <= len(both), f"한글 {len(used)}종 > 슬롯 {len(both)}"

# 4) 배정: 한글은 완성형(유니코드) 순, 코드는 오름차순
hangul = sorted(used)
mapping = {ch: both[i] for i, ch in enumerate(hangul)}

doc = {
    "note": "한글 -> 원본 한자 Shift-JIS 코드 배정. 폰트는 이 코드의 글리프를 "
            "해당 한글로 교체하고, 텍스트는 한글을 이 코드로 인코딩한다.",
    "count": len(mapping),
    "slots_available": len(both),
    "map": {ch: f"0x{code:04X}" for ch, code in mapping.items()},
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)

print(f"\n배정 {len(mapping):,}자 / 가용 {len(both):,} (여유 {len(both)-len(mapping):,})")
ks = list(mapping.items())
print("예시:", ', '.join(f"{c}=0x{v:04X}" for c, v in ks[:6]))
print(f"-> {OUT}")
