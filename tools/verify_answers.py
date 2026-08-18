# -*- coding: utf-8 -*-
"""추리가 실제로 풀리는지 검증한다 — 정답 키워드와 본문 분홍 글자 대조.

게임은 분홍 글자를 눌러 얻은 낱말을 문항(op 0x13)·착상(op 0x14) payload 안의
문자열과 **글자 그대로** 대조한다. 한 글자만 달라도 정답을 골라도 추리가
진행되지 않는다. 화면에 오류가 안 뜨고 그냥 안 넘어가므로 눈으로는 못 찾는다.

세 가지를 본다.

  (1) 정답표의 키워드가 **본문 조각과 같은가**
      원본 키워드를 본문에서 찾아 조각 구간을 구하고, 같은 구간의 한국어를
      이어 붙여 한글판 정답표의 값과 비교한다.

  (2) 같은 키워드가 여러 번 나오는데 **번역이 갈리지 않았는가**
      원문은 어느 쪽을 눌러도 글자가 같지만 번역이 갈리면 한쪽만 맞는다.
      BH 「ティアドロップ型のイヤリング」 가 그랬다 (#118 vs #1164).

  (3) 분홍 범위를 조각에 맞출 때 **정답표와 맞는 쪽을 골랐는가**
      길이가 같은 조각 조합이 이웃하면 keywordfix.match 의 델타 탐색이
      엉뚱한 쪽을 먼저 잡는다. KM 블록61 이 그랬다.

    python ../tools/verify_answers.py
"""
import paths
import json
import os
import sys

from isolib import Iso
from sectpack import from_iso
import keywordfix as kfx
import rawtext
import core
import answers

KR = paths.ISO_KR
REV = {int(v, 16): k for k, v in json.load(
    open(os.path.join(paths.TEXT, '_hangul_codes.json'),
         encoding='utf-8'))['map'].items()}


def dec_ko(bs):
    """한글이 올라탄 한자 코드를 되돌려 읽는다."""
    out, i, n = [], 0, len(bs)
    while i < n:
        b = bs[i]
        if ((0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC) and i + 1 < n
                and (0x40 <= bs[i + 1] <= 0x7E or 0x80 <= bs[i + 1] <= 0xFC)):
            code = (b << 8) | bs[i + 1]
            out.append(REV.get(code)
                       or bytes([b, bs[i + 1]]).decode('cp932', 'replace'))
            i += 2
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
            i += 1
        else:
            out.append('\uFFFD')
            i += 1
    return ''.join(out)


def _is_kw(t):
    return bool(t.strip()) and not t.startswith(('Q_', 'I_', 'SN', 'ENV_'))


def slots(iso, dec):
    """[(아카이브, 파일, 아이디, 키워드)] — 정답 키워드 자리마다 한 줄."""
    out = []
    for arch, name, op, ident, title, groups in answers.entries(iso):
        for g in groups:
            for s in g:
                if _is_kw(s.decode('cp932', 'replace')):
                    out.append((arch, name, ident.decode('ascii', 'replace'),
                                dec(s)))
    return out


def body():
    """{아카이브: [(파일, 이어붙인 일본어, 조각경계, [일본어], [한국어])]}"""
    idx = json.load(open(os.path.join(paths.TEXT, '_index.json'),
                         encoding='utf-8'))
    files = {}
    for meta in idx['files']:
        doc = json.load(open(os.path.join(paths.TEXT, meta['file']),
                             encoding='utf-8'))
        for r in doc['entries']:
            files.setdefault((r['archive'], r['file']), []).append(
                (int(r['index']), r.get('ja') or '', r.get('ko') or ''))
    out = {}
    for (arch, f), parts in files.items():
        parts.sort()
        jp = [rawtext.strip_tag(p[1]) for p in parts]
        kp = [p[2] for p in parts]
        cum, s = [0], 0
        for t in jp:
            s += len(t)
            cum.append(s)
        out.setdefault(arch, []).append((f, ''.join(jp), cum, jp, kp))
    return out


def check_slots(jp_iso, ko_iso):
    B = body()
    ja = slots(jp_iso, lambda b: b.decode('cp932', 'replace'))
    ko = slots(ko_iso, dec_ko)
    if len(ja) != len(ko):
        print('!! 키워드 자리 수가 다르다 %d vs %d' % (len(ja), len(ko)))
        return 1
    miss = notfound = 0
    for (a, n, i, kja), (_, _, _, kko) in zip(ja, ko):
        want = None
        for f, txt, cum, jp, kp in B.get(a, ()):
            pos = txt.find(kja)
            while pos >= 0:
                end = pos + len(kja)
                if pos in cum and end in cum:
                    x, y = cum.index(pos), cum.index(end)
                    want = ''.join(
                        rawtext.strip_tag(k) or rawtext.strip_tag(jp[m])
                        for m, k in enumerate(kp[x:y], start=x))
                    break
                pos = txt.find(kja, pos + 1)
            if want is not None:
                break
        if want is None:
            notfound += 1
        elif core.to_fullwidth(want) != kko:
            miss += 1
            print('!! %s/%s %s' % (a, n.split('/')[-1], i))
            print('     본문   %s' % core.to_fullwidth(want)[:56])
            print('     정답표 %s' % kko[:56])
    print('(1) 정답 키워드 %d자리 — 본문과 어긋남 %d / 본문에서 못 찾음 %d'
          % (len(ja), miss, notfound))
    return miss


def spans_of(iso, kws):
    """[(아카이브, 파일, 조각목록, 구간, 평범한구간)]"""
    out = []
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
                texts = [t for _, t in p]
                cumv = kfx.cum([len(t) for t in texts])
                good = kfx.match(rr, cumv, texts=texts, kws=kws)
                plain = kfx.match(rr, cumv)
                if not good:
                    continue
                out.append((arch, base, p, good, plain))
    return out


def main():
    jp_iso, ko_iso = Iso(), Iso(KR)
    bad = check_slots(jp_iso, ko_iso)

    kws = answers.keywords(jp_iso)
    ko_map = kfx.load_ko()
    seen, dup, wrong, tot = {}, 0, 0, 0
    for arch, base, p, good, plain in spans_of(jp_iso, kws):
        for k, (i, j) in enumerate(good):
            tot += 1
            kja = rawtext.strip_tag(''.join(t for _, t in p[i:j + 1]))
            kko = rawtext.strip_tag(''.join(
                core.to_fullwidth(ko_map.get((arch, base, ix)) or t)
                for ix, t in p[i:j + 1]))
            if kja and kko:
                key = (arch[:2], kja)
                if key in seen and seen[key] != kko:
                    dup += 1
                    print('!! [%s] %s 번역이 갈린다' % (arch[:2], kja[:40]))
                    print('     %s' % seen[key][:46])
                    print('     %s' % kko[:46])
                seen[key] = kko
            if plain:
                q = plain[k]
                tq = rawtext.strip_tag(''.join(t for _, t in p[q[0]:q[1] + 1]))
                if tq != kja and kja in kws:
                    wrong += 1
    print('(2) 분홍 키워드 %d종 — 번역이 갈린 것 %d' % (len(seen), dup))
    print('(3) 분홍 범위 %d개 — 정답표로 바로잡은 것 %d' % (tot, wrong))
    bad += dup
    print('')
    print('추리 진행 검증 통과' if bad == 0 else '!! 문제 %d건' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
