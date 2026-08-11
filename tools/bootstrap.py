"""ISO 에서 중간 산출물(common.bin, 원본 폰트)을 다시 뽑는다.

빌드 파이프라인을 처음부터 돌릴 때 가장 먼저 실행한다.
"""
import os
import struct
from isolib import Iso, SEC
from sectpack import SectPack

os.makedirs('out', exist_ok=True)
os.makedirs('font_out', exist_ok=True)

iso = Iso()
for s, e, n in iso.files():
    if n.endswith('/common.bin'):
        print(f"common.bin 추출 {e-s:,}B")
        iso.f.seek(s)
        left = e - s
        with open('common.bin', 'wb') as o:
            while left:
                b = iso.f.read(min(1 << 22, left))
                o.write(b)
                left -= len(b)

sp = SectPack(open('common.bin', 'rb').read())
for nm in ('NovelFontList.dat', 'AdvFontList.dat', 'NovelRubyFontList.dat'):
    ent = sp.byname('./script/Font/' + nm)
    open('out/' + nm, 'wb').write(sp.raw(ent))
    print(f"  out/{nm}  {ent['nsec']*SEC:,}B (comp={ent['comp']})")
print("\n완료. 다음: mapping.py -> build_font_kr.py -> insert.py -> build_iso.py")
