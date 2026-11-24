"""이야기 LLM 서버(FREETOKEN / OPENAI) 연결 확인. 모델(TTS·그림)이 없어도 바로 돎.

.env 의 설정으로 서버마다: ① 모델 이름 확인 → ② 짧은 동화(1장×2쪽)를 스트리밍으로 받아 첫 응답·전체 시간 측정
→ ③ 외국 글자 고치기 · 선택지 만들기 짧은 호출.

사용: .venv\\Scripts\\python.exe scripts\\check_llm.py             (설정된 서버 모두)
      .venv\\Scripts\\python.exe scripts\\check_llm.py FREETOKEN   (하나만)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import openai  # noqa: E402

from storybook import config  # noqa: E402
from storybook.infra import llm  # noqa: E402

HINTS = {
    openai.AuthenticationError: "API 키가 거부됨 (401) → .env 의 *_API_KEY 값을 확인하세요.",
    openai.NotFoundError: "주소나 모델 이름이 틀림 (404) → *_BASE_URL 끝이 /v1 인지, *_MODEL 이름이 맞는지 확인하세요.",
    openai.APIConnectionError: "서버에 연결할 수 없음 → *_BASE_URL 의 IP·포트, 사내망 접속, 서버가 켜져 있는지 확인하세요.",
    openai.RateLimitError: "요청 한도·잔액 부족 (429) → 잠시 뒤 다시 하거나 계정 사용량을 확인하세요.",
}


def check(name: str) -> bool:
    print(f"\n=== {name} ===")
    try:
        t = time.time()
        print(f"모델: {llm.model_name(name)} ({time.time() - t:.1f}초)")
        req = {"theme": "용감한 꼬마 다람쥐", "age": "6~8세", "language": "Korean", "chapters": 1, "pages_per": 2}
        raw, n, first, t0 = [], {}, None, time.time()
        for ev in llm.stream_story(name, req, raw):
            first = first or time.time() - t0
            n[ev["type"]] = n.get(ev["type"], 0) + 1
            if ev["type"] in ("title", "intro") or (ev["type"] == "line" and n["line"] <= 2):
                print(f"  {ev['type']:5} {ev.get('who', '')} {ev.get('text', '')}  [{ev.get('emotion', '')}]")
        print(f"동화: 첫 줄 {first or 0:.1f}초, 전체 {time.time() - t0:.1f}초, 줄 수 {n}")
        if n.get("page") != 2:
            print(f"  ⚠ 쪽수 {n.get('page', 0)} (요청 2) — 앱에서는 모자라면 이어 쓰기로 맞춤")
        t = time.time()
        print(f"외국 글자 고치기: {llm.fix_foreign(name, '다람쥐는 정말 happy 했어요.')} ({time.time() - t:.1f}초)")
        t = time.time()
        print(f"선택지 만들기: {llm.make_choice(name, raw)} ({time.time() - t:.1f}초)")
        print("✅ 정상")
        return True
    except Exception as e:  # noqa: BLE001
        hint = next((h for cls, h in HINTS.items() if isinstance(e, cls)), "")
        print(f"❌ 실패: {type(e).__name__}: {e}\n   {hint}")
        return False


def main():
    names = [a.upper() for a in sys.argv[1:]] or list(config.LLM_PROVIDERS)
    if not config.LLM_PROVIDERS:
        sys.exit("설정된 LLM 서버가 없습니다. .env 에 FREETOKEN_BASE_URL 또는 OPENAI_API_KEY 를 채우세요.")
    missing = [x for x in names if x not in config.LLM_PROVIDERS]
    if missing:
        sys.exit(f"{missing} 는 .env 에 설정되지 않았습니다. 설정된 서버: {list(config.LLM_PROVIDERS)}")
    ok = [check(x) for x in names]
    sys.exit(0 if all(ok) else 1)


if __name__ == "__main__":
    main()
