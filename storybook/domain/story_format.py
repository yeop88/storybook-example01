"""LLM 이 쓰는 이야기 형식 (JSON Lines) 해석.

한 줄에 JSON 하나씩:
  {"type": "title", "text"}
  {"type": "intro", "text", "emotion"}            표지에서 제목 다음에 읽을 도입 인사
  {"type": "cover", "scene"}
  {"type": "character", "name", "look", "voice", "tone"}
  {"type": "chapter", "no", "title"}
  {"type": "page", "no", "scene", "cast": [이름...]}     새 페이지 + 첫 삽화
  {"type": "scene", "scene", "cast": [이름...]}          페이지 중간 삽화 전환 (다음 줄부터)
  {"type": "line", "who", "text", "emotion"}
  {"type": "choice", "question", "options": [...]}      선택형 동화의 장 끝 질문
"""

import json
import re

NARRATOR = "해설"

_FIELD = re.compile(r'"(type|text|scene|name|look|voice|tone|who|emotion|title)"\s*:\s*"((?:[^"\\]|\\.)*)"')
_NO = re.compile(r'"no"\s*:\s*(\d+)')
_CAST = re.compile(r'"cast"\s*:\s*\[([^\]]*)\]')
_OPTIONS = re.compile(r'"options"\s*:\s*\[([^\]]*)\]')
_QUESTION = re.compile(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"')
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')

# 한국어 문장에 섞이면 안 되는 글자: 일본어 가나, 한자(CJK), 호환 한자 / 영어 단어(3글자 이상)
_FOREIGN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")


def clean(s) -> str:
    """공백 정리 + 앞뒤 따옴표 제거."""
    return re.sub(r"\s+", " ", str(s or "")).strip().strip("\"'“”‘’")


def parse_line(raw: str) -> dict | None:
    """JSON Lines 한 줄 → 이벤트 (type 이 없거나 JSON 이 아니면 None). 괄호를 틀리게 닫은 줄도 최대한 살림."""
    raw = raw.strip().strip("`").strip()
    if raw.startswith("json"):
        raw = raw[4:].strip()
    if not raw.startswith("{"):
        return None
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        ev = parse_loose(raw)  # 작은 모델이 괄호를 틀리게 닫는 경우 등
    return ev if isinstance(ev, dict) and ev.get("type") else None


def parse_loose(raw: str) -> dict | None:
    """깨진 JSON 한 줄에서 필드만 뽑아냄."""
    ev = {k: v.replace('\\"', '"') for k, v in _FIELD.findall(raw)}
    if m := _NO.search(raw):
        ev["no"] = int(m.group(1))
    if m := _OPTIONS.search(raw):
        ev["options"] = _STRING.findall(m.group(1))
    if m := _QUESTION.search(raw):
        ev["question"] = m.group(1)
    if m := _CAST.search(raw):
        ev["cast"] = _STRING.findall(m.group(1))
    return ev or None


def has_foreign(text: str) -> bool:
    """한국어 문장에 한자·일본어 글자나 영어 단어(3글자 이상)가 섞였는지."""
    return bool(_FOREIGN.search(text or "") or _LATIN_WORD.search(text or ""))


def strip_foreign(text: str) -> str:
    """섞인 외국 글자를 지운 문장 (고치기에 실패했을 때의 마지막 수단)."""
    return clean(_LATIN_WORD.sub("", _FOREIGN.sub("", text or "")))


def story_text(raw: str, limit: int = 2500) -> str:
    """지금까지 쓴 원문 → 읽은 문장만 (제목·대사·해설), 끝에서 limit 글자."""
    out = []
    for line in raw.split("\n"):
        ev = parse_line(line)
        if ev and ev.get("type") in ("title", "line") and ev.get("text"):
            out.append(clean(ev["text"]))
    return "\n".join(out)[-limit:]


def cut_after_choice(raw: str) -> str:
    """이어 쓰기용 원문을 choice 줄까지만 남김 (LLM 이 그 뒤를 더 썼어도 버림)."""
    i = raw.rfind('"choice"')
    j = raw.find("\n", i) if i != -1 else -1
    return raw[: j + 1] if j != -1 else raw + "\n"


def cut_before_next_chapter(raw: str) -> str:
    """이어 쓰기용 원문에서 다음 장을 시작한 page/chapter 줄부터 뒤를 버림."""
    lines = raw.split("\n")
    while lines:
        ev = parse_line(lines.pop())
        if ev and ev.get("type") in ("page", "chapter"):
            break
    while lines and (ev := parse_line(lines[-1])) and ev.get("type") == "chapter":
        lines.pop()
    return "\n".join(lines) + "\n"
