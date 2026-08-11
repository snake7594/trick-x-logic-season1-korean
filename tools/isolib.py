import paths
import struct

SEC = 2048
ISO_PATH = paths.ISO


class Iso:
    def __init__(self, path=ISO_PATH):
        self.f = open(path, 'rb')

    def sect(self, lba, n=1):
        self.f.seek(lba * SEC)
        return self.f.read(n * SEC)

    def pvd(self):
        d = self.sect(16)
        assert d[1:6] == b'CD001', d[1:6]
        return d[40:72].decode('latin1').strip(), d[156:156 + 34]

    def parse_dr(self, b, off):
        ln = b[off]
        if ln == 0:
            return None, off
        return dict(
            lba=struct.unpack('<I', b[off + 2:off + 6])[0],
            size=struct.unpack('<I', b[off + 10:off + 14])[0],
            flags=b[off + 25],
            name=b[off + 33:off + 33 + b[off + 32]],
        ), off + ln

    def listdir(self, lba, size):
        data = self.sect(lba, (size + SEC - 1) // SEC)
        entries, off = [], 0
        while off < size:
            if off % SEC == 0 or data[off] != 0:
                dr, noff = self.parse_dr(data, off)
                if dr is None:
                    off = (off // SEC + 1) * SEC
                    continue
                entries.append(dr)
                off = noff
            else:
                off = (off // SEC + 1) * SEC
        return entries

    def walk(self, lba, size, path=''):
        for e in self.listdir(lba, size):
            if e['name'] in (b'\x00', b'\x01'):
                continue
            full = path + '/' + e['name'].decode('latin1').split(';')[0]
            isdir = bool(e['flags'] & 2)
            yield full, e['lba'], e['size'], isdir
            if isdir:
                yield from self.walk(e['lba'], e['size'], full)

    def files(self):
        """-> list of (byte_start, byte_end, name), sorted."""
        _, root = self.pvd()
        rlba = struct.unpack('<I', root[2:6])[0]
        rsize = struct.unpack('<I', root[10:14])[0]
        out = [(lba * SEC, lba * SEC + size, name)
               for name, lba, size, isdir in self.walk(rlba, rsize) if not isdir]
        out.sort()
        return out

    def read(self, lba, size):
        self.f.seek(lba * SEC)
        return self.f.read(size)

    def read_named(self, name):
        for s, e, n in self.files():
            if n == name or n.endswith('/' + name.lstrip('/')):
                self.f.seek(s)
                return self.f.read(e - s)
        raise KeyError(name)
