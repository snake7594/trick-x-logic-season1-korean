#!/usr/bin/env python3
"""재번역이 필요한 항목만 꺼낸다.

사용법:  python retranslate.py [id목록.json] [개수]
기본값:  _retranslate_ids.json, 전부

제어 태그가 들어 있어 원문 그대로 되돌린 항목들이다.
태그(㊤㊥㊦㊧㊨)를 같은 위치·같은 개수로 유지한 채 앞뒤 텍스트만 번역해야 한다.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
idfile = sys.argv[1] if len(sys.argv) > 1 else '_retranslate_ids.json'
want = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9

path = os.path.join(HERE, idfile)
if not os.path.exists(path):
    sys.exit(f"'{idfile}' 없음")
ids = set(json.load(open(path, encoding='utf-8')))

idx = json.load(open(os.path.join(HERE, '_index.json'), encoding='utf-8'))
out = 0
for meta in idx['files']:
    doc = json.load(open(os.path.join(HERE, meta['file']), encoding='utf-8'))
    for r in doc['entries']:
        if r['id'] not in ids:
            continue
        tags = [c for c in r['ja'] if c in '㊤㊥㊦㊧㊨']
        print(json.dumps({
            "id": r['id'],
            "speaker": r.get('speaker_hint'),
            "category": r['category'],
            "ja": r['ja'],
            "tags_required": ''.join(tags),
            "max": r['max_chars'],
        }, ensure_ascii=False))
        out += 1
        if out >= want:
            sys.exit(0)
print(f"# {out}개 출력", file=sys.stderr)
