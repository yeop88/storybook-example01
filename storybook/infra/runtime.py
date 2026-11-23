"""프로세스 공용 객체 보관소.

Streamlit 은 화면을 다시 그릴 때 모듈을 다시 import 할 수 있어서, 모델처럼 한 번만 만들어야 하는 객체는
`sys` 에 보관해 프로세스가 끝날 때까지 하나만 쓰게 한다.
"""

import sys
import threading

_LOCK_NAME = "_storybook_singleton_lock"


def _lock() -> threading.RLock:
    # RLock: 객체를 만드는 중에 다른 공용 객체를 꺼내도(예: 시작 준비 → TTS 엔진) 스스로 막히지 않게
    if not hasattr(sys, _LOCK_NAME):
        setattr(sys, _LOCK_NAME, threading.RLock())
    return getattr(sys, _LOCK_NAME)


def shared(name: str, factory):
    """프로세스당 하나만 만들어 재사용."""
    attr = f"_storybook_{name}"
    with _lock():
        if not hasattr(sys, attr):
            setattr(sys, attr, factory())
    return getattr(sys, attr)


# 받아쓰기·그림 모델이 같은 GPU 를 쓰므로 한 번에 하나씩 (TTS 는 전용 GPU 스레드가 따로 처리)
GPU_LOCK: threading.Lock = shared("gpu_lock", threading.Lock)
