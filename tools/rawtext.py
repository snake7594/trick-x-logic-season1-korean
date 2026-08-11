"""길이 접두사가 없는 문자열 — 추리 데이터가 쓰는 또 하나의 문자열 형식.

대사(op 0x01)는 `u32 길이 + cp932 + NUL` 이지만, 추리에 쓰는 데이터에는
**길이 없이 NUL 로만 끝나는** 문자열이 따로 들어 있다. 추출 도구가 이걸
못 봐서 6,770건이 일본어로 남아 있었다.

그중 가장 중요한 것이 **키워드 이름**이다. 게임은 분홍 글자를 눌러 얻은
키워드를 `*_question.bin` / `*_inspiration.bin` 안의 문자열과 **글자 그대로**
대조한다. 본문만 한국어로 바꾸고 이쪽을 그대로 두면 정답 조각을 골라도
추리가 진행되지 않는다.

    분홍 범위의 글자 - 제어 태그(㊤㊥㊦㊧㊨) = 키워드 이름

파일 안에 절대 오프셋 참조가 없는 것을 확인했으므로(문자열 시작을 가리키는
u32 는 206개 중 7개로 우연 수준), 길이를 바꿔 넣어도 안전하다.
"""
import prcs

TAG = '㊤㊥㊦㊧㊨'


def strip_tag(t):
    return ''.join(c for c in t if c not in TAG)


def _covered(d):
    """op 0x01 문자열이 차지한 바이트 — 여기는 건드리지 않는다."""
    out = set()
    for lo, so, raw, t in prcs.find_strings(d):
        out.update(range(lo - 1, so + len(raw) + 1))
    return out


def strings(d, minlen=1):
    """[(오프셋, 원문)] — 길이 접두사 없는 cp932 문자열."""
    cov = _covered(d)
    out, i, n = [], 0, len(d)
    while i < n:
        j = i
        while j < n and d[j] != 0:
            j += 1
        if j > i and i not in cov:
            s = d[i:j]
            if all((0x81 <= c <= 0xFC) or (0x20 <= c < 0x7F) for c in s):
                try:
                    t = s.decode('cp932')
                except Exception:
                    t = None
                if t and len(t) >= minlen:
                    out.append((i, t))
        i = j + 1
    return out


def patch(d, repl):
    """{오프셋: 새 바이트열} 을 반영한 새 바이트열.

    길이가 달라지면 뒤가 밀린다. 오프셋 참조가 없으므로 그래도 된다."""
    if not repl:
        return bytes(d)
    out, pos = bytearray(), 0
    for off in sorted(repl):
        end = d.index(b'\x00', off)
        out += d[pos:off]
        out += repl[off]
        pos = end
    out += d[pos:]
    return bytes(out)
