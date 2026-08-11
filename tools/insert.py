"""번역문을 PRCS 스크립트에 재삽입하고 크기 변화를 계산한다."""
import paths
import json
import os
import struct
from collections import defaultdict
from isolib import Iso
from sectpack import from_iso, SectPack, SEC
from lz import compress, decompress

TEXT = paths.TEXT
m = json.load(open(os.path.join(TEXT, '_hangul_codes.json'), encoding='utf-8'))['map']
H2C = {ch: int(v, 16) for ch, v in m.items()}


from core import encode          # 반각공백 -> 전각공백 치환 포함


def rebuild(d, items):
    """items: [(len_off, str_off, orig_bytes, new_raw)] — 오프셋 순."""
    out = bytearray()
    pos = 0
    for lo, so, nb, new in sorted(items):
        out += d[pos:lo]
        out += struct.pack('<I', len(new) + 1)
        out += new + b'\x00'
        pos = so + nb
    out += d[pos:]
    return bytes(out)


# 번역 로드: archive -> file -> [(lo, so, nb, new_raw)]
idx = json.load(open(os.path.join(TEXT, '_index.json'), encoding='utf-8'))
plan = defaultdict(lambda: defaultdict(list))
n_tr = n_same = 0
for meta in idx['files']:
    doc = json.load(open(os.path.join(TEXT, meta['file']), encoding='utf-8'))
    for r in doc['entries']:
        ko = r.get('ko') or ''
        if not ko:
            n_same += 1
            continue
        loc = r['loc']
        plan[r['archive']][r['file']].append(
            (loc['len_off'], loc['str_off'], loc['orig_bytes'], encode(ko)))
        n_tr += 1
print(f"번역 반영 대상 {n_tr:,} / 원문 유지 {n_same:,}")

iso = Iso()
report = []
new_scripts = {}

for arch in sorted(plan):
    sp = (SectPack(open('common.bin', 'rb').read()) if arch == 'common.bin'
          else from_iso(iso, arch))
    orig_total = new_total = 0
    grew = 0
    for fname, items in plan[arch].items():
        e = sp.byname(fname)
        d = sp.get(e)
        nd = rebuild(d, items)
        assert nd[:4] == b'PRCS'
        # 저장 형태(원본이 압축이면 압축)
        if e['comp']:
            c = compress(nd)
            assert decompress(c, len(nd)) == nd
            payload = struct.pack('<II', len(nd), len(c)) + c
        else:
            payload = nd
        nsec = (len(payload) + SEC - 1) // SEC
        orig_total += e['nsec']
        new_total += nsec
        if nsec > e['nsec']:
            grew += 1
        new_scripts[(arch, fname)] = payload
    report.append((arch, len(plan[arch]), orig_total, new_total, grew))

print(f"\n{'아카이브':<14}{'스크립트':>8}{'원본섹터':>10}{'신규섹터':>10}{'증감':>8}{'커진파일':>9}")
tot_o = tot_n = 0
for arch, nf, o, n, grew in report:
    print(f"{arch:<14}{nf:>8}{o:>10,}{n:>10,}{n-o:>+8,}{grew:>9}")
    tot_o += o
    tot_n += n
print(f"{'합계':<14}{'':>8}{tot_o:>10,}{tot_n:>10,}{tot_n-tot_o:>+8,}")

import pickle
pickle.dump(new_scripts, open('new_scripts.pkl', 'wb'))
print(f"\n-> new_scripts.pkl ({len(new_scripts)} 파일)")
