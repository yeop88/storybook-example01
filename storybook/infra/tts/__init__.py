"""TTS 어댑터: story_app 이 띄우는 TTS 전용 작업 프로세스(worker.py)와 주고받음.

본 프로세스 쪽에서는 일반 함수처럼 쓴다: start() / status() / stream() / synthesize().
"""

import itertools
import multiprocessing as mp
import queue
import sys
import threading
import time
import types
from collections.abc import Iterator

import numpy as np

from storybook import config
from storybook.infra.runtime import shared

SR = config.SR


class _WorkerClient:
    def __init__(self):
        self._ctx = mp.get_context("spawn")
        self.req_q = self._ctx.Queue()
        self.resp_q = self._ctx.Queue()
        self.proc = None
        self.status = "대기"
        self.ready = False
        self.loaded = False
        self.jobs: dict[int, queue.Queue] = {}
        self.ids = itertools.count()
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.proc is not None:
                return
            from storybook.infra.tts import worker

            self.status = "작업 프로세스 시작 중"
            self.proc = self._ctx.Process(target=worker.run, args=(self.req_q, self.resp_q), daemon=True,
                                          name="story-tts-worker")
            # Windows(spawn)는 새 프로세스에서 주 스크립트(app.py, Streamlit 화면)를 다시 실행하려 함
            # → 잠깐 빈 __main__ 으로 바꿔 두면 worker.run 만 불러와 실행
            main = sys.modules["__main__"]
            sys.modules["__main__"] = types.ModuleType("__main__")
            try:
                self.proc.start()
            finally:
                sys.modules["__main__"] = main
            threading.Thread(target=self._dispatch, daemon=True, name="tts-dispatch").start()

    def _dispatch(self):
        """작업 프로세스가 보낸 상태·음성 조각을 요청한 쪽으로 나눠 줌."""
        while True:
            msg = self.resp_q.get()
            if msg[0] == "status":
                _, self.status, self.ready, self.loaded = msg
            elif q := self.jobs.get(msg[1]):
                q.put(msg)

    def wait_ready(self, timeout: float) -> bool:
        t0 = time.time()
        while not self.loaded and time.time() - t0 < timeout:
            if self.proc is not None and not self.proc.is_alive():
                self.status = f"오류: TTS 작업 프로세스가 종료됨 (exit {self.proc.exitcode})"
                return False
            time.sleep(0.2)
        return self.ready

    def stream(self, text, speaker, language, instruct, priority) -> Iterator[np.ndarray]:
        self.start()
        if not self.wait_ready(900):
            raise RuntimeError(f"TTS 모델을 쓸 수 없습니다: {self.status}")
        job_id = next(self.ids)
        q: queue.Queue = queue.Queue()
        self.jobs[job_id] = q
        self.req_q.put((job_id, text, speaker, language, instruct, float(priority)))
        try:
            while True:
                kind, _, payload = q.get()
                if kind == "chunk":
                    yield payload
                else:
                    if payload:
                        raise RuntimeError(payload)
                    return
        finally:
            self.jobs.pop(job_id, None)


def _client() -> _WorkerClient:
    return shared("tts_client", _WorkerClient)


def start():
    """TTS 작업 프로세스를 띄우고 모델 불러오기 시작 (최적화 컴파일 포함, 처음 약 2분 / 이후 약 40초)."""
    _client().start()


def status() -> dict:
    c = _client()
    return {"ready": c.ready, "status": c.status}


def wait_ready(timeout: float = 900) -> bool:
    return _client().wait_ready(timeout)


def stream(text: str, speaker: str, language: str = "Korean", instruct: str = "",
           priority: float = 0.0) -> Iterator[np.ndarray]:
    """텍스트 → float32 24kHz mono 조각을 생성되는 대로. priority 가 작을수록 먼저 만듦."""
    yield from _client().stream(text, speaker, language, instruct, priority)


def synthesize(text: str, speaker: str, language: str = "Korean", instruct: str = "",
               priority: float = 0.0) -> np.ndarray:
    parts = list(stream(text, speaker, language, instruct, priority))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


__all__ = ["SR", "start", "status", "wait_ready", "stream", "synthesize"]
