#!/usr/bin/env python3
"""번역 결과를 JSON 에 반영한다.

사용법:  python apply.py 번역.jsonl
입력:    한 줄에 {"id": "...", "ko": "..."} 또는
                 {"group": "...", "parts": [{"id": "...", "ko": "..."}, ...]}

ko 외의 필드는 절대 건드리지 않는다.
"""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2:
    sys.exit("사용법: python apply.py 번역.jsonl")

trans = {}
with open(sys.argv[1], encoding='utf-8') as f:
    for ln, line in enumerate(f, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            sys.exit(f"{ln}행 JSON 파싱 실패: {e}")
        if 'parts' in rec:
            for p in rec['parts']:
                if 'ko' in p:
                    trans[p['id']] = p['ko']
        elif 'id' in rec:
            trans[rec['id']] = rec.get('ko', '')
        else:
            sys.exit(f"{ln}행: id 도 parts 도 없음")

print(f"번역 {len(trans):,}건 읽음")

idx = json.load(open(os.path.join(HERE, '_index.json'), encoding='utf-8'))
applied = 0
unknown = set(trans)
for meta in idx['files']:
    fn = meta['file']
    path = os.path.join(HERE, fn)
    doc = json.load(open(path, encoding='utf-8'))
    hit = 0
    for r in doc['entries']:
        if r['id'] in trans:
            r['ko'] = trans[r['id']]
            unknown.discard(r['id'])
            hit += 1
    if hit:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(f"  {fn:<16} {hit:>6,}건 반영")
        applied += hit

print(f"\n총 {applied:,}건 반영")
if unknown:
    print(f"경고: 알 수 없는 id {len(unknown)}개 (앞 5개: {sorted(unknown)[:5]})")
print("\n이제 검증하세요:  python validate.py")
