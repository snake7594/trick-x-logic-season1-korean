"""추리 데이터의 **키워드 이름**을 한국어 분홍 글자와 똑같이 맞춘다.

게임은 분홍 글자를 눌러 얻은 키워드를 `*_question.bin` 등에 적힌 문자열과
글자 그대로 대조한다. 본문만 한국어로 바꾸면 정답 조각을 골라도 추리가
진행되지 않는다 — 실제로 그 제보를 받았다.

    분홍 범위의 글자 - 제어 태그 = 키워드 이름

`*_keyword.bin` 의 범위(한국어 기준으로 다시 계산된 것)로 한국어 조각을
뽑아 같은 문자열로 바꿔 넣는다. 이름을 따로 번역하지 않고 **본문에서
그대로 떠 오는** 것이 핵심이다. 사람이 번역하면 한 글자만 달라도 안 맞는다.

    python ../tools/keyname.py   ->  keyname_payloads.pkl
"""
import paths
import os
import pickle
from collections import defaultdict

from isolib import Iso
from sectpack import from_iso
from prcs import SCENARIOS, has_jp
from lz import decompress
import struct
import json
import core
import keywordfix as kfx
import rawtext

# 키워드 이름이 들어 있는 파일
TARGETS = ('_question.bin', '_inspiration.bin', '_answer_data.bin',
           '_hint.bin', '_hint2.bin', '_report.bin')


def _reading(t):
    """정렬용 히라가나 읽기 — 화면에 안 나오므로 건드리지 않는다."""
    return all('぀' <= c <= 'ゟ' or c == 'ー' for c in t)


def pink_map(iso, ko_map):
    """{아카이브: {일본어 분홍조각: 한국어 분홍조각}} — 태그는 뺀 상태."""
    out = defaultdict(dict)
    for arch in kfx.ARCHIVES:
        sp = from_iso(iso, arch)
        for kf in [e for e in sp.ents if e['name'].endswith('_keyword.bin')]:
            base = kf['name'].replace('_keyword.bin', '.bin')
            try:
                se = sp.byname(base)
            except Exception:
                continue
            bl = kfx.blocks_of(sp.get(se))
            for bi, off, seg, rr in kfx.recs_of(bytearray(sp.get(kf)), len(bl)):
                p = bl[bi]['parts']
                spans = kfx.match(rr, kfx.cum([len(t) for _, t in p]))
                if not spans:
                    continue
                for (i, j) in spans:
                    ja = rawtext.strip_tag(''.join(t for _, t in p[i:j + 1]))
                    ko = rawtext.strip_tag(''.join(
                        core.to_fullwidth(ko_map.get((arch, base, idx)) or t)
                        for idx, t in p[i:j + 1]))
                    if ja and ko:
                        out[arch[:2]][ja] = ko
    return out


def build(ko_map, base=None, verbose=False):
    """base: {(archive, name): 번역된 바이트} — insert.py 결과를 밑바탕으로 쓴다.

    원본에서 만들면 같은 파일에 들어 있는 **대사 번역을 덮어써 버린다.**"""
    iso = Iso()
    base = base or {}
    pink = pink_map(iso, ko_map)
    allpink = {}
    for m in pink.values():
        allpink.update(m)
    titles = {}
    tp = os.path.join(paths.TEXT, 'rawtext.json')
    if os.path.exists(tp):
        titles = {k: v for k, v in
                  json.load(open(tp, encoding='utf-8')).items()
                  if not k.startswith('_') and v}
    out, stat = {}, defaultdict(int)
    for arch in SCENARIOS + ['common.bin']:
        try:
            sp = from_iso(iso, arch)
        except Exception:
            continue
        tag = arch[:2]
        for e in sp.ents:
            if '/script/' not in e['name'] or not e['name'].endswith('.bin'):
                continue
            d = base.get((arch, e['name']))
            if d is None:
                d = sp.get(e)
            elif d[:4] != b'PRCS':
                # insert.py 결과는 압축된 payload 다 — 풀어서 쓴다
                n, c = struct.unpack('<II', d[:8])
                d = decompress(d[8:8 + c], n)
            if d[:4] != b'PRCS':
                continue
            repl = {}
            # 번역표에 있는 것만 바꾸므로 짧은 이름(黒木 등)도 봐야 한다
            for off, t in rawtext.strings(d, minlen=1):
                if not has_jp(t) or _reading(t):
                    continue
                ko = pink.get(tag, {}).get(t) or allpink.get(t)
                kind = '키워드 이름'
                if not ko:
                    ko = titles.get(t)
                    kind = '제목·인물명'
                if not ko:
                    stat['번역 없음'] += 1
                    continue
                try:
                    repl[off] = core.encode(ko)
                except Exception as ex:
                    stat['인코딩 실패'] += 1
                    if verbose:
                        print(f"   ! {e['name']} {ko!r} {ex}")
                    continue
                stat[kind] += 1
            if repl:
                out[(arch, e['name'])] = rawtext.patch(d, repl)
    return out, stat


if __name__ == '__main__':
    base = {}
    if os.path.exists('new_scripts.pkl'):
        base = pickle.load(open('new_scripts.pkl', 'rb'))
        print(f"번역된 스크립트 {len(base)}개를 밑바탕으로 사용")
    payload, stat = build(kfx.load_ko(), base, verbose=True)
    pickle.dump(payload, open('keyname_payloads.pkl', 'wb'))
    print(dict(stat))
    print(f"-> keyname_payloads.pkl ({len(payload)} 파일)")
