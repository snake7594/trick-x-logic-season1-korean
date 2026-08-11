"""한글판 ISO 를 만든다.

- 각 SECTPACK 아카이브를 번역된 스크립트로 재조립
- common.bin 에는 한글 폰트도 심는다
- 커진 아카이브는 ISO 의 파일 간 여유 섹터로 흡수하고,
  SI_A 뒤가 꽉 찬 BH.bin 만 1섹터 뒤로 옮기며 디렉터리 레코드를 갱신
"""
import paths
import os
import pickle
import shutil
import struct
from isolib import Iso, SEC
from sectpack import from_iso, SectPack

GAME = paths.ROOT
ISO_SRC = GAME + r'\Trick x Logic Season 1.iso'
ISO_DST = GAME + r'\Trick x Logic Season 1 (KR).iso'

FONT_PAYLOAD = {
    './script/Font/NovelFontList.dat': 'font_out/NovelFont_KR.payload',
    './script/Font/AdvFontList.dat': 'font_out/AdvFont_KR.payload',
}


# ---------- ISO 디렉터리 레코드 ----------
def dir_records(iso):
    """[(rec_off, name, lba, size)] — rec_off 는 ISO 안 절대 오프셋."""
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
            nlen = data[off + 32]
            nm = data[off + 33:off + 33 + nlen]
            if nm not in (b'\x00', b'\x01'):
                full = path + '/' + nm.decode('latin1').split(';')[0]
                out.append((base + off, full, ext, sz))
                if flags & 2:
                    walk(ext, sz, full)
            off += ln

    walk(rlba, rsize, '')
    return out


def patch_record(buf, rec_off, lba, size):
    struct.pack_into('<I', buf, rec_off + 2, lba)
    struct.pack_into('>I', buf, rec_off + 6, lba)
    struct.pack_into('<I', buf, rec_off + 10, size)
    struct.pack_into('>I', buf, rec_off + 14, size)


# ---------- 아카이브 재조립 ----------
def rebuild_archive(sp, replace, comp_override=None):
    """replace: {파일명: 새 payload}. 섹터를 다시 할당해 새 아카이브 바이트 반환.
       comp_override: {파일명: 0|1} — 저장 형식이 바뀐 파일의 압축 플래그."""
    ents = sorted(sp.ents, key=lambda e: e['sec'])
    out = bytearray(sp.data[:sp.base])        # TOC 그대로
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


new_scripts = pickle.load(open('new_scripts.pkl', 'rb'))
by_arch = {}
for (arch, fname), payload in new_scripts.items():
    by_arch.setdefault(arch, {})[fname] = payload

# 키워드(분홍 글자) 범위를 한국어 위치로 고친 파일
if os.path.exists('keyword_payloads.pkl'):
    from lz import compress as _kc, decompress as _kd
    kws = pickle.load(open('keyword_payloads.pkl', 'rb'))
    _iso_k = Iso()
    for (arch, fname), raw in kws.items():
        sp0 = (SectPack(open('common.bin', 'rb').read()) if arch == 'common.bin'
               else from_iso(_iso_k, arch))
        e0 = sp0.byname(fname)
        if e0['comp']:
            c = _kc(raw)
            assert _kd(c, len(raw)) == raw
            payload = struct.pack('<II', len(raw), len(c)) + c
        else:
            payload = raw
        by_arch.setdefault(arch, {})[fname] = payload
    print(f"키워드 파일 {len(kws)}개 반영")

# 한글화한 GIM 이미지 (있으면 함께 반영). 원본이 압축이면 압축해서 넣는다.
if os.path.exists('image_payloads.pkl'):
    from lz import compress as _lzc, decompress as _lzd
    imgs = pickle.load(open('image_payloads.pkl', 'rb'))
    _iso0 = Iso()
    n_img = 0
    for (arch, fname), raw in imgs.items():
        sp0 = (SectPack(open('common.bin', 'rb').read()) if arch == 'common.bin'
               else from_iso(_iso0, arch))
        e0 = sp0.byname(fname)
        if e0['comp']:
            c = _lzc(raw)
            assert _lzd(c, len(raw)) == raw
            payload = struct.pack('<II', len(raw), len(c)) + c
        else:
            payload = raw
        by_arch.setdefault(arch, {})[fname] = payload
        n_img += 1
    print(f"한글화 이미지 {n_img}장 포함")

iso = Iso()
recs = {n.split('/')[-1]: (o, l, s) for o, n, l, s in dir_records(iso)}

print("아카이브 재조립:")
built = {}
for arch in sorted(by_arch):
    sp = (SectPack(open('common.bin', 'rb').read()) if arch == 'common.bin'
          else from_iso(iso, arch))
    rep = dict(by_arch[arch])
    ovr = None
    if arch == 'common.bin':
        for name, path in FONT_PAYLOAD.items():
            rep[name] = open(path, 'rb').read()
        # 폰트는 전부 압축 저장한다 (NovelFontList 는 원본이 무압축이었음)
        ovr = {name: 1 for name in FONT_PAYLOAD}
    nb = rebuild_archive(sp, rep, ovr)
    old_sec = len(sp.data) // SEC
    new_sec = (len(nb) + SEC - 1) // SEC
    built[arch] = nb
    print(f"  {arch:<14} {old_sec:>6,} -> {new_sec:>6,} 섹터 ({new_sec-old_sec:+d})")

# ---------- 배치 계획 ----------
print("\n배치:")
plan = []
for arch, nb in sorted(built.items()):
    rec_off, lba, size = recs[arch]
    nsec = (len(nb) + SEC - 1) // SEC
    plan.append([arch, rec_off, lba, len(nb), nsec])

# 앞 아카이브가 넘치면 바로 뒤 아카이브를 필요한 만큼 뒤로 민다.
allf = sorted(((l, (s + SEC - 1) // SEC, n.split('/')[-1])
               for o, n, l, s in dir_records(iso)), key=lambda t: t[0])
mine = {p[0]: p for p in plan}
for i, (lba, nsec, base) in enumerate(allf):
    if base not in mine:
        continue
    end = mine[base][2] + mine[base][4]
    if i + 1 >= len(allf):
        continue
    nxt_lba, nxt_sec, nxt_base = allf[i + 1]
    cur_next = mine[nxt_base][2] if nxt_base in mine else nxt_lba
    if end > cur_next:
        shift = end - cur_next
        if nxt_base not in mine:
            raise SystemExit(f"{base} 가 {nxt_base} 를 침범 ({shift}섹터). "
                             f"뒤 파일이 우리 것이 아니라 밀 수 없음")
        mine[nxt_base][2] += shift
        print(f"  {nxt_base} LBA {mine[nxt_base][2]-shift:,} -> "
              f"{mine[nxt_base][2]:,} ({shift}섹터 이동, {base} 확장분)")

# 겹침 검사 (ISO 전체 파일 기준)
allf = sorted(((l, (s + SEC - 1) // SEC, n) for o, n, l, s in dir_records(iso)),
              key=lambda t: t[0])
moved = {p[0]: (p[2], p[4]) for p in plan}
occ = []
for l, ns, n in allf:
    b = n.split('/')[-1]
    if b in moved:
        l, ns = moved[b]
    if ns:
        occ.append((l, l + ns, n))
occ.sort()
bad = 0
for a, b in zip(occ, occ[1:]):
    if a[1] > b[0]:
        print(f"  겹침! {a[2]} [{a[0]}..{a[1]}) vs {b[2]} [{b[0]}..)")
        bad += 1
print(f"  겹침 {bad}건")
assert bad == 0, '배치 충돌'

# ---------- ISO 쓰기 ----------
print(f"\nISO 복사 -> {os.path.basename(ISO_DST)}")
shutil.copyfile(ISO_SRC, ISO_DST)
with open(ISO_DST, 'r+b') as f:
    for arch, rec_off, lba, nbytes, nsec in plan:
        f.seek(lba * SEC)
        f.write(built[arch])
        pad = nsec * SEC - nbytes
        if pad:
            f.write(b'\0' * pad)
        f.seek(rec_off)
        rec = bytearray(32)
        f.seek(rec_off + 2)
        buf = bytearray(16)
        struct.pack_into('<I', buf, 0, lba)
        struct.pack_into('>I', buf, 4, lba)
        struct.pack_into('<I', buf, 8, nbytes)
        struct.pack_into('>I', buf, 12, nbytes)
        f.write(buf)
        print(f"  {arch:<14} LBA {lba:,} 크기 {nbytes:,}B 기록")

print(f"\n원본 {os.path.getsize(ISO_SRC):,} / 신규 {os.path.getsize(ISO_DST):,}")
