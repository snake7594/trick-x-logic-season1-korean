"""재삽입·아카이브·ISO 공용 함수 (임포트해도 부작용 없음)."""
import paths
import json
import os
import struct

TEXT = paths.TEXT
SEC = 2048

_map = json.load(open(os.path.join(TEXT, '_hangul_codes.json'),
                     encoding='utf-8'))['map']
H2C = {ch: int(v, 16) for ch, v in _map.items()}
C2H = {v: k for k, v in H2C.items()}


# 원문이 한 번도 쓰지 않는 문자 -> 원문이 실제로 쓰는 문자로.
# 원문에 없는 입력은 게임이 상정하지 않아 오동작한다(반각·제어태그에서 확인).
SAFE_MAP = {
    '，': '、',     # FULLWIDTH COMMA -> IDEOGRAPHIC COMMA (원문 12,178회)
    '‘': '『', '’': '』',   # 원문은 「」『』“” 만 사용
    '－': '～',     # FULLWIDTH HYPHEN-MINUS -> 원문이 쓰는 물결
}


def to_fullwidth(t):
    """반각 ASCII 를 전각으로. 이 게임의 원문은 반각을 0회 사용한다(전수 확인).

    반각을 넣으면 게임이 오동작한다 — 반각 공백은 줄바꿈 로직에서 크래시,
    반각 영숫자는 버튼 아이콘 치환이 깨져 흰 사각형으로 표시된다(실기 확인).
    """
    out = []
    for ch in t:
        o = ord(ch)
        if o == 0x20:
            ch = '　'
        elif 0x21 <= o <= 0x7E:
            ch = chr(o + 0xFEE0)
        out.append(SAFE_MAP.get(ch, ch))
    return ''.join(out)


def encode(t):
    """한국어/일본어 혼합 문자열 -> 게임 바이트열."""
    t = to_fullwidth(t)
    out = bytearray()
    for ch in t:
        c = H2C.get(ch)
        if c is not None:
            out += bytes([c >> 8, c & 0xFF])
        else:
            out += ch.encode('cp932')
    return bytes(out)


def decode(raw):
    """게임 바이트열 -> 사람이 읽는 문자열 (한글 코드 역매핑)."""
    out, i, n = [], 0, len(raw)
    while i < n:
        c = raw[i]
        if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF) and i + 1 < n:
            code = (c << 8) | raw[i + 1]
            out.append(C2H.get(code) or bytes(raw[i:i + 2]).decode('cp932'))
            i += 2
        else:
            out.append(bytes([c]).decode('cp932'))
            i += 1
    return ''.join(out)


def rebuild_script(d, items):
    """items: [(len_off, str_off, orig_bytes, new_raw)] — 문자열 교체."""
    out = bytearray()
    pos = 0
    for lo, so, nb, new in sorted(items):
        out += d[pos:lo]
        out += struct.pack('<I', len(new) + 1)
        out += new + b'\x00'
        pos = so + nb
    out += d[pos:]
    return bytes(out)


def rebuild_archive(sp, replace, comp_override=None):
    """SECTPACK 재조립. replace: {파일명: payload}."""
    ents = sorted(sp.ents, key=lambda e: e['sec'])
    out = bytearray(sp.data[:sp.base])
    cur = 0
    for e in ents:
        payload = replace.get(e['name'])
        blob = payload if payload is not None else sp.raw(e)
        nsec = (len(blob) + SEC - 1) // SEC
        need = sp.base + (cur + nsec) * SEC
        if len(out) < need:
            out += b'\0' * (need - len(out))
        o = sp.base + cur * SEC
        out[o:o + len(blob)] = blob
        comp = e['comp']
        if comp_override and e['name'] in comp_override:
            comp = comp_override[e['name']]
        struct.pack_into('<HHH', out, e['foff'],
                         (e['id'] | (comp << 15)), cur, nsec)
        cur += nsec
    return bytes(out)


def dir_records(iso):
    """[(rec_off, name, lba, size)] — ISO9660 디렉터리 레코드."""
    _, root = iso.pvd()
    rlba = struct.unpack('<I', root[2:6])[0]
    rsize = struct.unpack('<I', root[10:14])[0]
    out = []

    def walk(lba, size, path):
        data = iso.sect(lba, (size + SEC - 1) // SEC)
        base = lba * SEC
        off = 0
        while off < size:
            ln = data[off]
            if ln == 0:
                off = (off // SEC + 1) * SEC
                continue
            ext = struct.unpack('<I', data[off + 2:off + 6])[0]
            sz = struct.unpack('<I', data[off + 10:off + 14])[0]
            flags = data[off + 25]
            nm = data[off + 33:off + 33 + data[off + 32]]
            if nm not in (b'\x00', b'\x01'):
                full = path + '/' + nm.decode('latin1').split(';')[0]
                out.append((base + off, full, ext, sz))
                if flags & 2:
                    walk(ext, sz, full)
            off += ln

    walk(rlba, rsize, '')
    return out


def patch_record(f, rec_off, lba, nbytes):
    """디렉터리 레코드의 LBA/크기를 both-endian 으로 갱신."""
    buf = bytearray(16)
    struct.pack_into('<I', buf, 0, lba)
    struct.pack_into('>I', buf, 4, lba)
    struct.pack_into('<I', buf, 8, nbytes)
    struct.pack_into('>I', buf, 12, nbytes)
    f.seek(rec_off + 2)
    f.write(buf)


def load_translations(arch=None, scripts=None):
    """{파일명: [(len_off, str_off, orig_bytes, new_raw)]}"""
    from collections import defaultdict
    idx = json.load(open(os.path.join(TEXT, '_index.json'), encoding='utf-8'))
    plan = defaultdict(list)
    for meta in idx['files']:
        doc = json.load(open(os.path.join(TEXT, meta['file']), encoding='utf-8'))
        for r in doc['entries']:
            if arch and r['archive'] != arch:
                continue
            if scripts and r['file'].split('/')[-1] not in scripts:
                continue
            if not r['ko']:
                continue
            loc = r['loc']
            plan[(r['archive'], r['file'])].append(
                (loc['len_off'], loc['str_off'], loc['orig_bytes'],
                 encode(r['ko'])))
    return plan
