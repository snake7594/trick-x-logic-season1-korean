"""SECTPACK 아카이브 리더."""
import struct
from lz import decompress

SEC = 2048


class SectPack:
    def __init__(self, data):
        assert data[:8] == b'SECTPACK', data[:8]
        self.data = data
        self.hdr_count = struct.unpack('<H', data[12:14])[0]
        off = data.find(b'./')
        ents = []
        while True:
            p = data.find(b'\x00', off)
            name = data[off:p]
            if not name.startswith(b'./') or not all(32 <= c < 127 for c in name):
                break
            a, sec, cnt = struct.unpack('<HHH', data[p + 1:p + 7])
            ents.append(dict(name=name.decode(), id=a & 0x7FFF, comp=a >> 15,
                             sec=sec, nsec=cnt, foff=p + 1))
            off = p + 7
        self.toc_end = off
        self.base = (off + SEC - 1) // SEC * SEC
        self.ents = ents

    def raw(self, e):
        o = self.base + e['sec'] * SEC
        return self.data[o:o + e['nsec'] * SEC]

    def get(self, e):
        b = self.raw(e)
        if e['comp']:
            ds, cs = struct.unpack('<II', b[:8])
            b = decompress(b[8:8 + cs], ds)
        return b

    def byname(self, name):
        for e in self.ents:
            if e['name'] == name or e['name'].endswith('/' + name.lstrip('./')):
                return e
        raise KeyError(name)


def from_iso(iso, name):
    """ISO 안의 data/<name> 을 SectPack 으로."""
    for s, e, n in iso.files():
        if n.endswith('/' + name):
            iso.f.seek(s)
            return SectPack(iso.f.read(e - s))
    raise KeyError(name)


if __name__ == '__main__':
    import sys
    from collections import Counter
    from isolib import Iso
    iso = Iso()
    for nm in (sys.argv[1:] or ['TU.bin', 'TU_A.bin', 'BJ.bin']):
        sp = from_iso(iso, nm)
        print(f"=== {nm}: {len(sp.ents)} entries (header says {sp.hdr_count}), "
              f"TOC end 0x{sp.toc_end:X}, data base 0x{sp.base:X}")
        ext = Counter(e['name'].rsplit('.', 1)[-1] for e in sp.ents)
        print("   확장자:", dict(ext))
        dirs = Counter('/'.join(e['name'].split('/')[:-1]) for e in sp.ents)
        for d, c in sorted(dirs.items()):
            print(f"   {d}/  ({c})")
        for e in sp.ents[:6]:
            print(f"     {e['name']:<48} comp={e['comp']} {e['nsec']*SEC:>8,}B")
        print()
