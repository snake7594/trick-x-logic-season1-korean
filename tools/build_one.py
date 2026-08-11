"""지정한 아카이브만 번역 반영한 진단 ISO 를 만든다 (ISO 구조 불변).

사용법:  python build_one.py <출력이름> <아카이브...>
예:      python build_one.py D TU.bin
         python build_one.py E TU_A.bin BJ.bin
common.bin(폰트+메뉴 번역)은 항상 포함하며 크기를 원본과 동일하게 유지한다.
"""
import paths
import os
import pickle
import shutil
import sys
from isolib import Iso, SEC
from sectpack import from_iso, SectPack
from build_iso import rebuild_archive, dir_records

GAME = paths.ROOT
ISO_SRC = GAME + r'\Trick x Logic Season 1.iso'
FONT = {'./script/Font/NovelFontList.dat': 'font_out/NovelFont_KR.payload',
        './script/Font/AdvFontList.dat': 'font_out/AdvFont_KR.payload'}

tag = sys.argv[1]
want = sys.argv[2:]
ISO_DST = GAME + rf'\KR-diag{tag}.iso'

new_scripts = pickle.load(open('new_scripts.pkl', 'rb'))
by_arch = {}
for (a, f), p in new_scripts.items():
    by_arch.setdefault(a, {})[f] = p

iso = Iso()
recs = {n.split('/')[-1]: (o, l, s) for o, n, l, s in dir_records(iso)}

data = open('common.bin', 'rb').read()
sp = SectPack(data)
rep = dict(by_arch['common.bin'])
for n, p in FONT.items():
    rep[n] = open(p, 'rb').read()
cb = rebuild_archive(sp, rep, {n: 1 for n in FONT})
cb += b'\0' * (len(data) - len(cb))
print(f"common.bin 포함 (크기 유지)")

out = {}
for arch in want:
    a = from_iso(iso, arch)
    nb = rebuild_archive(a, by_arch[arch])
    if len(nb) > len(a.data):
        print(f"  {arch}: +{(len(nb)-len(a.data)+SEC-1)//SEC} 섹터 필요 -> 제외 불가")
        sys.exit(1)
    out[arch] = nb + b'\0' * (len(a.data) - len(nb))
    print(f"  {arch}: 포함 (크기 유지)")

shutil.copyfile(ISO_SRC, ISO_DST)
with open(ISO_DST, 'r+b') as f:
    for s, e, n in iso.files():
        if n.endswith('/common.bin'):
            f.seek(s)
            f.write(cb)
    for arch, nb in out.items():
        rec_off, lba, size = recs[arch]
        assert size == len(nb)
        f.seek(lba * SEC)
        f.write(nb)
print(f"-> {os.path.basename(ISO_DST)}  ({os.path.getsize(ISO_DST):,}B, 구조 불변)")
