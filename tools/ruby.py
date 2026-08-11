"""한자 읽기(루비)를 지운다.

본문 문자열 사이에 이런 짝이 들어 있다.

    0x32  09 00 00 00  u32 덮는글자수  <읽기 cp932> NUL
    op 0x01  u32 길이  <읽는 대상 글자> NUL
    0x33  00 00 00 00

한국어 본문 위에 일본어 가나가 그대로 뜨므로 지워야 한다. 짝 구조를 건드리면
위험하니 **읽기 문자열만 빈 문자열로** 만든다(NUL 만 남긴다). 명령을 통째로
빼면 뒤따르는 0x33 이 짝을 잃는다.

전체 128개 — TU 1, NF 7, FW 20, FW_A 1, KM 45, KM_A 1, SI 22, BH 19, BJ 12.

키워드 위치(δ)와는 무관하다. δ 는 줄바꿈 명령 `27 01 00 00 00` 의 개수이고
(682곳 중 681곳 일치로 확인), 루비는 δ 에 관여하지 않는다.

    python ../tools/ruby.py   ->  ruby_payloads.pkl
"""
import paths
import os
import pickle
import struct
from collections import Counter

from isolib import Iso
from sectpack import from_iso
from lz import decompress
from prcs import SCENARIOS

HEAD = bytes([0x32, 0x09, 0x00, 0x00, 0x00])
KANA_OK = set('ー')


def _kana(t):
    return bool(t) and all('぀' <= c <= 'ヿ' or c in KANA_OK for c in t)


def spans(d):
    """[(읽기 시작, 끝)] — 지울 가나 문자열 위치. NUL 은 남긴다."""
    out, i = [], 0
    while True:
        i = d.find(HEAD, i)
        if i < 0:
            return out
        o = i + len(HEAD) + 4          # 덮는 글자수 u32 를 건너뛴다
        j = d.find(b'\x00', o)
        if j < 0 or j == o or j - o > 24:
            i += 1
            continue
        try:
            t = d[o:j].decode('cp932')
        except Exception:
            i += 1
            continue
        if _kana(t):
            out.append((o, j))
        i = j + 1


def drop(d):
    """(새 바이트열, 지운 개수)"""
    sp = spans(d)
    if not sp:
        return bytes(d), 0
    out, pos = bytearray(), 0
    for a, b in sp:
        out += d[pos:a]
        pos = b
    out += d[pos:]
    return bytes(out), len(sp)


def build(base=None):
    """base 를 밑바탕으로(없으면 원본) 루비를 지운 payload 를 만든다."""
    iso = Iso()
    base = base or {}
    out, stat = {}, Counter()
    for arch in SCENARIOS + ['common.bin']:
        try:
            sp = from_iso(iso, arch)
        except Exception:
            continue
        for e in sp.ents:
            if '/script/' not in e['name'] or not e['name'].endswith('.bin'):
                continue
            d = base.get((arch, e['name']))
            if d is None:
                d = sp.get(e)
            elif d[:4] != b'PRCS':
                n, c = struct.unpack('<II', d[:8])
                d = decompress(d[8:8 + c], n)
            if d[:4] != b'PRCS':
                continue
            new, n = drop(d)
            if n:
                out[(arch, e['name'])] = new
                stat[arch] += n
    return out, stat


if __name__ == '__main__':
    base = {}
    for f in ('new_scripts.pkl', 'keyname_payloads.pkl'):
        if os.path.exists(f):
            base.update(pickle.load(open(f, 'rb')))
    print(f"밑바탕 {len(base)}개")
    payload, stat = build(base)
    pickle.dump(payload, open('ruby_payloads.pkl', 'wb'))
    print(dict(stat), '합계', sum(stat.values()))
    print(f"-> ruby_payloads.pkl ({len(payload)} 파일)")
