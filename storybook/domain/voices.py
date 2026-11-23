"""목소리 배정 규칙: 등장인물마다 화자 고르기, 줄마다 말투 지시 만들기."""


def emotion_instruct(base: str, emotion: str) -> str:
    """기본 음색·말투 + 이 줄의 감정 → TTS 말투 지시."""
    return " ".join(x for x in (base, f"이번 문장은 {emotion} 말하세요." if emotion else "") if x)


def narrator_instruct(narrator_timbre: str, feel: str, emotion: str) -> str:
    """해설 한 줄의 말투 지시 (책 만들 때와 인사말 미리 만들기에서 똑같이 써야 TTS 캐시가 맞음)."""
    base = " ".join(x for x in (narrator_timbre, feel) if x)
    return emotion_instruct(base, emotion)


def pick_speaker(voice_type: str, default_speaker: str, alternatives: list[str], narrator: str,
                 taken: set[str], same_as_narrator: bool = False) -> str:
    """등장인물의 화자.

    - same_as_narrator: 해설자 한 명이 모든 인물을 연기
    - 아니면 해설자·다른 인물과 겹치지 않게, 대신 고를 때도 같은 성별·나이대 후보(alternatives) 안에서
    """
    if same_as_narrator:
        return narrator
    cands = [default_speaker] + [s for s in alternatives if s != default_speaker]
    used = {narrator} | taken
    free = [s for s in cands if s not in used]
    not_narrator = [s for s in cands if s != narrator]
    return (free or not_narrator or cands)[0]
