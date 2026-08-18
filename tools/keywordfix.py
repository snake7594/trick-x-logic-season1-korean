"""키워드(분홍 글자) 범위를 한국어 위치로 다시 계산한다.

`*_keyword.bin` 구조
--------------------
    u32 count       # 스크립트 블록 수(라벨 0x0f 구간 수 - 1)
    u32 0
    레코드 × count  # 블록 순서 그대로 1:1. 첫 블록(*_01_0000, 제목)은 제외
      type == 0 : u32 0 만 (그 블록엔 분홍 글자 없음)
      type == 1 : u32 1, u8 cnt, u16 pad, u8 seg, cnt × {u8 start, u8 end, u32 pad}

`start`/`end` 는 그 블록 본문의 **글자 인덱스**(끝 포함)이고, 원문에서 재보면
언제나 조각(0x01 문자열) 경계에 정확히 맞는다 — 430/430 확인.

다만 게임이 세는 인덱스에는 루비(op 0x09, 한자 읽기)마다 한 글자씩 더 들어
있다. 그 차이를 δ 라 하면

    start = (조각 p0 앞까지의 길이) - δ

이고, δ 는 **레코드가 아니라 범위마다** 다르다(앞쪽 루비가 쌓이므로 블록 안에서
0 부터 단조 감소한다).

δ 가 무엇인지 알아낼 필요는 없다. δ 를 만드는 요소(오프코드·루비·마커)는
번역이 건드리지 않으므로 한국어에서도 그대로다. 그래서 **조각 경계에서의
한·일 길이 차이만큼 범위를 밀어 주면** δ 가 자동으로 보존된다.

    새 start = start + (한국어 p0 앞까지 길이 - 일본어 p0 앞까지 길이)
    새 end   = end   + (한국어 p1 까지 길이   - 일본어 p1 까지 길이)
"""
import paths
import json
import os
import pickle
import struct
from collections import defaultdict

from isolib import Iso
from sectpack import from_iso
import prcs
import core
import rawtext
import answers

TEXT = paths.TEXT
U8 = 255
DELTAS = (0, -1, 1, -2, 2, -3, 3, -4, 4)


def blocks_of(d):
    """[{label, parts:[(문자열 index, 원문)]}] — 라벨(op 0f) 로 나눈 블록."""
    out, cur, i = [], None, 0
    for (lo, so, raw, t) in prcs.find_strings(d):
        op = d[lo - 1]
        if op == 0x0f:
            cur = {'label': t, 'parts': []}
            out.append(cur)
        elif op == 0x01 and cur is not None:
            cur['parts'].append((i, t))
        if op == 0x01:
            i += 1
    return out


def recs_of(k, nblock):
    """[(블록번호, 오프셋, seg, [(start, end)])] — 블록 순서 1:1, type 1 만."""
    out, off, bi = [], 8, 1
    while off + 4 <= len(k) and bi < nblock:
        typ = struct.unpack('<I', k[off:off + 4])[0]
        if typ != 1:
            off += 4
            bi += 1
            continue
        cnt = k[off + 4]
        seg = k[off + 7]
        rr = [(k[off + 8 + j * 6], k[off + 9 + j * 6]) for j in range(cnt)]
        base = off
        off += 8 + cnt * 6
        if rr:
            out.append((bi, base, seg, rr))
        bi += 1
    return out


def cum(lens):
    b = [0]
    for n in lens:
        b.append(b[-1] + n)
    return b


def match(rec_ranges, ja_cum, maxins=40, texts=None, kws=None):
    """범위가 덮는 조각 구간 [(i, j)] 를 찾는다. 못 찾으면 None.

    δ 는 범위마다 0 부터 단조 감소한다(앞쪽 루비 개수). 이전 범위의 δ 에서
    출발해 아래로 내려가며 **양 끝이 모두 조각 경계에 맞는** 첫 δ 를 쓴다.

    ⚠ 길이가 같은 조각 조합이 이웃하면 첫 δ 가 엉뚱한 쪽일 수 있다.

        KM 블록61  범위 (108,126) = 19글자
          조각 366+367  「桟」+「が凍っているらしく、なかなか開かない」  19
          조각 367+368  「が凍っているらしく、なかなか開かない」+「。」  19

    아래쪽을 골라 한글판 분홍 밑줄이 「창틀」을 빼고 「。」 를 물었고,
    `keyname` 이 본문에서 키워드를 못 떠 와 KM 문항 하나가 안 풀렸다.

    `texts`(조각 원문)와 `kws`(`answers.keywords` — 정답표에 적힌 키워드)를
    주면 **정답표에 있는 쪽**을 고른다. 정답표의 문자열이 곧 정답이므로
    이보다 확실한 기준이 없다. 682곳 중 이 한 곳만 달라진다."""
    pos = {v: i for i, v in enumerate(ja_cum)}
    got, prev, floor = [], 0, 0
    for s, e in rec_ranges:
        cand = []
        for d in range(prev, prev - maxins - 1, -1):
            i = pos.get(s + d)
            j = pos.get(e + d + 1)
            if i is not None and j is not None and j > i and i >= floor:
                cand.append((d, i, j - 1))
        if not cand:
            return None
        pick = cand[0]
        if texts is not None and kws:
            for c in cand:
                t = rawtext.strip_tag(''.join(texts[c[1]:c[2] + 1]))
                if t in kws:
                    pick = c
                    break
        prev = pick[0]
        got.append((pick[1], pick[2]))
        floor = pick[2] + 1
    return got


ARCHIVES = ['TU.bin', 'TU_A.bin', 'NF.bin', 'NF_A.bin', 'FW.bin', 'FW_A.bin',
            'KM.bin', 'KM_A.bin', 'SI.bin', 'SI_A.bin', 'BH.bin', 'BJ.bin']


def build(ko_map, verbose=False):
    """{(archive, keyword파일): 새 바이트} 를 만든다."""
    iso = Iso()
    out, stat = {}, defaultdict(int)
    for arch in ARCHIVES:
        sp = from_iso(iso, arch)
        for kf in [e for e in sp.ents if e['name'].endswith('_keyword.bin')]:
            base = kf['name'].replace('_keyword.bin', '.bin')
            try:
                se = sp.byname(base)
            except Exception:
                continue
            bl = blocks_of(sp.get(se))
            k = bytearray(sp.get(kf))
            changed = 0
            for bi, off, seg, rr in recs_of(k, len(bl)):
                parts = bl[bi]['parts']
                ja = cum([len(t) for _, t in parts])
                ko = cum([len(core.to_fullwidth(ko_map.get((arch, base, i)) or t))
                          for i, t in parts])
                spans = match(rr, ja, texts=[t for _, t in parts],
                              kws=answers.keywords(iso))
                if not spans:
                    stat['조각 경계 불일치'] += 1
                    continue
                new = [(s + ko[i] - ja[i], e + ko[j + 1] - ja[j + 1])
                       for (s, e), (i, j) in zip(rr, spans)]
                if any(s < 0 or e > U8 or e < s for s, e in new):
                    stat['범위 초과로 건너뜀'] += 1
                    if verbose:
                        print(f"   ! {arch} {bl[bi]['label']} {rr} -> {new}")
                    continue
                for n, (s, e) in enumerate(new):
                    k[off + 8 + n * 6] = s
                    k[off + 9 + n * 6] = e
                k[off + 7] = min(U8, max(0, seg + ko[-1] - ja[-1]))
                stat['갱신'] += 1
                changed += 1
            if changed:
                out[(arch, kf['name'])] = bytes(k)
            stat['파일'] += 1
    return out, stat


def load_ko():
    idx = json.load(open(os.path.join(TEXT, '_index.json'), encoding='utf-8'))
    ko_map = {}
    for meta in idx['files']:
        for e in json.load(open(os.path.join(TEXT, meta['file']),
                                encoding='utf-8'))['entries']:
            ko_map[(e['archive'], e['file'], e['index'])] = e.get('ko') or ''
    return ko_map


if __name__ == '__main__':
    payload, stat = build(load_ko(), verbose=True)
    pickle.dump(payload, open('keyword_payloads.pkl', 'wb'))
    print(dict(stat))
    print(f"-> keyword_payloads.pkl ({len(payload)} 파일)")
