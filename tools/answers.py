# -*- coding: utf-8 -*-
"""추리 정답표에서 **필요한 키워드 문자열**을 뽑는다.

    op 0x13  문항 : Q아이디\0 제목\0 [u32 개수 + 문자열\0 × 개수] × N
    op 0x14  착상 : I아이디\0 제목\0 [u32 개수 + 문자열\0 × 개수] × N

착상 payload 를 예로 들면 이렇다.

    I_0020_0020\0
    「写真は現場に人が集まる前に取り替えられた」\0        착상 제목
    01 00 00 00  Q_0020\0                                엮인 문항
    03 00 00 00  「…映って」\0「…映っていた」\0「…変わりない」\0
    00 00 00 00  03 00 00 00                              꼬리 필드

**개수 필드를 안 보고 (u32 + 문자열) 짝으로 읽으면** 두 번째 키워드부터 앞
4바이트(두 글자)를 u32 로 먹는다. 「こちらには…」 가 「らには…」 로 잘린다.

이 문자열이 곧 정답이다. 게임은 본문 분홍 글자를 눌러 얻은 낱말을 여기에
적힌 문자열과 **글자 그대로** 대조한다. 그래서 분홍 범위를 조각 경계에
맞출 때(`keywordfix.match`) 후보가 둘이면 **여기 있는 쪽**이 정답이다.
"""
import struct

from sectpack import from_iso
from lz import decompress
from prcs import SCENARIOS
import prcswalk

MAXN = 64
NUL = bytes([0])
_cache = None


def _unpack(d):
    if d[:4] == b'PRCS':
        return d
    try:
        n, c = struct.unpack('<II', d[:8])
        return decompress(d[8:8 + c], n)
    except Exception:
        return d


def fields(p):
    """(아이디, 제목, [묶음...]) — 묶음은 문자열 리스트."""
    n = len(p)
    j = p.find(NUL)
    if j < 0:
        return None
    ident, i = p[:j], j + 1
    j = p.find(NUL, i)
    if j < 0:
        return None
    title, i = p[i:j], j + 1
    groups = []
    while i + 4 <= n:
        cnt = struct.unpack('<I', p[i:i + 4])[0]
        i += 4
        if cnt > MAXN:
            break                  # 꼬리에 붙은 다른 필드다
        g, bad = [], False
        for _ in range(cnt):
            j = p.find(NUL, i)
            if j < 0:
                bad = True
                break
            g.append(p[i:j])
            i = j + 1
        if bad:
            break
        groups.append(g)
    return ident, title, groups


def entries(iso):
    """[(아카이브, 파일, op, 아이디, 제목, [묶음...])]"""
    out = []
    for arch in SCENARIOS + ['common.bin']:
        try:
            sp = from_iso(iso, arch)
        except Exception:
            continue
        for e in sp.ents:
            if '/script/' not in e['name'] or not e['name'].endswith('.bin'):
                continue
            d = _unpack(sp.get(e))
            if d[:4] != b'PRCS':
                continue
            cmds = prcswalk.walk(d)
            if cmds is None:
                continue
            for oo, op, po, pl in cmds:
                if op not in (0x13, 0x14):
                    continue
                f = fields(d[po:po + pl])
                if f:
                    out.append((arch, e['name'], op, f[0], f[1], f[2]))
    return out


def _is_kw(t):
    return bool(t.strip()) and not t.startswith(('Q_', 'I_', 'SN', 'ENV_'))


def keywords(iso):
    """정답에 쓰이는 키워드 문자열 집합 (원문 그대로)."""
    global _cache
    if _cache is not None:
        return _cache
    out = set()
    for arch, name, op, ident, title, groups in entries(iso):
        for g in groups:
            for s in g:
                t = s.decode('cp932', 'replace')
                if _is_kw(t):
                    out.add(t)
    _cache = out
    return out
