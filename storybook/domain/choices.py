"""선택형 동화: 질문 문장 만들기, 아이가 말한 대답을 선택지 번호로 맞추기."""

import re

ORDINALS = ["첫 번째", "두 번째", "세 번째"]
_ORDINAL_WORDS = [("첫", "하나", "일번", "1번", "1"), ("두", "둘", "이번", "2번", "2"), ("세", "셋", "삼번", "3번", "3")]


def question_text(question: str, options: list[str]) -> str:
    """해설자가 읽을 질문: "어디로 갈까요? 첫 번째, 동굴. 두 번째, 숲." """
    return question + " " + " ".join(f"{ORDINALS[i]}, {o}." for i, o in enumerate(options))


def _grams(x: str) -> set[str]:
    x = re.sub(r"[^\w]", "", x)
    return {x[i:i + 2] for i in range(len(x) - 1)} or {x}


def match_choice(text: str, options: list[str]) -> int | None:
    """말한 내용 → 선택지 번호. 선택지 낱말이 들어 있으면 그것, 아니면 '첫 번째/두 번째' 같은 순서 말. 모르면 None."""
    t = re.sub(r"[^\w]", "", text or "")
    if not t or not options:
        return None
    # 두 글자 조각이 겹치는 수 + 선택지 낱말(예: '숲')이 통째로 들어 있으면 가산점
    scores = [len(_grams(o) & _grams(t)) + 2 * sum(1 for w in re.findall(r"\w+", o) if w in t) for o in options]
    best = max(scores)
    if best and scores.count(best) == 1:
        return scores.index(best)
    for i, words in enumerate(_ORDINAL_WORDS):
        if i < len(options) and any(w in t for w in words):
            return i
    return None
