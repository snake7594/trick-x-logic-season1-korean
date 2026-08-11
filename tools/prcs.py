"""PRCS 스크립트에서 길이 접두 문자열을 뽑는다.

레이아웃:  u32 len(널 포함)  |  cp932 바이트열  |  0x00
"""
import struct

MAXLEN = 8192


def find_strings(d):
    """[(len_off, str_off, raw, text)]"""
    out, i, n = [], 0, len(d)
    while i + 8 <= n:
        v = struct.unpack('<I', d[i:i + 4])[0]
        if 2 <= v <= MAXLEN and i + 4 + v <= n and d[i + 4 + v - 1] == 0:
            raw = d[i + 4:i + 4 + v - 1]
            if 0 not in raw and all(c >= 0x20 or c == 0x0A for c in raw):
                try:
                    t = raw.decode('cp932')
                except Exception:
                    i += 1
                    continue
                out.append((i, i + 4, raw, t))
                i += 4 + v
                continue
        i += 1
    return out


def has_jp(t):
    return any(ord(c) > 0x7F for c in t)


SCENARIOS = ['TU.bin', 'TU_A.bin', 'NF.bin', 'NF_A.bin', 'FW.bin', 'FW_A.bin',
             'KM.bin', 'KM_A.bin', 'SI.bin', 'SI_A.bin', 'BH.bin',
             'BJ.bin', 'BJ_A.bin']


if __name__ == '__main__':
    from collections import Counter
    from isolib import Iso
    from sectpack import from_iso, SectPack

    iso = Iso()
    tot_str = tot_jp = 0
    ctrl = Counter()
    linelens = Counter()
    nlines = Counter()
    per_arch = []

    def scan(sp, label):
        global tot_str, tot_jp
        n_s = n_j = 0
        for e in sp.ents:
            if not e['name'].endswith('.bin') or '/script/' not in e['name']:
                continue
            d = sp.get(e)
            if d[:4] != b'PRCS':
                continue
            for lo, so, raw, t in find_strings(d):
                n_s += 1
                if has_jp(t):
                    n_j += 1
                    for c in t:
                        if ord(c) < 0x20:
                            ctrl[hex(ord(c))] += 1
                    parts = t.split('\n')
                    nlines[len(parts)] += 1
                    for p in parts:
                        linelens[len(p)] += 1
        tot_str += n_s
        tot_jp += n_j
        per_arch.append((label, n_s, n_j))

    for nm in SCENARIOS:
        scan(from_iso(iso, nm), nm)
    scan(SectPack(open('common.bin', 'rb').read()), 'common.bin')

    for label, s, j in per_arch:
        print(f"  {label:<12} 문자열 {s:>6,}  일본어 {j:>6,}")
    print(f"\n합계 문자열 {tot_str:,} / 일본어 {tot_jp:,}")
    print(f"\n제어문자: {dict(ctrl)}")
    print(f"\n줄 수 분포(상위): {nlines.most_common(8)}")
    mx = max(linelens)
    print(f"한 줄 글자수: 최대 {mx}, 분포 상위 {linelens.most_common(6)}")
    over = sum(c for L, c in linelens.items() if L > 30)
    print(f"30자 초과 줄: {over}")
