"""길이 접두사가 없는 문자열 — 추리 데이터가 쓰는 또 하나의 문자열 형식.

대사(op 0x01)는 `u32 길이 + cp932 + NUL` 이지만, 추리에 쓰는 데이터에는
**길이 없이 NUL 로만 끝나는** 문자열이 따로 들어 있다. 추출 도구가 이걸
못 봐서 6,770건이 일본어로 남아 있었다.

그중 가장 중요한 것이 **키워드 이름**이다. 게임은 분홍 글자를 눌러 얻은
키워드를 `*_question.bin` / `*_inspiration.bin` 안의 문자열과 **글자 그대로**
대조한다. 본문만 한국어로 바꾸고 이쪽을 그대로 두면 정답 조각을 골라도
추리가 진행되지 않는다.

    분홍 범위의 글자 - 제어 태그(㊤㊥㊦㊧㊨) = 키워드 이름

⚠ 이 문자열들은 **명령의 payload 안에** 들어 있다. PRCS 는
`u8 명령 + u32 payload 길이 + payload` 의 연속이고, 예컨대 op 0xa4 하나가
`"ENV_NF\\0前奏曲第２番\\0Ｇ．ガーシュウィン\\0env_q_b01\\0"` 를 통째로 담는다.
안에서 길이가 바뀌면 **그 명령의 u32 도 같이 고쳐야 한다.** 안 고치면 해석기가
어긋나 게임이 부팅에서 죽는다 — 실제로 그렇게 죽였다(`prcswalk.py` 참고).

대사(op 0x01)는 payload 가 문자열 하나뿐이라 u32 가 곧 문자열 길이다. 그래서
대사만 바꿀 때는 이 구조를 몰라도 우연히 맞아떨어졌다.
"""
import prcs
import prcswalk

TAG = '㊤㊥㊦㊧㊨'


def strip_tag(t):
    return ''.join(c for c in t if c not in TAG)


def _covered(d):
    """**진짜** op 0x01 문자열이 차지한 바이트 — 여기는 건드리지 않는다.

    ⚠ `prcs.find_strings` 는 명령 구조를 안 보고 `u32 길이 + 글자 + NUL` 처럼
    **보이는 자리**를 전부 잡는다. 앞 4바이트가 우연히 길이처럼 보이면 가짜로
    걸린다(README 「가짜 문자열」). 그걸 그대로 덮으면 그 자리에 있던 **진짜
    원시문자열이 가려진다** — `sn7_init.bin` 의 「練習問題　指さす死体」
    (연습문제 시나리오 제목)가 그래서 일본어로 남아 있었다.

    명령 스트림을 걸어 **op 0x01 의 payload 시작**인 것만 덮는다.
    """
    cmds = prcswalk.walk(d)
    real = ({po for _, op, po, _ in cmds if op == 0x01}
            if cmds is not None else None)
    out = set()
    for lo, so, raw, t in prcs.find_strings(d):
        if real is not None and so not in real:
            continue
        out.update(range(lo - 1, so + len(raw) + 1))
    return out


def _sjis_only(s):
    """ASCII 인쇄글자 + 올바른 2바이트 Shift-JIS 짝으로만 이뤄졌는가.

    ⚠ 예전에는 `all((0x81 <= c <= 0xFC) or (0x20 <= c < 0x7F))` 로 **바이트를
    낱개로** 봤다. 그러면 뒤바이트가 **0x80** 인 글자가 든 문자열이 통째로
    빠진다 — `ム`(83 80)·`死`(8E 80) 가 대표적이라
    「ハムレット」「フェティシズム」「バスの乗客は全員死亡している…」 처럼
    TIPS 용어와 착상·조서 문항 **58종**이 일본어로 남아 있었다.
    """
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if 0x20 <= c < 0x7F:
            i += 1
        elif ((0x81 <= c <= 0x9F or 0xE0 <= c <= 0xFC) and i + 1 < n
              and (0x40 <= s[i + 1] <= 0x7E or 0x80 <= s[i + 1] <= 0xFC)):
            i += 2
        else:
            return False
    return True


def strings(d, minlen=1):
    """[(오프셋, 원문)] — 길이 접두사 없는 cp932 문자열."""
    cov = _covered(d)
    out, i, n = [], 0, len(d)
    while i < n:
        j = i
        while j < n and d[j] != 0:
            j += 1
        # 문자열 앞에 제어 바이트가 붙어 있는 자리가 있다. NUL 로만 끊으면
        # 그 바이트까지 문자열에 들어가 통째로 걸러진다 — `sn7_init.bin` 의
        # op 0x99 payload 가 `… ENV_TA\0\0\0\0\0\x01練習問題　指さす死体\0`
        # 라서 「연습문제 가리키는 시체」가 일본어로 남아 있었다.
        while i < j and d[i] < 0x20:
            i += 1
        if j > i and i not in cov:
            s = d[i:j]
            if _sjis_only(s):
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

    길이가 달라지면 뒤가 밀리고, **감싸는 명령의 u32 길이도 같이 밀어야 한다.**
    그 일은 `prcswalk.patch` 가 한다."""
    if not repl:
        return bytes(d)
    return prcswalk.patch(bytes(d), repl)
