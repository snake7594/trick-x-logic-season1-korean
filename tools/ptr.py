import struct
from fonts import load


def read_ptrlist(d, off):
    """SIR0 relocation list: varint deltas (7 bits/byte, MSB = continue), 0 terminates."""
    ptrs, pos, i = [], 0, off
    while True:
        v = 0
        while True:
            b = d[i]
            i += 1
            v = (v << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        if v == 0:
            break
        pos += v
        ptrs.append(pos)
    return ptrs, i


def write_ptrlist(ptrs):
    out = bytearray()
    prev = 0
    for p in ptrs:
        d = p - prev
        prev = p
        chunks = []
        while True:
            chunks.append(d & 0x7F)
            d >>= 7
            if not d:
                break
        for k in range(len(chunks) - 1, -1, -1):
            out.append(chunks[k] | (0x80 if k else 0))
    out.append(0)
    return bytes(out)


for fn, name in (('NovelFontList.dat', 'NovelFont'),
                 ('AdvFontList.dat', 'AdvFont'),
                 ('NovelRubyFontList.dat', 'NovelRubyFont')):
    d, _ = load('out/' + fn)
    sub, ptro = struct.unpack('<II', d[4:12])
    cnt = struct.unpack('<I', d[sub:sub + 4])[0]
    ptrs, end = read_ptrlist(d, ptro)
    expect = [4, 8] + [sub + 8 + i * 4 for i in range(cnt)]
    print(f"=== {name}: {len(ptrs)} pointers (expect {len(expect)}) "
          f"match={ptrs == expect}")
    print(f"   first 6 {ptrs[:6]}  expect {expect[:6]}")
    print(f"   list 0x{ptro:X}..0x{end:X} ({end-ptro}B), file 0x{len(d):X}, "
          f"trailing {len(d)-end}B")
    print(f"   re-encode identical: {write_ptrlist(ptrs) == d[ptro:end]}")
    print(f"   tail bytes: {d[end:end+16].hex(' ')}")
    print()
