"""TTS 에 보내기 전 한국어 문장 다듬기 — 숫자를 읽는 말로 ("3살" → "세 살", "2025년" → "이천이십오 년").

화면에 보이는 글은 그대로 두고, 소리로 읽을 글에만 씁니다. 문장 하나에 1ms 미만.
"""

import re

# 고유어 수(하나, 둘...)로 읽는 단위 — 동화에 자주 나오는 것 위주
_NATIVE_COUNTERS = (
    "번째|살|개|마리|명|사람|시간|시|번|권|잔|그루|송이|벌|켤레|가지|군데|척|대|채|달|걸음|방울|조각|알|바퀴|줄|장|쌍|통|"
    "그릇|접시|봉지|상자|발짝|밤|낮"
)
_ONES = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]
_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]
_SINO = "영일이삼사오육칠팔구"
_SINO_UNITS = ["", "십", "백", "천"]
_BIG = ["", "만", "억", "조"]


def native(n: int) -> str:
    """1~99 → 고유어 (단위 앞 형태: 한, 두, 세, 네, 스무)."""
    if n == 20:
        return "스무"
    return _TENS[n // 10] + _ONES[n % 10]


def sino(n: int) -> str:
    """정수 → 한자어 수 (일, 이, 삼 ... 십, 백, 천, 만). '일십' 이 아니라 '십'."""
    if n == 0:
        return "영"
    out, group = [], 0
    while n > 0:
        n, chunk = divmod(n, 10000)
        if chunk:
            s = ""
            for i, d in enumerate(reversed(f"{chunk:04d}")):
                d = int(d)
                if d:
                    s = ("" if d == 1 and i > 0 else _SINO[d]) + _SINO_UNITS[i] + s
            out.append(s + _BIG[group])
        group += 1
    return "".join(reversed(out))


_COUNTER_RE = re.compile(r"(\d+)\s*(" + _NATIVE_COUNTERS + r")")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _counter(m: re.Match) -> str:
    n, unit = int(m.group(1)), m.group(2)
    if unit == "번째":
        return ("첫" if n == 1 else native(n) if 0 < n < 100 else sino(n)) + " 번째"
    if 0 < n < 100:
        return native(n) + " " + unit
    return sino(n) + " " + unit


def _number(m: re.Match) -> str:
    t = m.group(0)
    if "." in t:
        a, b = t.split(".", 1)
        return sino(int(a)) + " 점 " + " ".join(_SINO[int(d)] for d in b)
    return sino(int(t))


def to_speech(text: str) -> str:
    """읽기용 문장: 숫자 → 말, 기호 정리."""
    t = text.replace("%", " 퍼센트").replace("~", " 에서 ").replace("&", " 그리고 ")
    while re.search(r"\d,\d{3}", t):  # 1,000 → 1000
        t = re.sub(r"(\d),(\d{3})", r"\1\2", t)
    t = _COUNTER_RE.sub(_counter, t)
    t = _NUM_RE.sub(_number, t)
    return re.sub(r"\s{2,}", " ", t).strip()


if __name__ == "__main__":
    for s in ["문어는 3살이었어요.", "사과 12개와 물고기 20마리", "1번째 친구, 2번째 친구", "2025년 3월 5일",
              "100명이 모였어요", "오후 3시에 2시간 동안", "50% 할인", "3.5킬로미터", "1,000원"]:
        print(s, "→", to_speech(s))
