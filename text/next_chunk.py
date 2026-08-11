#!/usr/bin/env python3
"""번역할 다음 묶음을 뽑아 준다(문장 그룹이 쪼개지지 않게).

사용법:  python next_chunk.py TU.json [그룹수]
출력:    한 줄에 문장 그룹 하나 (JSON)
"""
import json
import os
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
fn = sys.argv[1] if len(sys.argv) > 1 else 'TU.json'
want = int(sys.argv[2]) if len(sys.argv) > 2 else 40

path = os.path.join(HERE, fn)
if not os.path.exists(path):
    avail = sorted(f for f in os.listdir(HERE)
                   if f.endswith('.json') and not f.startswith('_')
                   and f != 'charset.json')
    sys.exit(f"'{fn}' 없음. 사용 가능: {', '.join(avail)}")
doc = json.load(open(path, encoding='utf-8'))

groups = OrderedDict()
for r in doc['entries']:
    groups.setdefault(r['group']['id'], []).append(r)

out = 0
for gid, rows in groups.items():
    if all(r.get('ko') for r in rows):
        continue                      # 이미 다 번역됨
    rec = {
        "group": gid,
        "speaker": rows[0].get('speaker_hint'),
        "category": rows[0]['category'],
        "full_ja": rows[0]['group']['ja'] or rows[0]['ja'],
        "parts": [{"id": r['id'], "ja": r['ja'], "max": r['max_chars']}
                  for r in rows],
    }
    print(json.dumps(rec, ensure_ascii=False))
    out += 1
    if out >= want:
        break

if out == 0:
    print(f"# {fn} 남은 그룹 없음", file=sys.stderr)
else:
    print(f"# {fn} 에서 {out}개 그룹 출력", file=sys.stderr)
