"""스트리밍 TTS 엔진 (Qwen3-TTS CustomVoice). TTS 전용 작업 프로세스(worker.py) 안에서 돎.

- GPU 전용 스레드 1개가 모델을 소유 (torch.compile/CUDA graph 는 같은 스레드에서만 안전)
- 요청은 우선순위 대기열로 받음: 숫자가 작을수록 먼저.
  동화는 "재생보다 앞서 만들어 둔 음성(초)" 을 우선순위로 보내 → 여러 권을 동시에 만들 때 곧 끊길 책의 문장부터
- 생성되는 PCM 조각을 StreamJob 으로 바로 흘려보냄 (첫 조각 약 0.2~0.3초)
- 끝까지 만든 문장은 캐시 → 같은 문장(인사말 등)은 즉시
- 시작 시 최적화 컴파일 + 워밍업 (약 2분, 1회). 말투 지시가 있는/없는 경우 모두 미리 컴파일
"""

import hashlib
import itertools
import queue
import threading
import time

import numpy as np
import soundfile as sf
import torch

from storybook import config
from storybook.infra.tts.streaming import stream_custom_voice

SR = config.SR
_WARMUP = (
    ("워밍업입니다.", None),
    ("스트리밍 음성 합성을 준비하고 있습니다. 잠시만 기다려 주세요.", None),
    ("우와, 정말 멋진 무지개다!", "깜짝 놀라 숨을 들이켜며 높고 빠르게 말하세요."),
    ("옛날 옛적, 깊은 숲속에 작은 토끼가 살았어요.", "따뜻하고 다정한 목소리로, 아이에게 동화를 읽어 주듯 천천히 또박또박 읽어 주세요."),
)


class StreamJob:
    """만들고 있는 음성 한 문장. iter_chunks() 로 생성되는 대로 읽음."""

    def __init__(self, text, speaker, language, instruct, key):
        self.text, self.speaker, self.language, self.instruct, self.key = text, speaker, language, instruct, key
        self.chunks: list[np.ndarray] = []
        self.done = False
        self.error: Exception | None = None
        self._cv = threading.Condition()

    def put(self, chunk: np.ndarray):
        with self._cv:
            self.chunks.append(chunk)
            self._cv.notify_all()

    def finish(self, error: Exception | None = None):
        with self._cv:
            self.error, self.done = error, True
            self._cv.notify_all()

    def iter_chunks(self):
        i = 0
        while True:
            with self._cv:
                while i >= len(self.chunks) and not self.done:
                    self._cv.wait(0.2)
                if i >= len(self.chunks):
                    if self.error:
                        raise self.error
                    return
                item = self.chunks[i]
            i += 1
            yield item


class TTSEngine:
    def __init__(self):
        self.ready = threading.Event()
        self.status = "대기"
        self.load_error: Exception | None = None
        self.model = None
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._started = False
        self._start_lock = threading.Lock()

    def start(self):
        """모델 불러오기 시작 (백그라운드, 한 번만)."""
        with self._start_lock:
            if not self._started:
                self._started = True
                self.status = "불러오는 중"
                threading.Thread(target=self._run, daemon=True, name="tts-gpu").start()

    # --- 공개 API -------------------------------------------------------------
    def stream(self, text: str, speaker: str, language: str, instruct: str = "", priority: float = 0.0) -> StreamJob:
        text, instruct = text.strip(), (instruct or "").strip()
        key = hashlib.sha1(f"{text}|{speaker}|{language}|{instruct}".encode()).hexdigest()[:16]
        job = StreamJob(text, speaker, language, instruct, key)
        cached = config.TTS_CACHE_DIR / f"{key}.wav"
        if cached.exists():
            data, _ = sf.read(str(cached), dtype="float32")
            job.put(data)
            job.finish()
        else:
            self._q.put((float(priority), next(self._seq), job))
        return job

    def wait_ready(self, timeout=None) -> bool:
        """모델이 준비될 때까지 기다림 (불러오기는 application/startup.py 가 차례에 맞춰 시작)."""
        return self.ready.wait(timeout)

    # --- GPU 스레드 -----------------------------------------------------------
    def _run(self):
        try:
            self._load()
        except Exception as e:  # noqa: BLE001
            self.load_error, self.status = e, f"오류: {e}"
            self.ready.set()
            return
        while True:
            _prio, _n, job = self._q.get()
            try:
                self._synthesize(job)
                if job.chunks:
                    path = config.TTS_CACHE_DIR / f"{job.key}.wav"
                    tmp = path.with_name(path.stem + ".tmp.wav")
                    sf.write(str(tmp), np.concatenate(job.chunks), SR)
                    tmp.replace(path)
                job.finish()
            except Exception as e:  # noqa: BLE001
                job.finish(e)

    def _synthesize(self, job: StreamJob):
        # 스트리밍 디코더는 매번 맨 앞 약 78ms 에 화자·문장과 무관한 똑같은 잡음을 냄 (빈 앞부분을 복원한 소리)
        # → 앞부분을 잘라내고 짧게 페이드인 (줄이 바뀔 때 '틱' 소리 제거)
        trim = int(SR * config.TRIM_START_MS / 1000)
        fade = int(SR * config.FADE_IN_MS / 1000)
        first = True
        for chunk, _sr in stream_custom_voice(self.model, job.text, job.speaker, job.language, job.instruct or None,
                                              emit_every_frames=config.EMIT_EVERY_FRAMES, decode_window_frames=80):
            chunk = np.asarray(chunk, dtype=np.float32)
            if trim:
                cut = min(trim, len(chunk))
                chunk, trim = chunk[cut:], trim - cut
            if first and len(chunk):
                chunk = chunk.copy()
                n = min(fade, len(chunk))
                chunk[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
                first = False
            if len(chunk):
                job.put(chunk)

    def _load(self):
        from qwen_tts import Qwen3TTSModel

        t0 = time.time()
        torch.set_float32_matmul_precision("high")
        for name in ("recompile_limit", "cache_size_limit"):
            if hasattr(torch._dynamo.config, name):
                setattr(torch._dynamo.config, name, 64)
        dev = config.DEVICE if torch.cuda.is_available() else "cpu"
        self.model = Qwen3TTSModel.from_pretrained(
            str(config.TTS_MODEL), device_map=dev,
            dtype=torch.bfloat16 if dev.startswith("cuda") else torch.float32,
            attn_implementation=config.TTS_ATTN,
        )
        if config.STREAM_OPTIMIZE and dev.startswith("cuda"):
            self.status = "최적화 컴파일 중 (약 2분, 처음 한 번)"
            self.model.enable_streaming_optimizations(decode_window_frames=80)
            for text, instruct in _WARMUP:
                for _ in stream_custom_voice(self.model, text, "Sohee", "Korean", instruct,
                                             emit_every_frames=config.EMIT_EVERY_FRAMES):
                    pass
        self.status = f"준비 완료 ({time.time() - t0:.0f}초)"
        self.ready.set()
