"""원본 ISO 와 한글 ISO 의 문자열 목록을 위치별로 전부 대조한다."""
import paths
import json
import os
from isolib import Iso
from sectpack import SectPack, from_iso
from prcs import find_strings, has_jp

GAME = paths.ROOT
TEXT = GAME + r'\text'
m = json.load(open(TEXT + r'\_hangul_codes.json', encoding='utf-8'))['map']
C2H = {int(v, 16): k for k, v in m.items()}


def decode_kr(raw):
    out, i, n = [], 0, len(raw)
    while i < n:
        c = raw[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF) and i + 1 < n:
            code = (c << 8) | raw[i + 1]
            out.append(C2H.get(code) or bytes(raw[i:i + 2]).decode('cp932'))
            i += 2
        else:
            out.append(bytes([c]).decode('cp932'))
            i += 1
    return ''.join(out)


iso_o = Iso(GAME + r'\Trick x Logic Season 1.iso')
iso_n = Iso(GAME + r'\Trick x Logic Season 1 (KR).iso')


def arch(iso, name):
    if name == 'common.bin':
        for s, e, n in iso.files():
            if n.endswith('/common.bin'):
                iso.f.seek(s)
                return SectPack(iso.f.read(e - s))
    return from_iso(iso, name)


idx = json.load(open(os.path.join(TEXT, '_index.json'), encoding='utf-8'))
tr = {}
for meta in idx['files']:
    doc = json.load(open(os.path.join(TEXT, meta['file']), encoding='utf-8'))
    for r in doc['entries']:
        tr.setdefault((r['archive'], r['file']), []).append(r)

tot = same = changed = bad = 0
cnt_bad = 0
for (a, fname), rows in sorted(tr.items()):
    so = arch(iso_o, a)
    sn = arch(iso_n, a)
    do = so.get(so.byname(fname))
    dn = sn.get(sn.byname(fname))
    lo = find_strings(do)
    ln = find_strings(dn)
    if len(lo) != len(ln):
        cnt_bad += 1
        print(f"  문자열 개수 불일치 {fname}: 원본 {len(lo)} vs 신규 {len(ln)}")
        continue
    ko_iter = iter(sorted(rows, key=lambda r: r['index']))
    for (_, _, ro, to), (_, _, rn, tn) in zip(lo, ln):
        tot += 1
        dec = decode_kr(rn)
        if has_jp(to):                       # 번역 대상이었던 문자열
            exp = next(ko_iter)
            # 삽입 시 반각 -> 전각 치환이 적용되므로 기대값도 맞춘다
            from core import to_fullwidth
            want = to_fullwidth(exp['ko'] or exp['ja'])
            if want == exp['ja']:
                # 원문 유지(제어 태그 등) — 바이트가 그대로여야 한다.
                # 한자 코드가 한글 배정과 겹쳐 decode_kr 로는 비교할 수 없음.
                if ro == rn:
                    changed += 1
                else:
                    bad += 1
                    if bad <= 5:
                        print(f"  원문유지인데 바이트가 바뀜 {exp['id']}")
            elif dec == want:
                changed += 1
            else:
                bad += 1
                if bad <= 5:
                    print(f"  불일치 {exp['id']}: 기대 {len(want)}자 / 실제 {len(dec)}자")
        else:                                 # 리소스 이름 등 — 그대로여야 함
            if ro == rn:
                same += 1
            else:
                bad += 1
                if bad <= 5:
                    print(f"  비번역 문자열이 변경됨 {fname}")

print(f"\n총 문자열 {tot:,}")
print(f"  번역 반영 정확 {changed:,}")
print(f"  비번역 원본유지 {same:,}")
print(f"  불일치 {bad:,} / 파일 개수 불일치 {cnt_bad}")
print("\n엄밀 검증 통과" if bad == 0 and cnt_bad == 0 else "\n문제 있음")
