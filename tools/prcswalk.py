"""PRCS 명령 스트림을 걷는다.

    0x00..0x0f   헤더 ('PRCS' + 0)
    이후 반복     u8 opcode | u32 payload 길이 | payload

대사(op 0x01)는 payload 가 곧 `cp932 + NUL` 이라 u32 가 문자열 길이와 같다.
그래서 대사만 바꿀 때는 이 구조를 몰라도 맞아떨어졌다. 하지만 추리 데이터의
**길이 접두사 없는 문자열**은 op 0xa4 같은 명령의 payload 안에 여러 개가 묶여
들어 있어서, 안에서 길이가 바뀌면 **그 명령의 u32 도 같이 고쳐야 한다.**
안 고치면 해석기가 어긋나 게임이 부팅에서 죽는다(sn7_init.bin).
"""
import struct

HDR = 0x10


def walk(d):
    """[(op_off, op, payload_off, payload_len)] — 끝까지 못 걸으면 None."""
    out, i, n = [], HDR, len(d)
    if d[:4] != b'PRCS':
        return None
    while i < n:
        if i + 5 > n:
            return None
        op = d[i]
        ln = struct.unpack('<I', d[i + 1:i + 5])[0]
        if i + 5 + ln > n:
            return None
        out.append((i, op, i + 5, ln))
        i += 5 + ln
    return out


def owner(cmds, off):
    """오프셋을 품은 명령의 인덱스. 이분 탐색."""
    lo, hi = 0, len(cmds) - 1
    while lo <= hi:
        m = (lo + hi) // 2
        _, _, po, pl = cmds[m]
        if off < po:
            hi = m - 1
        elif off >= po + pl:
            lo = m + 1
        else:
            return m
    return None


def patch(d, repl):
    """repl: {문자열 시작 오프셋: 새 바이트열(NUL 제외)}.

    바이트를 갈아 끼우면서 **그 문자열을 품은 명령의 u32 길이**를 같이 고친다."""
    cmds = walk(d)
    if cmds is None:
        raise ValueError('PRCS 스트림을 끝까지 걸을 수 없다')
    # 명령별 길이 변화량
    delta = {}
    for off, new in repl.items():
        end = d.index(b'\0', off)
        k = owner(cmds, off)
        if k is None:
            raise ValueError(f'0x{off:x} 를 품은 명령이 없다')
        if end >= cmds[k][2] + cmds[k][3]:
            raise ValueError(f'0x{off:x} 문자열이 명령 밖으로 나간다')
        delta[k] = delta.get(k, 0) + len(new) - (end - off)

    out = bytearray()
    prev = 0
    # 명령 헤더(u32)와 문자열 본문을 오프셋 순서대로 갈아 끼운다
    edits = []
    for k, dl in delta.items():
        oo, op, po, pl = cmds[k]
        edits.append((oo + 1, 4, struct.pack('<I', pl + dl)))
    for off, new in repl.items():
        edits.append((off, d.index(b'\0', off) - off, new))
    for off, ln, new in sorted(edits):
        if off < prev:
            raise ValueError('교체 구간이 겹친다')
        out += d[prev:off] + new
        prev = off + ln
    out += d[prev:]
    return bytes(out)
