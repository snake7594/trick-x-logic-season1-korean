"""대사창이 2줄을 넘는 곳을 찾는다.

대사창 글자 영역은 화면에서 재서 **342px** 다(x70..412). 글자 진행 폭은
글리프 헤더의 `x1` — 한글 17px, 전각 공백 6px(`build_font_kr.SPACE_ADV`).
화면 화소로 확인했다.

    16글자×17 + 6공백×11 = 338px   ← 실제 첫 줄 폭과 일치(옛 공백 11px 기준)

소설 읽기 화면(`TU.bin` 같은 민짜 이름)은 여러 줄이 정상이라 뺀다. 그리고
**원문이 2줄에 들어가는 것만** 고칠 대상으로 본다 — 원문도 넘치는 자리는
애초에 2줄 화면이 아니다.

    python ../tools/advfit.py          # 목록
    python ../tools/advfit.py -v       # 조각별로 자세히
"""
import paths
import json
import os
import sys

from isolib import Iso
from sectpack import from_iso, SectPack
from prcs import SCENARIOS, find_strings, has_jp
from fonts import load, glyphs
from core import to_fullwidth
import prcswalk
import joints

W, G, SP = 342, 17, 6

# 대사창을 쓰는 스크립트
ADV = ('_prologue.bin', '_interval_0.bin', '_interval_1.bin', '_interval_2.bin',
       '_interval_3.bin', '_intro.bin', '_marunouchi.bin', '_tukasa.bin',
       '_bridge.bin', '_answer_begin.bin', '_giveup.bin', '_after_story.bin',
       '_trailer.bin', 'tutorial_msg.bin', 'yosikawa_suiri.bin',
       'tukasa_hint.bin')


def _ja_adv():
    d, _ = load('out/AdvFontList.dat')
    return {g['code']: g['x1'] for g in glyphs(d)}


def lines(t):
    """전각 공백으로 낱말을 갈라 줄 수를 센다."""
    n, cur, word = 1, 0, 0
    for ch in list(t) + ['　']:
        if ch == '　':
            if cur and cur + SP + word > W:
                n += 1
                cur = word
            else:
                cur += (SP if cur else 0) + word
            word = 0
        else:
            word += G
    return n


def scan():
    ja_adv = _ja_adv()

    def wja(t):
        s = 0
        for ch in t:
            try:
                c = int.from_bytes(ch.encode('cp932'), 'big')
            except Exception:
                c = None
            s += ja_adv.get(c, G)
        return s

    iso = Iso()
    idx = json.load(open(os.path.join(paths.TEXT, '_index.json'),
                         encoding='utf-8'))
    by = {}
    for m in idx['files']:
        doc = json.load(open(os.path.join(paths.TEXT, m['file']),
                             encoding='utf-8'))
        for r in doc['entries']:
            by.setdefault((r['archive'], r['file']), {})[r['index']] = r

    tot, out = 0, []
    for a in SCENARIOS + ['common.bin']:
        sp = joints.arch(iso, a)
        for e in sp.ents:
            base = e['name'].split('/')[-1]
            if not base.endswith(ADV):
                continue
            rows = by.get((a, e['name']))
            if not rows:
                continue
            d = sp.get(e)
            if d[:4] != b'PRCS':
                continue
            cmds = prcswalk.walk(d)
            at = {po: k for k, (oo, op, po, pl) in enumerate(cmds)}
            seq, ji = [], 0
            for lo, so, raw, t in find_strings(d):
                if has_jp(t):
                    seq.append((ji, at.get(so)))
                    ji += 1
            joined = dict(joints.pairs(d))
            used, groups = set(), []
            for i, k in seq:
                if i in used:
                    continue
                g = [i]
                used.add(i)
                while g[-1] in joined:
                    nx = joined[g[-1]]
                    if nx in used:
                        break
                    g.append(nx)
                    used.add(nx)
                groups.append(g)
            for g in groups:
                ko = ''.join(to_fullwidth(rows[i]['ko'] or '')
                             for i in g if i in rows)
                if not ko.strip():
                    continue
                tot += 1
                if lines(ko) <= 2:
                    continue
                ja = ''.join(rows[i]['ja'] for i in g if i in rows)
                if (wja(ja) + W - 1) // W > 2:      # 원문도 넘치면 2줄 화면 아님
                    continue
                px = sum(SP if c == '　' else G for c in ko)
                out.append(dict(file=base, idx=g, lines=lines(ko), px=px,
                                need=px - 2 * W, ko=ko, ja=ja))
    out.sort(key=lambda r: -r['need'])
    return tot, out


if __name__ == '__main__':
    tot, out = scan()
    print(f"대사창 덩어리 {tot:,} / 2줄 초과 {len(out):,} "
          f"({len(out)/max(tot,1):.1%})")
    if '-v' in sys.argv:
        idx = json.load(open(os.path.join(paths.TEXT, '_index.json'),
                             encoding='utf-8'))
        rows = {}
        for m in idx['files']:
            doc = json.load(open(os.path.join(paths.TEXT, m['file']),
                                 encoding='utf-8'))
            for r in doc['entries']:
                rows.setdefault(r['file'].split('/')[-1], {})[r['index']] = r
        for i, w in enumerate(out):
            print(f"[{i}] {w['file']} {w['idx']}  {w['need']:+}px "
                  f"({max(1,(w['need']+16)//17)}자)")
            print(f"    ja {w['ja']}")
            for j in w['idx']:
                print(f"    {j:>5}  {rows[w['file']][j]['ko']!r}")
    else:
        for w in out[:40]:
            print(f"  {w['need']:+5}px {w['file']:<22}{w['idx'][0]:>5}  "
                  f"{w['ko'][:44]}")
