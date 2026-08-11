"""일본어 원문을 번역/재삽입용 JSON 으로 뽑는다."""
import paths
import json
import os
import re
from collections import Counter, defaultdict
from isolib import Iso
from sectpack import from_iso, SectPack
from prcs import find_strings, has_jp, SCENARIOS

OUT = paths.TEXT
os.makedirs(OUT, exist_ok=True)

ADV_LIMIT = 44          # 대사창: 22자 x 2줄
IDENT = re.compile(rb'^[a-z][a-z0-9_]{2,23}$')

iso = Iso()
archives = [(nm, from_iso(iso, nm)) for nm in SCENARIOS]
archives.append(('common.bin', SectPack(open('common.bin', 'rb').read())))


def cstr_before(d, pos, span=320):
    """pos 앞 span 바이트 안의 널종료 소문자 식별자들 (가까운 순)."""
    lo = max(0, pos - span)
    seg = d[lo:pos]
    out = []
    for m in re.finditer(rb'[\x20-\x7E]{3,24}\x00', seg):
        s = m.group()[:-1]
        if IDENT.match(s):
            out.append((lo + m.start(), s.decode()))
    return out[::-1]


# ---- 1차: 파일별 관측 최대 길이 ----
filemax = {}
raw = defaultdict(list)
for arch, sp in archives:
    for e in sp.ents:
        if not e['name'].endswith('.bin') or '/script/' not in e['name']:
            continue
        d = sp.get(e)
        if d[:4] != b'PRCS':
            continue
        items = [(lo, so, rb, t) for lo, so, rb, t in find_strings(d) if has_jp(t)]
        if not items:
            continue
        key = (arch, e['name'])
        raw[key] = (d, items)
        filemax[key] = max(len(t) for _, _, _, t in items)

# ---- 화자 후보 빈도 ----
# 포즈/스프라이트 ID(yos_001a 등)의 접두사가 인물을 가리킨다
NAME_MAP = {'yos': 'yosikawa', 'tuk': 'tukasa', 'mar': 'marunouchi',
            'yam': 'yama', 'kao': 'kaoru', 'its': 'itsuki'}
FULL = set(NAME_MAP.values())


def norm_speaker(n):
    if n in FULL:
        return n
    return NAME_MAP.get(n.split('_')[0])


freq = Counter()
for (arch, fn), (d, items) in raw.items():
    for lo, so, rb, t in items:
        for _, n in cstr_before(d, lo):
            s = norm_speaker(n)
            if s:
                freq[s] += 1
                break
print(f"인물별 등장: {freq.most_common()}")


def category(path):
    b = path.split('/')[-1][:-4]
    for k in ('answer_begin', 'answer', 'giveup', 'question', 'inspiration',
              'prologue', 'interval', 'bridge', 'trailer', 'hint', 'tips',
              'profile', 'report', 'outline', 'keyword'):
        if k in b:
            return k
    if '/COMMON/' in path:
        return 'common_' + path.split('/')[-2].lower()
    return 'scenario'


# ---- 2차: JSON 생성 ----
groups = defaultdict(list)
total = 0
END = '。！？」』…♪'
MAX_FRAG, MAX_CH, MAX_GAP = 8, 120, 512

for (arch, fn), (d, items) in sorted(raw.items()):
    cat = category(fn)
    fmax = filemax[(arch, fn)]
    limit = ADV_LIMIT if fmax <= ADV_LIMIT else fmax
    base = fn.split('/')[-1][:-4]

    hints = []
    for lo, so, rb, t in items:
        h = None
        for _, n in cstr_before(d, lo):
            h = norm_speaker(n)
            if h:
                break
        hints.append(h)

    # 문장 그룹: 종결부호 / 화자변경 / 큰 간격 / 길이상한 에서 끊는다
    gids, gid, gsz, gch = [], 0, 0, 0
    for i, (lo, so, rb, t) in enumerate(items):
        if i:
            pt = items[i - 1][3]
            gap = lo - (items[i - 1][1] + len(items[i - 1][2]) + 1)
            if ((pt and pt[-1] in END) or hints[i] != hints[i - 1]
                    or gap > MAX_GAP or gsz >= MAX_FRAG or gch >= MAX_CH):
                gid += 1
                gsz = gch = 0
        gids.append(gid)
        gsz += 1
        gch += len(t)

    gtext, gcount = defaultdict(str), Counter()
    for g, it in zip(gids, items):
        gtext[g] += it[3]
        gcount[g] += 1

    for i, (lo, so, rb, t) in enumerate(items):
        hint = hints[i]
        g = gids[i]
        groups[arch].append({
            "id": f"{arch[:-4]}/{base}/{i:04d}",
            "archive": arch,
            "file": fn,
            "index": i,
            "category": cat,
            "speaker_hint": hint,
            "ja": t,
            "ko": "",
            "chars": len(t),
            "max_chars": limit,
            "group": {
                "id": f"{base}/g{g:04d}",
                "size": gcount[g],
                "pos": gids[:i + 1].count(g) - 1,
                "ja": gtext[g] if gcount[g] > 1 else None,
            },
            "loc": {"len_off": lo, "str_off": so, "orig_bytes": len(rb) + 1},
        })
        total += 1

index = {
    "game": "Trick x Logic Season 1",
    "game_id": "UCJS-10097",
    "source_iso": "Trick x Logic Season 1.iso",
    "encoding": "cp932 (Shift-JIS)",
    "total_entries": total,
    "string_format": "u32 length(널 포함) + cp932 바이트열 + 0x00",
    "display_limits": {
        "adv_dialogue": {
            "max_chars": ADV_LIMIT, "chars_per_line": 22, "lines": 2,
            "note": "대사창 실측 폭 약 367px, 전각 advance 17px 기준. "
                    "대사 전용 파일들의 원문 최대가 정확히 44자로 일치."
        },
        "long_text": {
            "note": "시나리오 본체/question/tips/inspiration 은 별도 창을 쓰며 "
                    "entry 의 max_chars(해당 파일 원문 관측 최대)를 상한으로 삼을 것."
        }
    },
    "translation_notes": [
        "ko 필드에 한국어 번역을 채운다. 비워두면 원문 유지로 처리.",
        "speaker_hint 는 직전 캐릭터 표시 명령에서 유추한 '화면에 나온 인물'이라 "
        "실제 화자와 다를 수 있다. 참고용으로만 쓸 것.",
        "원문에는 개행/제어문자가 전혀 없다. 게임이 자동 줄바꿈하므로 번역문에도 개행을 넣지 말 것.",
        "한글은 전각이라 일본어와 폭이 같다. max_chars 를 넘기지 말 것.",
        "loc 은 재삽입용 위치 정보이니 수정하지 말 것.",
        "대사는 문장 단위가 아니라 조각으로 저장돼 있다(루비/강조/키워드 표시 때문). "
        "group.ja 가 있으면 그 그룹 전체를 하나의 문장으로 보고 번역한 뒤, "
        "각 조각의 ko 에 자연스럽게 나눠 담을 것.",
        "조각 경계를 원문과 똑같이 맞출 필요는 없다. 길이 필드가 있어 자유롭게 "
        "조절 가능하므로, 한 조각에 몰아넣고 나머지를 빈 문자열로 둬도 된다.",
        "group.pos 는 그룹 내 순서, group.size 는 그룹의 조각 수.",
    ],
    "files": [],
}

for arch, rows in sorted(groups.items()):
    name = arch[:-4] + '.json'
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        json.dump({"archive": arch, "count": len(rows), "entries": rows},
                  f, ensure_ascii=False, indent=1)
    cats = Counter(r['category'] for r in rows)
    over = sum(1 for r in rows if r['chars'] > ADV_LIMIT)
    index["files"].append({"file": name, "archive": arch, "entries": len(rows),
                           "over_44": over, "categories": dict(cats)})
    print(f"  {name:<16} {len(rows):>6,}개  44자초과 {over:>4}")

with open(os.path.join(OUT, '_index.json'), 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, indent=1)

print(f"\n총 {total:,}개 -> {OUT}")
