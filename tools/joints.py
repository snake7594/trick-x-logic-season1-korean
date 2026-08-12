"""조각 이음매를 명령 스트림에서 정확히 뽑는다.

번역은 조각(op 0x01) 단위로 이뤄져서 **이음매의 띄어쓰기가 빠지기 쉽다**.
어떤 조각끼리 화면에서 이어 붙는지는 JSON 의 index 순서만으로는 알 수 없다 —
사이에 줄바꿈(0x27)이나 블록 경계(0x0f)가 있으면 이어지지 않는다.

여기서는 PRCS 를 걸어 op 0x01 사이에 **루비 명령(0x32/0x33)만** 있는 경우를
'이어 붙는 짝'으로 본다. 그 짝에만 `spacefix.need_space` 를 적용한다.

    python ../tools/joints.py          # 점검만
    python ../tools/joints.py --fix    # text/*.json 을 고친다
"""
import paths
import json
import os
import sys

from isolib import Iso
from sectpack import from_iso, SectPack
from prcs import SCENARIOS, has_jp, find_strings
import prcswalk
import spacefix

# 줄·쪽을 끊는 명령. 어떤 명령이 끊는지는 **원문 문장부호와의 상관**으로
# 가려냈다: 명령 없이 붙은 1,532쌍 중 앞 조각이 `。！？` 로 끝나는 비율은
# 9.0% 인데(기준선), 아래 명령이 끼면 25~94% 로 뛴다. 일본어는 화면에서
# 이어지는 자리에 마침표를 안 찍으므로 이 차이가 곧 '끊김'이다.
#
#   29 94% · af 73% · 19 63% · 0f 63% · 39 62% · 38 61% · 57 55%
#   aa 55% · 6d 46% · 6c 45% · 27 43%(줄바꿈) · 28 25%(입력 대기)
#
# 반대로 루비(32·33)는 2.7%·0.0% 로 확실히 같은 줄 안이다.
BREAK = {0x29, 0xaf, 0x19, 0x0f, 0x39, 0x38, 0x57, 0xaa, 0x6d, 0x6c,
         0x27, 0x28}
SENT_END = ('。', '！', '？', '．')

# 하단 안내바는 '설명'과 '버튼 이름'이 각각 다른 칸에 그려진다. 명령 스트림에서는
# 이어져 보이지만 화면에서는 떨어져 있으므로 건드리지 않는다.
SKIP_FILE = ('information_message.bin', 'information_bar.bin')

# 전수 검토에서 걸러낸 것 — 낱말이나 어미가 조각 경계로 쪼개진 자리다.
# 여기에 공백을 넣으면 '여리 고', '끔찍 한', '남자 가' 처럼 깨진다.
SKIP = {
    ('FW.bin', 103), ('FW.bin', 347),
    ('KM.bin', 241), ('KM.bin', 364), ('KM.bin', 881),
    ('KM_answer_begin.bin', 832),
    ('SI.bin', 247), ('SI.bin', 964),
    ('BJ.bin', 274), ('BJ.bin', 974),
    ('KM_answer_begin.bin', 1051),   # '낮은'+'가……' 는 한 낱말
}


def arch(iso, name):
    if name == 'common.bin':
        for s, e, n in iso.files():
            if n.endswith('/common.bin'):
                iso.f.seek(s)
                return SectPack(iso.f.read(e - s))
    return from_iso(iso, name)


def pairs(d):
    """[(앞 조각의 index, 뒤 조각 index)] — 화면에서 이어 붙는 짝.

    index 는 **JSON 과 같은 기준**이어야 한다. JSON 은 `find_strings` 순서에서
    일본어가 든 것만 센 번호다(`verify_strict` 와 같다). 명령을 직접 세면
    `find_strings` 가 더 잡는 가짜 문자열 때문에 한 칸씩 어긋난다."""
    cmds = prcswalk.walk(d)
    if cmds is None:
        return []
    at = {po: k for k, (oo, op, po, pl) in enumerate(cmds)}
    seq, ji = [], 0
    for lo, so, raw, t in find_strings(d):
        if not has_jp(t):
            continue
        k = at.get(so)
        seq.append((ji, k if k is not None and cmds[k][1] == 0x01 else None))
        ji += 1
    out = []
    for (a, ka), (b, kb) in zip(seq, seq[1:]):
        if ka is None or kb is None or kb <= ka:
            continue
        mid = [cmds[m][1] for m in range(ka + 1, kb)]
        if any(o in BREAK for o in mid):
            continue
        # 루비를 건너뛰는 자리는 낱말이 쪼개진 것이다 — 絨/毯, 悶/着, 痙攣.
        # 앞 조각이 루비 대상 글자라 여기에 공백을 넣으면 낱말이 깨진다.
        if 0x32 in mid or 0x33 in mid:
            continue
        out.append((a, b))
    return out


def scan(fix=False):
    iso = Iso()
    idx = json.load(open(os.path.join(paths.TEXT, '_index.json'),
                         encoding='utf-8'))
    docs = {}
    for m in idx['files']:
        docs[m['file']] = json.load(
            open(os.path.join(paths.TEXT, m['file']), encoding='utf-8'))
    by_file = {}
    for name, doc in docs.items():
        for r in doc['entries']:
            by_file.setdefault((r['archive'], r['file']), {})[r['index']] = r

    n_hit, n_chk = 0, 0
    samples = []
    for a in SCENARIOS + ['common.bin']:
        sp = arch(iso, a)
        for e in sp.ents:
            rows = by_file.get((a, e['name']))
            if not rows or e['name'].endswith(SKIP_FILE):
                continue
            base = e['name'].split('/')[-1]
            d = sp.get(e)
            if d[:4] != b'PRCS':
                continue
            for i, j in pairs(d):
                ra, rb = rows.get(i), rows.get(j)
                if not ra or not rb:
                    continue
                ka = ra.get('ko') or ''
                kb = rb.get('ko') or ''
                if not ka or not kb:
                    continue
                n_chk += 1
                if ka.endswith((' ', '　')) or kb.startswith((' ', '　')):
                    continue
                # 원문이 문장으로 끝났으면 띄어쓰기가 아니라 마침표 문제다.
                # 여기서는 건드리지 않는다.
                if ra['ja'].rstrip().endswith(SENT_END):
                    continue
                # 한 글자짜리 조각은 낱말이 쪼개진 것이다(屏/風 → '병'+'풍').
                # 여기에 공백을 넣으면 낱말이 깨진다.
                if len(ka.strip()) < 2 or len(kb.strip()) < 2:
                    continue
                if (base, i) in SKIP:
                    continue
                if spacefix.need_space(ka, kb, ra['ja'], rb['ja']):
                    n_hit += 1
                    if len(samples) < 15:
                        samples.append((e['name'], i, ka[-12:], kb[:12]))
                    if fix:
                        ra['ko'] = ka + ' '
    print(f"이어 붙는 짝 {n_chk:,} / 띄어쓰기 빠진 곳 {n_hit:,}")
    for s in samples:
        print(f"   {s[0].split('/')[-1]:<24} {s[1]:>5}  …{s[2]!r} + {s[3]!r}")
    if fix and n_hit:
        for name, doc in docs.items():
            json.dump(doc, open(os.path.join(paths.TEXT, name), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"-> text/*.json 갱신")
    return n_hit


if __name__ == '__main__':
    scan('--fix' in sys.argv)
