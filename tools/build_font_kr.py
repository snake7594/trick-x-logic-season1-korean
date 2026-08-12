"""한글 글리프를 '원본 한자 코드'에 얹어 폰트를 만든다.

코드는 하나도 바꾸지 않으므로, 배정되지 않은 한자는 원본 글리프가 그대로 남아
흰 박스 문제가 생기지 않는다.
"""
import paths
import os
import json
import struct
from collections import Counter
from fonts import load, glyphs
from lz import compress, decompress
from ptr import write_ptrlist
from build_font import render

TEXT = paths.TEXT
KANJI0 = 0x889F

# 전각 공백(0x8140)의 진행 폭을 반각 공백(0x0020)과 같게 만든다.
# 환경변수 TXL_HALF_SPACE=1 로 켠다.
HALF_SPACE = os.environ.get('TXL_HALF_SPACE') == '1'


def _half_space(recs, gl):
    """0x8140 레코드의 폭 필드를 0x0020 과 똑같이 맞춘다.

    게임은 **비례 폭**으로 그리고 진행 폭은 글리프 헤더의 `x1`(rec[8])이다.
    화면에서 재 보면 한글 글자 17px, 전각 공백 11px 로 헤더 값과 정확히
    맞는다(AdvFont 기준). 반각 공백은 8px 다.

    문자 자체를 반각으로 바꾸면 게임이 오작동한다는 기록이 있어서, **문자는
    전각 그대로 두고 글리프의 진행 폭만** 반각과 같게 만든다. 텍스트도
    스크립트도 한 바이트 안 바뀐다.

        rec[6]=x0  rec[8]=x1(진행 폭)   rec[13],[15] = 세로쓰기용 같은 값
    """
    idx = {g['code']: i for i, g in enumerate(gl)}
    if 0x8140 not in idx or 0x0020 not in idx:
        return recs
    hw = recs[idx[0x0020]]
    fw = bytearray(recs[idx[0x8140]])
    before = fw[8]
    for k in (6, 8, 13, 15):
        fw[k] = hw[k]
    recs = list(recs)
    recs[idx[0x8140]] = bytes(fw)
    print(f"   전각 공백 진행 폭 {before} -> {fw[8]} (반각과 동일)")
    return recs

m = json.load(open(os.path.join(TEXT, '_hangul_codes.json'), encoding='utf-8'))['map']
h2c = {ch: int(v, 16) for ch, v in m.items()}
c2h = {v: k for k, v in h2c.items()}
print(f"한글 배정 {len(h2c):,}자")


def build(name, fn, bw, bh):
    d, kind = load('out/' + fn)
    gl = glyphs(d)
    sub = struct.unpack('<I', d[4:8])[0]
    cnt = struct.unpack('<I', d[sub:sub + 4])[0]
    offs = list(struct.unpack(f'<{cnt}I', d[sub + 8:sub + 8 + cnt * 4]))

    # 이 폰트에 실제로 존재하는 코드만 대상
    present = {g['code'] for g in gl}
    targets = [c for c in sorted(c2h) if c in present]
    chars = [c2h[c] for c in targets]
    print(f"   교체 대상 {len(targets):,}자")

    # 최빈 한자 메트릭을 템플릿으로
    kan = [g for g in gl if g['code'] >= KANJI0]
    key = Counter((g['w'], g['h'], g['x0'], g['y0'], g['x1'], g['y1'])
                  for g in kan).most_common(1)[0][0]
    tg = next(g for g in kan
              if (g['w'], g['h'], g['x0'], g['y0'], g['x1'], g['y1']) == key)
    thdr = bytearray(d[offs[tg['i']]:offs[tg['i']] + 16])
    print(f"   템플릿 0x{tg['code']:04X} {tg['w']}x{tg['h']} "
          f"hdr={bytes(thdr).hex(' ')}")

    size, bmps, stride = render(chars, bw, bh)
    bmp_of = dict(zip(targets, bmps))
    print(f"   한글 렌더 {bw}x{bh}, TTF size={size}")

    recs = []
    for i, g in enumerate(gl):
        if g['code'] in bmp_of:
            r = bytearray(thdr)
            r[0] = g['code'] & 0xFF
            r[1] = g['code'] >> 8
            r[2] = 1                      # 세로 전용 자형 없음
            r[4], r[5] = bw, bh
            r += bmp_of[g['code']]
            while len(r) % 4:
                r.append(0)
            recs.append(bytes(r))
        else:
            recs.append(d[offs[i]:offs[i] + g['reclen']])

    if HALF_SPACE:
        recs = _half_space(recs, gl)

    # SIR0 재조립 (코드 순서·개수 그대로)
    body = bytearray(b'SIR0' + b'\0' * 28)
    table = []
    for r in recs:
        table.append(len(body))
        body += r
    subo = len(body)
    body += struct.pack('<II', len(recs), 0)
    for o in table:
        body += struct.pack('<I', o)
    while len(body) % 16:
        body.append(0xAA)
    ptro = len(body)
    body += write_ptrlist([4, 8] + [subo + 8 + i * 4 for i in range(len(recs))])
    while len(body) % 16:
        body.append(0xAA)
    body[4:12] = struct.pack('<II', subo, ptro)
    body = bytes(body)

    # 검증
    g2 = glyphs(body)
    assert len(g2) == len(gl), '글리프 수 변경'
    assert [x['code'] for x in g2] == [x['code'] for x in gl], '코드 변경'
    assert all(x['calc'] == x['reclen'] for x in g2), '레코드 크기 오류'
    comp = compress(body)
    assert decompress(comp, len(body)) == body, '압축 왕복 실패'
    payload = struct.pack('<II', len(body), len(comp)) + comp
    print(f"   {len(body):,}B -> 압축 {len(payload):,}B "
          f"({(len(payload)+2047)//2048} 섹터)")
    open(f'font_out/{name}_KR.payload', 'wb').write(payload)
    open(f'font_out/{name}_KR.sir0', 'wb').write(body)
    return payload


tot = 0
for name, fn, bw, bh in (('NovelFont', 'NovelFontList.dat', 20, 20),
                         ('AdvFont', 'AdvFontList.dat', 17, 17)):
    print(f"=== {name}")
    tot += (len(build(name, fn, bw, bh)) + 2047) // 2048
ruby = (len(open('out/NovelRubyFontList.dat', 'rb').read()) + 2047) // 2048
print(f"\n합계 {tot + ruby} 섹터 / 가용 402  "
      f"-> {'OK' if tot + ruby <= 402 else '초과!'}")
