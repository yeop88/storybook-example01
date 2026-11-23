"""책 만들기 차례 관리: 동시에 최대 MAX_BOOKS_AT_ONCE 권, 먼저 누른 순서대로.

TTS 가 곧 재생될 문장부터 만들도록 우선순위를 주므로 2권까지는 둘 다 실시간을 유지.
선택형 동화가 아이의 대답을 받고 다시 이어 쓸 때는 대기열 맨 앞에 섬.
"""

import threading
from collections.abc import Callable

from storybook import config
from storybook.infra.runtime import shared


def _state() -> dict:
    return shared("scheduler", lambda: {"cv": threading.Condition(), "making": [], "waiting": []})


def status() -> dict:
    """지금 만드는 책 / 기다리는 책 (화면 표시용)."""
    s = _state()
    with s["cv"]:
        return {"making": list(s["making"]), "waiting": list(s["waiting"]), "limit": config.MAX_BOOKS_AT_ONCE}


def acquire(book_id: str, resumed: bool = False, on_wait: Callable[[int], None] | None = None):
    """차례가 올 때까지 기다림. on_wait(앞에 있는 책 수) 를 1초마다 부름."""
    s = _state()
    with s["cv"]:
        if resumed:
            s["waiting"].insert(0, book_id)
        else:
            s["waiting"].append(book_id)
        while not (len(s["making"]) < config.MAX_BOOKS_AT_ONCE and s["waiting"][0] == book_id):
            if on_wait:
                on_wait(s["waiting"].index(book_id) + len(s["making"]))
            s["cv"].wait(1.0)
        s["waiting"].remove(book_id)
        s["making"].append(book_id)


def release(book_id: str):
    s = _state()
    with s["cv"]:
        if book_id in s["making"]:
            s["making"].remove(book_id)
        s["cv"].notify_all()
