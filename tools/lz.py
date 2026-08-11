"""LZ77 codec for Trick x Logic .dat files.

Control byte, MSB first, bit 1 = literal.
Match (2 bytes): len = (b0 & 0x0F) + 3, dist = ((b0 >> 4) << 8) | b1,
copied from outpos-dist (overlapping); reads before offset 0 yield 0.
"""
MAXLEN = 18
MAXDIST = 4095


def decompress(src, outsize):
    out = bytearray()
    i = 0
    while len(out) < outsize and i < len(src):
        ctrl = src[i]
        i += 1
        for bit in range(8):
            if len(out) >= outsize or i >= len(src):
                break
            if ctrl & (0x80 >> bit):
                out.append(src[i])
                i += 1
            else:
                if i + 1 >= len(src):
                    break
                b0, b1 = src[i], src[i + 1]
                i += 2
                ln = (b0 & 0x0F) + 3
                dist = ((b0 >> 4) << 8) | b1
                for _ in range(ln):
                    q = len(out) - dist
                    out.append(out[q] if 0 <= q < len(out) else 0)
                    if len(out) >= outsize:
                        break
    return bytes(out)


def compress(data, cands=12):
    n = len(data)
    out = bytearray()
    table = {}
    group = []

    def flush():
        ctrl = 0
        for k, t in enumerate(group):
            if len(t) == 1:
                ctrl |= 0x80 >> k
        out.append(ctrl)
        for t in group:
            out.extend(t)
        group.clear()

    i = 0
    while i < n:
        best_len, best_dist = 0, 0
        # fast path: run of equal bytes -> dist=1 overlapping copy
        if i > 0 and data[i] == data[i - 1]:
            ln = 1
            m = min(MAXLEN, n - i)
            while ln < m and data[i + ln] == data[i - 1]:
                ln += 1
            if ln >= 3:
                best_len, best_dist = ln, 1
        if best_len < MAXLEN and i + 3 <= n:
            key = data[i:i + 3]
            lst = table.get(key)
            if lst:
                lo = i - MAXDIST
                for p in reversed(lst[-cands:]):
                    if p < lo:
                        break
                    ln = 3
                    m = min(MAXLEN, n - i)
                    while ln < m and data[p + ln] == data[i + ln]:
                        ln += 1
                    if ln > best_len:
                        best_len, best_dist = ln, i - p
                        if ln == MAXLEN:
                            break
        if best_len >= 3:
            group.append(bytes((((best_dist >> 8) << 4) | (best_len - 3),
                                best_dist & 0xFF)))
            step = best_len
        else:
            group.append(bytes((data[i],)))
            step = 1
        for k in range(step):
            j = i + k
            if j + 3 <= n:
                key = data[j:j + 3]
                lst = table.get(key)
                if lst is None:
                    table[key] = [j]
                else:
                    lst.append(j)
                    if len(lst) > 32:
                        del lst[:16]
        i += step
        if len(group) == 8:
            flush()
    if group:
        flush()
    return bytes(out)


if __name__ == '__main__':
    import struct
    import time
    for fn in ('AdvFontList.dat', 'NovelRubyFontList.dat'):
        raw = open('out/' + fn, 'rb').read()
        dec_size, comp_size = struct.unpack('<II', raw[:8])
        orig = decompress(raw[8:8 + comp_size], dec_size)
        t = time.time()
        c = compress(orig)
        el = time.time() - t
        back = decompress(c, len(orig))
        print(f"{fn}: {len(orig):,} -> mine {len(c):,} ({len(c)/len(orig)*100:.1f}%), "
              f"game {comp_size:,} ({comp_size/len(orig)*100:.1f}%), "
              f"roundtrip {'OK' if back == orig else 'FAIL'}, {el:.1f}s")
