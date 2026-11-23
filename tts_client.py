"""tts_app_streaming 이 띄운 내부 TTS API 클라이언트 (TTS 모델을 두 번 올리지 않음).

stream() 은 생성되는 PCM 조각을 바로바로 돌려줌 (첫 조각 약 0.3초).
"""

from collections.abc import Iterator

import numpy as np
import requests

import config

_session = requests.Session()
_session.trust_env = False  # 사내 프록시를 거치지 않고 127.0.0.1 로 바로 접속


def health() -> dict:
    try:
        return _session.get(f"{config.TTS_API_URL}/health", timeout=3).json()
    except requests.RequestException as e:
        return {"ready": False, "status": f"연결 안 됨 ({type(e).__name__}) — tts_app_streaming 이 실행 중인지 확인하세요"}


def stream(text: str, speaker: str = "Sohee", language: str = "Korean", instruct: str = "") -> Iterator[np.ndarray]:
    """텍스트 → float32 24kHz mono 조각을 생성되는 대로."""
    r = _session.post(f"{config.TTS_API_URL}/tts", timeout=(5, 600), stream=True,
                      json={"text": text, "speaker": speaker, "language": language, "instruct": instruct})
    if r.status_code != 200:
        raise RuntimeError(f"TTS API 오류 {r.status_code}: {r.text[:200]}")
    rest = b""
    for data in r.iter_content(chunk_size=None):
        data = rest + data
        cut = len(data) - len(data) % 2
        rest = data[cut:]
        if cut:
            yield np.frombuffer(data[:cut], dtype="<i2").astype(np.float32) / 32768


def synthesize(text: str, speaker: str = "Sohee", language: str = "Korean", instruct: str = "") -> np.ndarray:
    parts = list(stream(text, speaker, language, instruct))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
