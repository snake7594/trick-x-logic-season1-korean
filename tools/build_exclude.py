"""전체 번역하되 '지정한 부분만 원문 유지'한 ISO 를 만든다.

사용법: python build_exclude.py <태그> <제외스펙...>
제외스펙: 파일명(TU_interval_1.bin) 또는 id접두(TU/TU_interval_1/003)
"""
import paths
import json
import os
import shutil
import struct
import sys
from collections import defaultdict
from isolib import Iso
from sectpack import from_iso, SectPack
from lz import compress, decompress
from core import (encode, rebuild_script, rebuild_archive, dir_records,
                  TEXT, SEC)

GAME = paths.ROOT
ISO_SRC = GAME + r'\Trick x Logic Season 1.iso'
FONT = {'./script/Font/NovelFontList.dat': 'font_out/NovelFont_KR.payload',
        './script/Font/AdvFontList.dat': 'font_out/AdvFont_KR.payload'}

tag = sys.argv[1]
excl = [a for a in sys.argv[2:] if a != '--nofont']
NOFONT = '--nofont' in sys.argv      # 폰트를 원본으로 두고 텍스트만 번역
ISO_DST = GAME + rf'\KR-diag{tag}.iso'


def excluded(r):
    for e in excl:
        if r['file'].endswith('/' + e) or r['id'].startswith(e):
            return True
    return False


idx = json.load(open(os.path.join(TEXT, '_index.json'), encoding='utf-8'))
plan = defaultdict(list)
n_ex = 0
for meta in idx['files']:
    for r in json.load(open(os.path.join(TEXT, meta['file']),
                            encoding='utf-8'))['entries']:
        if excluded(r):
            n_ex += 1
            continue                      # 원문 유지 = 교체하지 않음
        loc = r['loc']
        plan[(r['archive'], r['file'])].append(
            (loc['len_off'], loc['str_off'], loc['orig_bytes'], encode(r['ko'])))
print(f"제외(원문 유지) {n_ex}건")

iso = Iso()
by_arch = defaultdict(dict)
for (arch, fname), items in plan.items():
    sp = (SectPack(open('common.bin', 'rb').read()) if arch == 'common.bin'
          else from_iso(iso, arch))
    e = sp.byname(fname)
    d = sp.get(e)
    nd = rebuild_script(d, items)
    if e['comp']:
        c = compress(nd)
        assert decompress(c, len(nd)) == nd
        payload = struct.pack('<II', len(nd), len(c)) + c
    else:
        payload = nd
    by_arch[arch][fname] = payload

recs = {n.split('/')[-1]: (o, l, s) for o, n, l, s in dir_records(iso)}
built, plan2 = {}, []
for arch in sorted(by_arch):
    sp = (SectPack(open('common.bin', 'rb').read()) if arch == 'common.bin'
          else from_iso(iso, arch))
    rep = dict(by_arch[arch])
    ovr = None
    if arch == 'common.bin' and not NOFONT:
        for n, p in FONT.items():
            rep[n] = open(p, 'rb').read()
        ovr = {n: 1 for n in FONT}
    nb = rebuild_archive(sp, rep, ovr)
    built[arch] = nb
    rec_off, lba, size = recs[arch]
    plan2.append([arch, rec_off, lba, len(nb), (len(nb) + SEC - 1) // SEC])

allf = sorted(((l, (s + SEC - 1) // SEC, n.split('/')[-1])
               for o, n, l, s in dir_records(iso)), key=lambda t: t[0])
mine = {p[0]: p for p in plan2}
for i, (lba, nsec, base) in enumerate(allf):
    if base not in mine or i + 1 >= len(allf):
        continue
    end = mine[base][2] + mine[base][4]
    nxt_lba, _, nxt_base = allf[i + 1]
    cur = mine[nxt_base][2] if nxt_base in mine else nxt_lba
    if end > cur:
        shift = end - cur
        assert nxt_base in mine, f"{base} -> {nxt_base} 침범"
        mine[nxt_base][2] += shift
        print(f"  {nxt_base} {shift}섹터 이동")

shutil.copyfile(ISO_SRC, ISO_DST)
with open(ISO_DST, 'r+b') as f:
    for arch, rec_off, lba, nbytes, nsec in plan2:
        f.seek(lba * SEC)
        f.write(built[arch])
        if nsec * SEC - nbytes:
            f.write(b'\0' * (nsec * SEC - nbytes))
        buf = bytearray(16)
        struct.pack_into('<I', buf, 0, lba)
        struct.pack_into('>I', buf, 4, lba)
        struct.pack_into('<I', buf, 8, nbytes)
        struct.pack_into('>I', buf, 12, nbytes)
        f.seek(rec_off + 2)
        f.write(buf)
print(f"-> {os.path.basename(ISO_DST)} ({os.path.getsize(ISO_DST):,}B)")
