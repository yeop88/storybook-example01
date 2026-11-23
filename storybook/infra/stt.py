"""받아쓰기(STT) 어댑터: Whisper large-v3-turbo.

평소엔 RAM 에 두고 받아쓸 때만 GPU 로 옮김 (주제·선택을 말할 때만 쓰므로, GPU 메모리는 TTS·그림 모델에 양보).
"""

import io
import threading

import soundfile as sf
import torch

from storybook import config
from storybook.infra.runtime import GPU_LOCK, shared


class _STT:
    def __init__(self):
        self.lock = threading.Lock()
        self.model = None
        self.processor = None
        self.status = "대기"

    def load(self):
        with self.lock:
            if self.model is None:
                from transformers import WhisperForConditionalGeneration, WhisperProcessor

                self.status = "불러오는 중"
                self.processor = WhisperProcessor.from_pretrained(str(config.WHISPER_PATH))
                self.model = WhisperForConditionalGeneration.from_pretrained(str(config.WHISPER_PATH),
                                                                             dtype=torch.float16).eval()
                self.status = "준비 완료"
        return self.processor, self.model


def _stt() -> _STT:
    return shared("stt", _STT)


def load():
    _stt().load()


def status() -> str:
    return _stt().status


def transcribe(audio_bytes: bytes, language: str = "korean") -> str:
    """녹음(WAV 등) → 텍스트."""
    data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        import librosa
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
    if len(data) < 1600:  # 0.1초 미만
        return ""
    proc, model = _stt().load()
    dev = config.DEVICE if torch.cuda.is_available() else "cpu"
    long = len(data) > 30 * 16000
    feats = proc(data, sampling_rate=16000, return_tensors="pt", return_attention_mask=True,
                 **({"truncation": False, "padding": "longest"} if long else {}))
    with GPU_LOCK, torch.inference_mode():
        model.to(dev)
        try:
            ids = model.generate(feats.input_features.to(dev, torch.float16),
                                 attention_mask=feats.attention_mask.to(dev),
                                 language=language, task="transcribe")
        finally:
            model.to("cpu")
            torch.cuda.empty_cache()
    return proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
