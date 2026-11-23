"""이야기 쓰기: 내부 네트워크 OpenAI 호환 LLM (think 끔), 실시간 스트리밍.

LLM 이 한 줄에 JSON 하나씩(JSON Lines) 쓰게 하고, 줄이 완성되는 즉시 이벤트로 넘깁니다.
→ 이야기를 다 쓰기 전에 제목·첫 문장부터 바로 읽기 시작할 수 있음.

이벤트 종류
  {"type": "title", "text"}
  {"type": "intro", "text", "emotion"}            표지에서 제목 다음에 읽을 도입 인사
  {"type": "cover", "scene"}
  {"type": "character", "name", "look", "voice", "tone"}
  {"type": "page", "scene", "cast": [이름...]}     새 페이지 + 첫 삽화
  {"type": "scene", "scene", "cast": [이름...]}    페이지 중간 삽화 전환 (다음 줄부터)
  {"type": "line", "who", "text", "emotion"}
"""

import json
import re
from collections.abc import Iterator
from functools import lru_cache

import httpx
from openai import OpenAI

import config

NARRATOR = "해설"


@lru_cache(maxsize=None)
def client(name: str) -> OpenAI:
    p = config.LLM_PROVIDERS[name]
    # 연결 자체가 안 되면 5초 안에 포기하고 다른 서버로 넘어가도록
    return OpenAI(base_url=p["base_url"], api_key=p["api_key"], timeout=httpx.Timeout(240, connect=5), max_retries=0)


@lru_cache(maxsize=None)
def model_name(name: str) -> str:
    return config.LLM_PROVIDERS[name]["model"] or client(name).models.list().data[0].id


SYSTEM = f"""당신은 아이들을 위한 그림 동화 작가이자 오디오북 연출가입니다.
요청에 맞는 그림 동화를 쓰고, 성우가 읽을 수 있도록 줄마다 말투와 감정을 연출하세요.

출력 형식: JSON Lines — 한 줄에 JSON 객체 하나씩, 아래 순서대로. 코드 블록(```)이나 다른 설명은 절대 쓰지 마세요.
{{"type": "title", "text": "동화 제목"}}
{{"type": "intro", "text": "표지에서 읽을 짧은 도입 인사 1~2문장", "emotion": "읽는 감정·말투 지시"}}
{{"type": "cover", "scene": "표지 그림 장면 (영어)"}}
{{"type": "character", "name": "인물 이름", "look": "생김새 (영어, 종·색·옷·특징을 자세히 — 모든 그림에서 똑같이 그려지도록)", "voice": "{'|'.join(config.VOICE_TYPES)} 중 하나", "tone": "이 인물의 기본 말투 (한국어)"}}
  (등장인물 수만큼 character 줄)
{{"type": "chapter", "no": 1, "title": "장 제목"}}
  (장이 여러 개일 때만, 각 장의 첫 page 바로 앞에)
{{"type": "page", "no": 1, "scene": "이 페이지 그림 장면 (영어, 누가 어디서 무엇을 하는지)", "cast": ["이 페이지에 나오는 인물 이름"]}}
{{"type": "line", "who": "{NARRATOR}", "text": "해설 문장", "emotion": "읽는 감정·말투 지시"}}
{{"type": "line", "who": "인물 이름", "text": "대사 (따옴표 없이)", "emotion": "말투·감정 지시"}}
{{"type": "scene", "scene": "바뀐 장면의 삽화 (영어)", "cast": ["이 장면에 나오는 인물 이름"]}}
{{"type": "line", ...}}
  (페이지마다 page 한 줄 뒤에 line 2~5줄. scene 은 필요할 때만)
{{"type": "choice", "question": "아이에게 묻는 말", "options": ["첫 번째 선택", "두 번째 선택"]}}
  (선택형 동화로 요청받았을 때만. 장의 마지막 쪽 끝에 쓰고 거기서 멈춤)

분량 규칙 (매우 중요):
- page 의 no 는 1부터 차례로 매기는 전체 쪽 번호입니다. 요청한 쪽수와 정확히 같은 개수의 page 를 쓰세요.
  모자라거나 넘치면 안 됩니다. 마지막 page 의 no 가 요청한 전체 쪽수와 같아야 하고, 그 쪽에서 이야기를 마무리하세요.
- 장이 여러 개면 각 장은 요청한 쪽수만큼 정확히 쓰고, 장마다 작은 사건과 마무리가 있게 하세요.

도입 규칙:
- intro 는 title 바로 다음 줄에 꼭 쓰세요. 듣는 아이에게 말을 건네듯 이야기의 분위기만 살짝 알려 주는 1~2문장
  (예: "오늘은 깊은 바닷속에 사는 아주 특별한 꼬마 문어의 이야기를 들려줄게요."). 줄거리를 미리 말하지는 마세요.

삽화 규칙:
- page 의 scene 이 그 페이지 첫 삽화입니다.
- 페이지 중간에 장소가 바뀌거나, 새 인물이 등장하거나, 결정적인 사건이 일어나는 등 그림이 달라져야 하는 순간에만
  그 줄 바로 앞에 scene 줄을 넣으세요. 페이지마다 0~1개, 이야기 전체에서 2~4개 정도.
- scene 은 그 순간의 모습을 한 장면으로 구체적으로 (누가, 어디서, 무엇을, 표정·분위기).

연출 규칙:
- 해설과 등장인물들의 대화를 섞어 생동감 있게 쓰세요. 인물끼리 주고받는 대화가 많을수록 좋습니다.
- emotion 은 한국어로 아주 구체적으로 쓰세요. 감정 + 세기 + 속도 + 높낮이 + 숨·떨림·웃음 같은 표현을 담으세요.
  좋은 예: "깜짝 놀라 숨을 들이켜며 높고 빠르게", "속상해서 울먹이며 작고 떨리는 목소리로 천천히",
  "신이 나서 웃음을 참지 못하고 통통 튀듯 밝게", "비밀을 말하듯 낮게 속삭이며", "졸려서 하품 섞인 늘어지는 목소리로".
  나쁜 예: "기쁘게", "보통".
- 해설의 emotion 도 장면 분위기에 맞게 바꾸세요 (긴장감 있게, 설레게, 포근하게 등).
- 한국어 본문(title, intro, text, 장 제목)에는 한자·중국어·일본어 글자를 절대 쓰지 마세요. 순우리말·한글로만 쓰세요.
- text 는 소리 내어 읽습니다. 마크다운·이모지·괄호 설명·따옴표 없이 자연스러운 구어체로, 한 줄은 1~2문장으로 짧게.
- 시작, 사건, 해결, 따뜻한 마무리가 있어야 합니다. 무섭거나 폭력적인 내용은 넣지 마세요.
- voice 는 인물의 나이·성별에 맞게 고르세요. 아이 주인공(꼬마 동물 포함)은 girl/boy, 엄마·아빠는 woman/man,
  할머니·할아버지는 grandma/grandpa, 요정·작은 동물·사물 친구는 creature. 인물끼리 되도록 다른 voice 를 쓰세요.
- who 는 "{NARRATOR}" 또는 character 의 name 과 정확히 같아야 합니다.
- scene, look 은 그림 생성용이므로 반드시 영어로 쓰고, 글자나 말풍선은 넣지 마세요."""


def clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().strip("\"'“”‘’")


def _event(raw: str) -> dict | None:
    raw = raw.strip().strip("`").strip()
    if raw.startswith("json"):
        raw = raw[4:].strip()
    if not raw.startswith("{"):
        return None
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        ev = _loose(raw)  # 작은 모델이 괄호를 틀리게 닫는 경우 등
    return ev if isinstance(ev, dict) and ev.get("type") else None


_FIELD = re.compile(r'"(type|text|scene|name|look|voice|tone|who|emotion|title)"\s*:\s*"((?:[^"\\]|\\.)*)"')
_NO = re.compile(r'"no"\s*:\s*(\d+)')
_CAST = re.compile(r'"cast"\s*:\s*\[([^\]]*)\]')
_OPTIONS = re.compile(r'"options"\s*:\s*\[([^\]]*)\]')
_QUESTION = re.compile(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _loose(raw: str) -> dict | None:
    """깨진 JSON 한 줄에서 필드만 뽑아냄."""
    ev = {k: v.replace('\\"', '"') for k, v in _FIELD.findall(raw)}
    if m := _NO.search(raw):
        ev["no"] = int(m.group(1))
    if m := _OPTIONS.search(raw):
        ev["options"] = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
    if m := _QUESTION.search(raw):
        ev["question"] = m.group(1)
    if m := _CAST.search(raw):
        ev["cast"] = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))
    return ev or None


def _request_text(req: dict) -> str:
    c, p = req["chapters"], req["pages_per"]
    total = c * p
    lang = "영어(English) — text 만 영어, emotion·tone 은 한국어" if req["language"] == "English" else "한국어"
    out = [f"주제: {req['theme']}", f"독자: {config.AGES[req['age']]}", f"본문 언어: {lang}"]
    if c > 1:
        out.append(f"구성: {c}개 장, 장마다 정확히 {p}쪽 → 전체 정확히 {total}쪽 (page no 1~{total})")
        for i in range(c):
            o = (req.get("outline") or [{}] * c)[i] if i < len(req.get("outline") or []) else {}
            first, last = i * p + 1, (i + 1) * p
            line = f"  {i + 1}장 (page {first}~{last})"
            if o.get("title"):
                line += f" 제목: {o['title']}"
            if o.get("plot"):
                line += f" / 줄거리: {o['plot']}"
            out.append(line)
    else:
        out.append(f"분량: 정확히 {total}쪽 (page no 1~{total}, chapter 줄은 쓰지 마세요)")
    if req.get("interactive") and c > 1:
        out.append("선택형 동화: 마지막 장을 뺀 각 장의 마지막 page 끝에 choice 줄을 쓰고 바로 멈추세요 (그 뒤는 쓰지 마세요). "
                   "아이가 고른 선택에 따라 다음 장을 이어 쓰게 됩니다. 선택지는 둘 다 재미있고 안전한 길로, 짧고 쉽게.")
    if req.get("hero"):
        out.append(f"주인공 이름: {req['hero']}")
    if req.get("lesson"):
        out.append(f"담고 싶은 교훈: {req['lesson']}")
    return "\n".join(out)


def _stream(provider: str, messages: list[dict], raw: list[str]) -> Iterator[dict]:
    stream = client(provider).chat.completions.create(
        model=model_name(provider), messages=messages, max_tokens=12000, temperature=0.8, stream=True,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},  # think 끔
    )
    buf = ""
    try:
        for chunk in stream:
            if not (chunk.choices and chunk.choices[0].delta.content):
                continue
            piece = chunk.choices[0].delta.content
            raw.append(piece)
            buf += piece
            *done, buf = buf.split("\n")
            for line in done:
                if ev := _event(line):
                    yield ev
        for line in buf.split("\n"):
            if ev := _event(line):
                yield ev
    finally:
        # 중간에 멈추면(선택형 질문 등) 연결을 바로 끊어 서버가 남은 글을 계속 쓰지 않게 → 다음 요청이 바로 시작
        stream.close()


def stream_story(provider: str, req: dict, raw: list[str]) -> Iterator[dict]:
    """이야기 이벤트를 쓰는 대로. raw 에 원문을 모아 둠 (이어 쓰기용)."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _request_text(req)}]
    yield from _stream(provider, messages, raw)


def continue_story(provider: str, req: dict, raw: list[str], pages_done: int, choice: str = "") -> Iterator[dict]:
    """쪽수가 모자랄 때: 지금까지 쓴 내용 뒤에 이어서 나머지 쪽을 쓰게 함."""
    total = req["chapters"] * req["pages_per"]
    per = req["pages_per"]
    so_far = "".join(raw)
    chapter_hint = ""
    if req["chapters"] > 1 and pages_done % per == 0 and pages_done < total:
        nxt = pages_done // per + 1
        chapter_hint = f' 다음 쪽부터 {nxt}장이 시작되니, 먼저 {{"type": "chapter", "no": {nxt}, "title": "장 제목"}} 줄을 쓰세요.'
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _request_text(req)},
        {"role": "assistant", "content": so_far},
        {"role": "user", "content": (
            f"아직 {pages_done}쪽까지만 썼습니다. 요청한 전체 쪽수는 정확히 {total}쪽입니다. "
            f"page no {pages_done + 1} 부터 {total} 까지 같은 JSON Lines 형식으로 이어서 쓰고, 마지막 쪽에서 이야기를 마무리하세요. "
            "title, cover, character 줄은 다시 쓰지 마세요. 이미 쓴 내용은 반복하지 마세요." + chapter_hint
            + (f" 아이가 고른 선택: '{choice}'. 바로 이어지는 다음 장은 이 선택대로 펼쳐지게 쓰세요." if choice else ""))},
    ]
    raw.append("\n")
    yield from _stream(provider, messages, raw)


# ---------------------------------------------------------------------------
# 외국 글자 섞임 수정 (Qwen 계열 LLM 이 가끔 한국어 문장에 한자·중국어를 섞음 → TTS 가 중국어로 읽음)
# ---------------------------------------------------------------------------
_FOREIGN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


def has_foreign(text: str) -> bool:
    return bool(_FOREIGN.search(text or ""))


def fix_foreign(provider: str, text: str) -> str:
    """한자·중국어·일본어가 섞인 한국어 문장을 자연스러운 한글 문장으로 (짧은 LLM 호출, 실패하면 그 글자만 지움)."""
    try:
        r = client(provider).chat.completions.create(
            model=model_name(provider), max_tokens=300, temperature=0.2,
            messages=[{"role": "system", "content": "다음 한국어 문장에 섞인 한자·중국어·일본어를 뜻이 같은 자연스러운 한국어(한글)로 바꾸세요. "
                                                    "다른 부분은 그대로 두고, 고친 문장 하나만 출력하세요."},
                      {"role": "user", "content": text}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        fixed = clean(re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S))
        if fixed and not has_foreign(fixed):
            return fixed
    except Exception:  # noqa: BLE001
        pass
    return clean(_FOREIGN.sub("", text))


def make_choice(provider: str, req: dict, raw: list[str]) -> dict:
    """선택형 동화: 지금까지의 이야기 → 다음 장에서 아이가 고를 질문 1개 + 선택지 2개 (짧은 LLM 호출, 1~2초)."""
    story = []
    for line in "".join(raw).split("\n"):
        ev = _event(line)
        if ev and ev.get("type") in ("title", "line") and ev.get("text"):
            story.append(clean(ev["text"]))
    text = "\n".join(story)[-2500:]
    fallback = {"question": "그다음에는 어떻게 될까요?", "options": ["용감하게 앞으로 나아가기", "친구에게 도움을 청하기"]}
    try:
        r = client(provider).chat.completions.create(
            model=model_name(provider), max_tokens=300, temperature=0.7,
            messages=[{"role": "system", "content": (
                "당신은 아이를 위한 선택형 동화의 연출가입니다. 지금까지의 이야기를 읽고, 다음 장에서 이야기가 갈 방향을 "
                "아이가 고르도록 묻는 질문 1개와 선택지 2개를 만드세요. 둘 다 재미있고 안전한 길로, 짧고 쉬운 말로. "
                '한글로만 쓰고, JSON 한 줄만 출력: {"question": "...", "options": ["...", "..."]}')},
                {"role": "user", "content": text}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        out = re.sub(r"<think>.*?</think>", "", r.choices[0].message.content or "", flags=re.S)
        m = re.search(r"\{.*\}", out, re.S)
        ev = _event(m.group(0).replace("\n", " ")) if m else None
        if ev is None and m:
            ev = _loose(m.group(0))
        q = clean((ev or {}).get("question"))
        opts = [clean(o) for o in (ev or {}).get("options", []) if clean(o)][:2]
        if q and len(opts) == 2 and not any(has_foreign(x) for x in [q, *opts]):
            return {"question": q, "options": opts}
    except Exception:  # noqa: BLE001
        pass
    return fallback
