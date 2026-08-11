#!/usr/bin/env python3
"""번역 결과 검증기.

사용법:  python validate.py            (전체)
         python validate.py TU.json    (특정 파일만)

검사 항목
 1. 원문 무결성  — id / ja / loc / max_chars 가 하나도 안 바뀌었는지
 2. 길이 제한    — ko 글자수 <= max_chars
 3. 금지 문자    — 개행·제어문자·한자·표시 불가 문자
 4. 한글 종류    — 폰트 슬롯 상한(1914) 초과 여부
 5. 진행률
"""
import hashlib
import json
import os
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        return json.load(f)


idx = load('_index.json')
baseline = load('_baseline.json')['files']
cs = load('charset.json')

# 대사 출력 명령(0x01)이 아닌 문자열 — UI 라벨 등 고정 길이 슬롯.
# 번역해서 길이가 바뀌면 게임이 죽는다.
try:
    NOEDIT = set(load('_noteditable_ids.json'))
except Exception:
    NOEDIT = set()

HANGUL = set(cs['hangul']['chars'])
ALLOWED = HANGUL | set(cs['ascii']) | set(cs['kana']) | set(cs['punctuation_fullwidth'])
SLOT_LIMIT = cs['hangul_distinct_limit']['value']

# 게임이 명령으로 해석하는 인라인 태그. 지우면 파서가 깨져 게임이 죽는다.
CTRL_TAGS = set('㊤㊥㊦㊧㊨')

targets = sys.argv[1:] or sorted(e['file'] for e in idx['files'])
errors = []
used_hangul = Counter()
done = total = 0

for fn in targets:
    doc = load(fn)
    rows = doc['entries']
    base = baseline.get(fn)

    if base and len(rows) != base['entries']:
        errors.append(f"{fn}: 엔트리 수가 {base['entries']} -> {len(rows)} 로 바뀜")

    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r['id']}\x1f{r['ja']}\x1f{r['loc']['len_off']}"
                 f"\x1f{r['loc']['str_off']}\x1f{r['loc']['orig_bytes']}"
                 f"\x1f{r['max_chars']}\x1e".encode())
    if base and h.hexdigest() != base['sha256']:
        errors.append(f"{fn}: 원문/위치정보가 변경됨 (id·ja·loc·max_chars 는 "
                      f"절대 수정 금지). ko 만 채울 것.")

    for r in rows:
        total += 1
        ko = r.get('ko', '')
        ja = r['ja']
        if not isinstance(ko, str):
            errors.append(f"{r['id']}: ko 가 문자열이 아님")
            continue
        if not ko:
            continue
        done += 1

        # 제어 태그 보존 검사 — 어기면 게임이 죽는다
        jt = [c for c in ja if c in CTRL_TAGS]
        kt = [c for c in ko if c in CTRL_TAGS]
        if jt != kt:
            errors.append(f"{r['id']}: 제어 태그가 바뀜 "
                          f"(원문 {''.join(jt) or '없음'} -> 번역 {''.join(kt) or '없음'}). "
                          f"태그는 원문 그대로 같은 위치에 두어야 함")
        if any(0xFF61 <= ord(c) <= 0xFF9F for c in ja) and ko != ja:
            errors.append(f"{r['id']}: 반각 가타카나(제어 명령) 포함 원문은 "
                          f"번역하지 말고 원문 그대로 둘 것")
        if ja.strip('　') == '' and ko != ja:
            errors.append(f"{r['id']}: 전각공백만인 원문(레이아웃용)은 "
                          f"번역하지 말고 원문 그대로 둘 것")
        if len(ko) > r['max_chars']:
            errors.append(f"{r['id']}: {len(ko)}자 > 상한 {r['max_chars']}자")
        if r['id'] in NOEDIT and ko != ja:
            errors.append(f"{r['id']}: 대사가 아닌 문자열(UI 라벨 등 고정 슬롯)이라 "
                          f"번역하면 게임이 죽는다. ko 에 원문 그대로 둘 것")
        if ko == ja:
            continue          # 의도적 원문 유지(제어 태그 등) — 문자 검사 제외
        bad = set()
        for ch in ko:
            if ch in HANGUL:
                used_hangul[ch] += 1
            elif ch in ALLOWED:
                pass
            elif ch in '\n\r\t':
                bad.add('개행/탭')
            elif unicodedata.category(ch) == 'Cc':
                bad.add('제어문자')
            elif '一' <= ch <= '鿿':
                bad.add(f'한자 {ch}')
            elif '가' <= ch <= '힣':
                bad.add(f'완성형밖 한글 {ch}')
            else:
                bad.add(f'표시불가 {ch!r}')
        if bad:
            errors.append(f"{r['id']}: 사용 불가 문자 {sorted(bad)[:4]}")

print(f"진행률 {done:,}/{total:,} ({done/total*100:.1f}%)")
print(f"쓰인 한글 종류 {len(used_hangul):,} / 슬롯 상한 {SLOT_LIMIT:,}")
if len(used_hangul) > SLOT_LIMIT:
    over = len(used_hangul) - SLOT_LIMIT
    rare = [c for c, n in used_hangul.most_common()[-over - 10:]]
    errors.append(f"한글 종류가 슬롯 상한을 {over}자 초과. "
                  f"드물게 쓰인 음절: {''.join(rare[:30])}")

if errors:
    print(f"\n오류 {len(errors)}건 (앞 40건):")
    for e in errors[:40]:
        print("  -", e)
    sys.exit(1)
print("\n검증 통과")
