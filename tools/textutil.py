"""바이너리/Shift-JIS 공용 유틸."""


def hexdump(b, base=0, width=16):
    out = []
    for i in range(0, len(b), width):
        row = b[i:i + width]
        h = ' '.join(f'{c:02X}' for c in row)
        a = ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)
        out.append(f'{base+i:06X}  {h:<{width*3}} |{a}|')
    return '\n'.join(out)


def is_sjis_lead(c):
    return 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF


def sjis_runs(b, minlen=4):
    """Shift-JIS 로 읽히는 연속 구간 [(offset, text)]."""
    runs, i, start, buf = [], 0, None, bytearray()
    n = len(b)
    while i < n:
        c = b[i]
        two = False
        if is_sjis_lead(c) and i + 1 < n:
            d = b[i + 1]
            if 0x40 <= d <= 0xFC and d != 0x7F:
                two = True
        if two:
            if start is None:
                start, buf = i, bytearray()
            buf += b[i:i + 2]
            i += 2
        elif 0x20 <= c <= 0x7E or c == 0x0A:
            if start is None:
                start, buf = i, bytearray()
            buf.append(c)
            i += 1
        else:
            if start is not None and len(buf) >= minlen:
                try:
                    runs.append((start, buf.decode('cp932')))
                except Exception:
                    pass
            start, buf = None, bytearray()
            i += 1
    if start is not None and len(buf) >= minlen:
        try:
            runs.append((start, buf.decode('cp932')))
        except Exception:
            pass
    return runs


def cstrings(b, minlen=2):
    """널 종료 문자열 전부 [(offset, bytes, text)] — cp932 로 디코드되는 것만."""
    out, i, n = [], 0, len(b)
    while i < n:
        j = b.find(b'\x00', i)
        if j < 0:
            break
        if j - i >= minlen:
            seg = b[i:j]
            if all(c >= 0x20 or c == 0x0A for c in seg):
                try:
                    out.append((i, seg, seg.decode('cp932')))
                except Exception:
                    pass
        i = j + 1
    return out
