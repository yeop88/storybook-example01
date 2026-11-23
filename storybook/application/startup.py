"""서버 시작 준비: 모델을 백그라운드로 미리 올리고, 누르자마자 읽을 인사말을 미리 만들어 둠.

- TTS 는 전용 작업 프로세스(infra/tts/worker.py)에서 따로 불러옴 → 바로 시작 (처음 약 2분, 이후 약 40초)
- 받아쓰기·그림은 이 프로세스의 한 스레드에서 차례대로 불러옴
  (여러 스레드가 transformers 를 동시에 처음 import 하면 지연 로딩이 꼬여 import 오류가 날 수 있음)
- TTS 가 준비되면 그림 한 장을 미리 그리고, 인사말을 미리 만들어 TTS 캐시에 넣어 둠 (캐시는 다음 실행에도 남음)
"""

import threading
import time

from storybook import config
from storybook.domain.voices import narrator_instruct
from storybook.infra import painter, stt, tts
from storybook.infra.runtime import shared


def start():
    """프로세스당 한 번만 실행 (화면 스크립트는 막지 않음)."""
    shared("startup", _start)


def _start():
    tts.start()
    threading.Thread(target=_load_all, daemon=True, name="load-models").start()
    return True


def _load_all():
    for load in (stt.load, painter.load):
        try:
            load()
        except Exception as e:  # noqa: BLE001
            print(f"[startup] {load.__module__} 불러오기 실패: {e}", flush=True)
    try:  # 첫 그림은 느리므로 실제 크기로 한 장 미리 그려 둠
        painter.paint("a cute rabbit in a meadow, watercolor")
    except Exception:  # noqa: BLE001
        pass
    if tts.wait_ready():
        _prewarm_greetings()


def _prewarm_greetings():
    """모든 해설자 × 해설 느낌 × 인사말을 낮은 우선순위로 만들어 TTS 캐시에 넣어 둠
    → 동화 만들기를 누르면 인사말이 캐시에서 바로 나오고, 그동안 LLM 이 제목을 씀.
    책을 만드는 동안에는 쉼: 이미 시작한 한 문장은 끝까지 GPU 를 차지해 책 낭독이 끊길 수 있음."""
    from storybook.application import scheduler

    for speaker, timbre in config.NARRATORS.values():
        for feel in config.VOICES.values():
            for text in config.GREETINGS:
                while scheduler.status()["making"]:
                    time.sleep(1.0)
                try:
                    tts.synthesize(text, speaker, "Korean", narrator_instruct(timbre, feel, config.GREETING_EMOTION),
                                   priority=1000)
                except Exception:  # noqa: BLE001
                    return


def status() -> dict:
    t = tts.status()
    return {"tts": t["status"], "tts_ready": t["ready"], "stt": stt.status(), "paint": painter.status()}
