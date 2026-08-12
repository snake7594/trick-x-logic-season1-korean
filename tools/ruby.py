"""한자 읽기(루비)를 지운다.

본문 문자열 사이에 이런 짝이 들어 있다.

    op 0x32  u32 payload길이  [ u32 읽기개수 | (<읽기 cp932> NUL) × 개수 ]
    op 0x01  u32 길이         <읽는 대상 글자> NUL
    op 0x33  00 00 00 00

한국어 본문 위에 일본어 가나가 그대로 뜨므로 지워야 한다. 짝 구조를 건드리면
위험하니 **읽기 글자를 전각 공백으로 바꾼다**. 명령을 통째로 빼면 뒤따르는
0x33 이 짝을 잃는다.

⚠ 처음에는 읽기를 **빈 문자열**로 만들었다(NUL 만 남김). 그랬더니 소설 읽기
화면이 **첫 루비에서 멈췄다**(제보 #4 — 제1장 제목 다음 쪽. TU.bin 블록 1 의
`えつらん` 이 게임에서 처음 만나는 루비다). 길이 0 인 읽기를 해석기가 감당하지
못하는 것으로 보인다.

가나는 cp932 에서 모두 2바이트이고 전각 공백도 2바이트다. 그래서 지금 방식은
**payload 길이가 1바이트도 안 변하고** 명령 구조도 원본 그대로다. 글자 폭도
같아서 배치가 흔들리지 않고, 화면에는 아무것도 안 보인다.

전체 561개. 예전에는 `0x32 09 00 00 00` 을 바이트로 찾아서 payload 길이가
9(가나 두 자)인 것만 128개 잡았고, 나머지 433개는 화면에 그대로 남아 있었다.

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
import prcswalk

RUBY = 0x32
KANA_OK = set('ー')


def _kana(t):
    return bool(t) and all('぀' <= c <= 'ヿ' or c in KANA_OK for c in t)


def spans(d):
    """[(읽기 시작, 끝)] — 지울 가나 문자열 위치. NUL 은 남긴다."""
    cmds = prcswalk.walk(d)
    if cmds is None:
        return []
    out = []
    for oo, op, po, pl in cmds:
        if op != RUBY or pl <= 5:
            continue
        # payload = u32 읽기개수 + (읽기 NUL) × 개수. 한 명령에 **두 개 이상**
        # 들어 있는 경우가 있다(`ろ` + `けん`). 하나로 보고 통째로 읽으면
        # 가운데 NUL 때문에 가나 판정에 걸려 그냥 지나쳤다.
        n = struct.unpack('<I', d[po:po + 4])[0]
        o, end = po + 4, po + pl
        for _ in range(max(n, 1)):
            if o >= end:
                break
            j = d.find(bytes([0]), o, end)
            if j < 0:
                break
            if j > o:
                try:
                    t = d[o:j].decode('cp932')
                except Exception:
                    t = None
                if t and _kana(t):
                    out.append((o, j))
            o = j + 1
    return out


SP2 = b'\x81\x40'          # cp932 전각 공백 — 가나와 같은 2바이트


def drop(d):
    """(새 바이트열, 지운 개수) — 길이는 그대로 두고 가나만 전각 공백으로."""
    sp = spans(d)
    if not sp:
        return bytes(d), 0
    out = bytearray(d)
    for a, b in sp:
        assert (b - a) % 2 == 0, f'가나가 2바이트가 아니다 @0x{a:x}'
        out[a:b] = SP2 * ((b - a) // 2)
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
