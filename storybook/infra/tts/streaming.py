"""CustomVoice 모델 스트리밍 래퍼.

커뮤니티 변형판(Qwen3-TTS-streaming, requirements.txt 참고)의 core `stream_generate_pcm()` 을
공식 `generate_custom_voice()` 와 같은 방식으로 입력을 만들어 호출합니다.
→ 화자(speaker) + 말투 지시(instruct) 를 유지한 채 PCM 조각을 순서대로 yield.
"""

from typing import Generator, Optional, Tuple

import numpy as np


def stream_custom_voice(
    model,
    text: str,
    speaker: str,
    language: str = "Auto",
    instruct: Optional[str] = None,
    emit_every_frames: int = 8,       # 8프레임 ≈ 0.67초 분량마다 조각 출력 (12Hz)
    decode_window_frames: int = 80,
    use_optimized_decode: bool = True,
    **gen_kwargs,
) -> Generator[Tuple[np.ndarray, int], None, None]:
    if model.model.tts_model_type != "custom_voice":
        raise ValueError("CustomVoice 모델에서만 사용할 수 있습니다.")
    model._validate_languages([language])
    model._validate_speakers([speaker])

    input_ids = model._tokenize_texts([model._build_assistant_text(text)])
    instruct_ids = [model._tokenize_texts([model._build_instruct_text(instruct)])[0] if instruct else None]
    kwargs = model._merge_generate_kwargs(**gen_kwargs)
    # stream_generate_pcm 이 받는 샘플링 인자만 전달
    allowed = {
        "do_sample", "top_k", "top_p", "temperature",
        "subtalker_dosample", "subtalker_top_k", "subtalker_top_p", "subtalker_temperature",
    }
    kwargs = {k: v for k, v in kwargs.items() if k in allowed}

    yield from model.model.stream_generate_pcm(
        input_ids=input_ids,
        instruct_ids=instruct_ids,
        languages=[language],
        speakers=[speaker],
        non_streaming_mode=False,
        emit_every_frames=emit_every_frames,
        decode_window_frames=decode_window_frames,
        use_optimized_decode=use_optimized_decode,
        **kwargs,
    )
