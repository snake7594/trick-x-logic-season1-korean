"""원본 ISO 와 한글 ISO 의 문자열 목록을 위치별로 전부 대조한다."""
import paths
import json
import os
from isolib import Iso
from sectpack import SectPack, from_iso
from prcs import find_strings, has_jp, SCENARIOS

TEXT = paths.TEXT
m = json.load(open(os.path.join(TEXT, '_hangul_codes.json'),
                   encoding='utf-8'))['map']
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


iso_o = Iso(paths.ISO)
iso_n = Iso(paths.ISO_KR)


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

def align(lo, do, ln, dn):
    """원본 문자열 목록에 신규를 맞춘다. 못 맞추면 None.

    '길이 접두사 없는' 한국어 문자열은 앞 4바이트가 우연히 길이 필드처럼
    보여 신규에서만 문자열로 한 번 더 잡히는 일이 있다(op 0x3c 등). 위치로
    zip 하면 그 뒤가 통째로 밀리므로, **원본의 오프코드 순서**를 기준으로
    신규를 따라가며 남는 것만 건너뛴다."""
    out, j = [], 0
    for (l, _, _, _) in lo:
        op = do[l - 1]
        while j < len(ln) and dn[ln[j][0] - 1] != op:
            j += 1
        if j >= len(ln):
            return None
        out.append(ln[j])
        j += 1
    return out


# ── 명령 스트림 검사 ─────────────────────────────────────────────
# PRCS 는 `u8 명령 + u32 payload 길이 + payload` 의 연속이다. 문자열이 맞아도
# 이 길이가 어긋나면 해석기가 무너져 **게임이 부팅에서 죽는다.** 실제로
# 그렇게 죽였다(keyname/ruby 가 감싸는 명령의 u32 를 안 고쳤다). 문자열
# 대조만으로는 절대 안 잡히므로 반드시 같이 본다.
import prcswalk

walk_ok = walk_bad = 0
for a in SCENARIOS + ['common.bin']:
    so, sn = arch(iso_o, a), arch(iso_n, a)
    for e in sn.ents:
        if '/script/' not in e['name'] or not e['name'].endswith('.bin'):
            continue
        d = sn.get(e)
        if d[:4] != b'PRCS':
            continue
        if prcswalk.walk(d) is None:
            walk_bad += 1
            if walk_bad <= 5:
                print(f"  명령 스트림이 어긋남 {a} {e['name']}")
        else:
            walk_ok += 1
n_orig = sum(1 for a in SCENARIOS + ['common.bin'] for e in arch(iso_o, a).ents
             if '/script/' in e['name'] and e['name'].endswith('.bin')
             and arch(iso_o, a).get(e)[:4] == b'PRCS')
print(f"명령 스트림 정상 {walk_ok:,} / 어긋남 {walk_bad} (원본 {n_orig:,}개)")
if walk_ok != n_orig:
    print(f"  ! PRCS 파일 개수가 원본과 다름")

tot = same = changed = bad = 0
cnt_bad = 0
for (a, fname), rows in sorted(tr.items()):
    so = arch(iso_o, a)
    sn = arch(iso_n, a)
    do = so.get(so.byname(fname))
    dn = sn.get(sn.byname(fname))
    lo = find_strings(do)
    ln = align(lo, do, find_strings(dn), dn)
    if ln is None:
        cnt_bad += 1
        print(f"  문자열을 맞출 수 없음 {fname}")
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
