"""한자 슬롯을 한글 완성형 2350자로 교체한 폰트를 생성한다."""
import paths
import struct
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
from fonts import load, glyphs, to_img
from lz import compress, decompress
from ptr import read_ptrlist, write_ptrlist

TTF = paths.TTF_GAME
KANJI0 = 0x889F
# 게임은 글리프 알파를 그대로 그리는데, **가장자리의 중간값이 검은 외곽선**
# 으로 보인다. 원본 한자 획 단면이 `7 F 7` 인 것이 그 증거다.
#
# 여기서 세 번 헛짚었다.
#   1. 굵게(BOLD=1.55)  — 흰 획만 두꺼워지고 외곽선은 그대로
#   2. 0/15 이진화       — 중간값이 없어져 **외곽선이 사라졌다**
#   3. 속 F + 테 7 조립  — 계조가 없어 거칠고, 획 사이 빈 곳까지 테로 메워
#                          **외곽선이 글자 안으로 파고들었다**
#
# 결국 답은 **원본과 같은 값 분포를 만드는 것**이었다. 계조는 그대로 두고
# 감마로 가장자리 값만 낮춘다. 원본 한자와 대조해 맞춘 값이다(잉크 화소 기준).
#
#            속(≥C)   테(4~9)   평균
#   원본       29.1%    37.5%     7.8
#   B γ1.4     29.1%    36.8%     7.8
#
# 굵기도 여기서 정해진다 — ExtraBold 는 너무 굵고 Medium 은 너무 가늘다.
GAMMA = 1.4

# KS X 1001 완성형 2350자 (EUC-KR 0xB0A1..0xC8FE)
HAN = [bytes([hi, lo]).decode('euc-kr')
       for hi in range(0xB0, 0xC9) for lo in range(0xA1, 0xFF)]
assert len(HAN) == 2350


def sjis_seq(n, start=KANJI0):
    """start부터 유효한 Shift-JIS 2바이트 코드 n개."""
    out, lead, trail = [], start >> 8, start & 0xFF
    while len(out) < n:
        if 0x40 <= trail <= 0x7E or 0x80 <= trail <= 0xFC:
            out.append((lead << 8) | trail)
        trail += 1
        if trail > 0xFC:
            trail, lead = 0x40, lead + 1
    return out


def fit(chars, bw, bh):
    """박스(bw,bh)에 전부 들어가는 최대 폰트 크기와 기준 원점."""
    for size in range(bh + 12, 5, -1):
        f = ImageFont.truetype(TTF, size)
        W = H = size * 4
        ox, oy = size, size * 2
        x0 = y0 = 1 << 30
        x1 = y1 = -(1 << 30)
        for ch in chars:
            im = Image.new('L', (W, H), 0)
            ImageDraw.Draw(im).text((ox, oy), ch, font=f, fill=255, anchor='ls')
            bb = im.getbbox()
            if bb:
                x0, y0 = min(x0, bb[0]), min(y0, bb[1])
                x1, y1 = max(x1, bb[2]), max(y1, bb[3])
        if x1 - x0 <= bw and y1 - y0 <= bh:
            return size, (ox, oy), (x0, y0, x1, y1)
    raise SystemExit('맞는 크기 없음')


def render(chars, bw, bh):
    """각 글자를 bw x bh 박스에 4bpp 비트맵으로."""
    size, (ox, oy), (bx0, by0, bx1, by1) = fit(chars, bw, bh)
    padx = (bw - (bx1 - bx0)) // 2
    pady = (bh - (by1 - by0)) // 2
    f = ImageFont.truetype(TTF, size)
    W = H = size * 4
    stride = (bw + 1) // 2
    out = []
    for ch in chars:
        im = Image.new('L', (W, H), 0)
        ImageDraw.Draw(im).text((ox, oy), ch, font=f, fill=255, anchor='ls')
        cell = Image.new('L', (bw, bh), 0)
        cell.paste(im.crop((bx0 - padx, by0 - pady,
                            bx0 - padx + bw, by0 - pady + bh)), (0, 0))
        # 계조는 그대로, 감마로 가장자리 값만 낮춘다. 위 GAMMA 설명 참고.
        px = cell.load()
        bmp = bytearray(stride * bh)
        for y in range(bh):
            for x in range(bw):
                v = round(15 * (px[x, y] / 255) ** GAMMA)
                if v:
                    bmp[y * stride + (x >> 1)] |= v << (4 if x & 1 else 0)
        out.append(bytes(bmp))
    return size, out, stride


def build(name, fn, bw, bh):
    d, kind = load('out/' + fn)
    gl = glyphs(d)
    keep = [g for g in gl if g['code'] < KANJI0]
    kan = [g for g in gl if g['code'] >= KANJI0]

    # 최빈 한자 메트릭을 템플릿으로 (헤더 16바이트 그대로 재사용)
    key = Counter((g['w'], g['h'], g['x0'], g['y0'], g['x1'], g['y1'])
                  for g in kan).most_common(1)[0][0]
    tmpl = next(g for g in kan
                if (g['w'], g['h'], g['x0'], g['y0'], g['x1'], g['y1']) == key)
    thdr = d[0:0]  # placeholder
    raw = None
    for g in gl:
        if g is tmpl:
            break
    # 템플릿 레코드의 원본 16바이트를 얻는다
    sub = struct.unpack('<I', d[4:8])[0]
    cnt = struct.unpack('<I', d[sub:sub + 4])[0]
    offs = list(struct.unpack(f'<{cnt}I', d[sub + 8:sub + 8 + cnt * 4]))
    thdr = bytearray(d[offs[tmpl['i']]:offs[tmpl['i']] + 16])
    print(f"   템플릿 0x{tmpl['code']:04X}: w={tmpl['w']} h={tmpl['h']} "
          f"x0={tmpl['x0']} y0={tmpl['y0']} x1={tmpl['x1']} y1={tmpl['y1']} "
          f"hdr={bytes(thdr).hex(' ')}")

    size, bmps, stride = render(HAN, bw, bh)
    print(f"   한글 렌더: {bw}x{bh}, TTF size={size}, stride={stride}")

    codes = sjis_seq(2350)
    print(f"   한글 코드: 0x{codes[0]:04X} .. 0x{codes[-1]:04X}")

    recs = []
    for g in keep:
        recs.append((g['code'], d[offs[g['i']]:offs[g['i']] + g['reclen']]))
    for code, bmp in zip(codes, bmps):
        r = bytearray(thdr)
        r[0] = code & 0xFF
        r[1] = code >> 8
        r[2] = 1              # flag=1: 세로 전용 자형 없음
        r[4], r[5] = bw, bh
        r += bmp
        while len(r) % 4:
            r.append(0)
        recs.append((code, bytes(r)))
    recs.sort(key=lambda t: t[0])
    assert len({c for c, _ in recs}) == len(recs), '코드 중복'

    # SIR0 조립
    body = bytearray(b'SIR0' + b'\0' * 28)   # 0x20까지 헤더+패딩
    offsets = []
    for _, r in recs:
        offsets.append(len(body))
        body += r
    subo = len(body)   # 레코드는 4바이트 정렬이라 그대로 이어붙임 (원본과 동일)
    body += struct.pack('<II', len(recs), 0)
    for o in offsets:
        body += struct.pack('<I', o)
    while len(body) % 16:
        body.append(0xAA)
    ptro = len(body)
    body += write_ptrlist([4, 8] + [subo + 8 + i * 4 for i in range(len(recs))])
    while len(body) % 16:
        body.append(0xAA)
    body[4:12] = struct.pack('<II', subo, ptro)
    body = bytes(body)

    # 검증: 다시 파싱
    gl2 = glyphs(body)
    assert len(gl2) == len(recs), 'glyph count'
    assert all(g['calc'] == g['reclen'] for g in gl2), 'record size'
    p2, _ = read_ptrlist(body, ptro)
    assert p2 == [4, 8] + [subo + 8 + i * 4 for i in range(len(recs))], 'ptrlist'

    comp = compress(body)
    assert decompress(comp, len(body)) == body, 'compress roundtrip'
    payload = struct.pack('<II', len(body), len(comp)) + comp
    print(f"   글리프 {len(recs)} (원본유지 {len(keep)} + 한글 2350)")
    print(f"   무압축 {len(body):,}B -> 압축 {len(payload):,}B "
          f"({len(payload)/len(body)*100:.1f}%) = {(len(payload)+2047)//2048} 섹터")
    return body, payload, gl2


if __name__ == '__main__':
    import pickle
    res = {}
    for name, fn, bw, bh in (('NovelFont', 'NovelFontList.dat', 20, 20),
                             ('AdvFont', 'AdvFontList.dat', 17, 17)):
        print(f"=== {name}")
        body, payload, gl2 = build(name, fn, bw, bh)
        open(f'font_out/{name}_KR.sir0', 'wb').write(body)
        open(f'font_out/{name}_KR.payload', 'wb').write(payload)
        res[name] = len(payload)
        print()
    ruby = len(open('out/NovelRubyFontList.dat', 'rb').read())
    tot = sum((v + 2047) // 2048 for v in res.values()) + (ruby + 2047) // 2048
    print(f"3개 폰트 합계 {tot} 섹터 / 가용 402 섹터  -> "
          f"{'OK, 여유 %d섹터' % (402-tot) if tot <= 402 else '초과!'}")
