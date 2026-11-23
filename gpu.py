"""STT(Whisper)·그림(SDXL-Lightning) 모델 관리.

- 프로세스당 1번만 불러와 서버가 꺼질 때까지 유지 (sys 에 보관 → 모듈이 다시 import 돼도 재사용)
- 두 모델이 같은 GPU 를 쓰므로 GPU_LOCK 으로 한 번에 하나씩 실행
- 그림 모델은 GPU 상주 (한 장 약 1초). GPU 여유가 부족하면 자동으로 CPU 오프로드
- 받아쓰기 모델은 RAM 에 두고 받아쓸 때만 GPU 로 옮김 (이야기 시작 전 한 번만 쓰므로)
  (TTS 는 tts_app_streaming 프로세스에 상주)
"""

import io
import sys
import threading

import numpy as np
import soundfile as sf
import torch

import config


def _shared():
    if not hasattr(sys, "_story_gpu"):
        sys._story_gpu = {"lock": threading.Lock(), "init_stt": threading.Lock(), "init_paint": threading.Lock(), "stt": None, "paint": None,
                          "status": {"stt": "대기", "paint": "대기"}}
    return sys._story_gpu


S = _shared()
GPU_LOCK: threading.Lock = S["lock"]


def status() -> dict:
    return S["status"]


# ---------------------------------------------------------------------------
# STT: Whisper large-v3-turbo — 평소엔 RAM 에 두고, 받아쓸 때만 GPU 로 (GPU 메모리는 그림 모델에 양보)
# ---------------------------------------------------------------------------
def _stt():
    with S["init_stt"]:
        if S["stt"] is None:
            from transformers import WhisperForConditionalGeneration, WhisperProcessor

            S["status"]["stt"] = "불러오는 중"
            proc = WhisperProcessor.from_pretrained(str(config.WHISPER_PATH))
            model = WhisperForConditionalGeneration.from_pretrained(str(config.WHISPER_PATH), dtype=torch.float16)
            model.eval()
            S["stt"] = (proc, model)
            S["status"]["stt"] = "준비 완료"
    return S["stt"]


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
    proc, model = _stt()
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


# ---------------------------------------------------------------------------
# 그림: SDXL + SDXL-Lightning 4step UNet
# ---------------------------------------------------------------------------
def _painter():
    with S["init_paint"]:
        if S["paint"] is None:
            from diffusers import AutoencoderKL, EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel
            from safetensors.torch import load_file

            S["status"]["paint"] = "불러오는 중"
            base = str(config.SDXL_BASE)
            unet = UNet2DConditionModel.from_config(UNet2DConditionModel.load_config(base, subfolder="unet"))
            unet.load_state_dict(load_file(str(config.SDXL_UNET)))
            unet.to(torch.float16)
            vae = AutoencoderKL.from_pretrained(str(config.SDXL_VAE), torch_dtype=torch.float16)
            pipe = StableDiffusionXLPipeline.from_pretrained(
                base, unet=unet, vae=vae, torch_dtype=torch.float16, variant="fp16",
            )
            # Lightning 은 trailing 타임스텝 + 4단계 + guidance 0 으로 학습됨
            pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
            pipe.set_progress_bar_config(disable=True)
            pipe.enable_vae_tiling()  # 그림 마무리(VAE 디코딩) 때 메모리 순간 사용량을 줄임
            S["ref"] = False
            if config.CHARACTER_REF and config.IP_ADAPTER.exists() and config.IP_ENCODER.exists():
                # 주인공 모습 일관성: 표지 그림을 참고 이미지로 (IP-Adapter Plus, ViT-H)
                pipe.load_ip_adapter(str(config.IP_ADAPTER_DIR), subfolder="sdxl_models",
                                     weight_name=config.IP_ADAPTER.name, image_encoder_folder="models/image_encoder",
                                     torch_dtype=torch.float16)
                S["ref"] = True
            mode = _place(pipe)
            S["paint"] = pipe
            S["status"]["paint"] = f"준비 완료 ({mode}{', 주인공 모습 유지' if S['ref'] else ''})"
    return S["paint"]


def _place(pipe) -> str:
    """UNet·VAE(·IP-Adapter)는 GPU 상주(빠름), 글/그림 이해 모델(텍스트·이미지 인코더)은 CPU(한 장에 약 0.3초).
    GPU 여유가 부족하면 전체를 CPU 오프로드(필요할 때만 GPU 로)로 물러남."""
    gpu = int(config.DEVICE.split(":")[-1]) if ":" in config.DEVICE else 0
    S["split"] = False
    if config.PAINT_ON_GPU and torch.cuda.is_available():
        try:
            for m in (pipe.text_encoder, pipe.text_encoder_2, getattr(pipe, "image_encoder", None)):
                if m is not None:
                    m.to("cpu", torch.float32)  # CPU 에서는 fp32 가 빠름
            pipe.unet.to(config.DEVICE)
            pipe.vae.to(config.DEVICE)
            free, _ = torch.cuda.mem_get_info(gpu)
            if free >= config.PAINT_MIN_FREE_GB * 1e9:
                S["split"] = True
                # 글 이해 모델은 파이프라인에서 떼어 보관 (붙어 있으면 diffusers 가 결과를 fp32 로 바꿔 UNet(fp16)과 안 맞음)
                S["te"] = (pipe.text_encoder, pipe.text_encoder_2)
                pipe.text_encoder = pipe.text_encoder_2 = None
                # 인코더가 CPU 에 있으면 diffusers 가 실행 장치를 CPU 로 잘못 판단 → GPU 로 고정
                dev = torch.device(config.DEVICE)
                pipe.__class__ = type("SplitSDXLPipeline", (pipe.__class__,),
                                      {"_execution_device": property(lambda self: dev)})
                return "GPU 상주"
            print(f"[paint] GPU 여유 {free / 1e9:.1f}GB 부족 → CPU 오프로드로 전환", flush=True)
        except torch.OutOfMemoryError:
            print("[paint] GPU 메모리 부족 → CPU 오프로드로 전환", flush=True)
        pipe.to("cpu", torch.float16)
        torch.cuda.empty_cache()
    pipe.enable_model_cpu_offload(gpu_id=gpu)
    return "CPU 오프로드"


def _ref_embeds(pipe, ref):
    """참고 그림 → IP-Adapter 이미지 임베딩 (CPU, 책마다 한 번만 계산해 캐시)."""
    cache = S.setdefault("ref_cache", {})
    key = id(ref) if ref is not None else "blank"
    if key not in cache:
        from PIL import Image
        img = ref if ref is not None else Image.new("RGB", (224, 224), (128, 128, 128))
        dev = "cpu" if S.get("split") else config.DEVICE
        with torch.inference_mode():
            emb = pipe.prepare_ip_adapter_image_embeds(ip_adapter_image=[img], ip_adapter_image_embeds=None, device=dev,
                                                       num_images_per_prompt=1, do_classifier_free_guidance=False)
        if len(cache) > 8:
            cache.clear()
        cache[key] = emb
    return cache[key]


def paint(prompt: str, seed: int = 0, size=config.IMAGE_SIZE, ref=None, ref_scale: float | None = None):
    """프롬프트(영어) → PIL 이미지. ref(PIL)를 주면 그 그림 속 인물 모습을 따라 그림 (IP-Adapter)."""
    pipe = _painter()
    dev, dt = config.DEVICE, torch.float16
    with GPU_LOCK, torch.inference_mode():
        g = torch.Generator("cpu").manual_seed(seed)
        kw = {}
        if S.get("ref"):
            pipe.set_ip_adapter_scale(0.0 if ref is None else (config.REF_SCALE if ref_scale is None else ref_scale))
            emb = _ref_embeds(pipe, ref)
            kw["ip_adapter_image_embeds"] = [e.to(dev, dt) for e in emb] if S.get("split") else emb
        if S.get("split"):  # 글 이해는 CPU 에서 → 결과만 GPU 로
            pipe.text_encoder, pipe.text_encoder_2 = S["te"]
            try:
                pe, _, pooled, _ = pipe.encode_prompt(prompt=prompt, device="cpu", num_images_per_prompt=1,
                                                      do_classifier_free_guidance=False)
            finally:
                pipe.text_encoder = pipe.text_encoder_2 = None
            kw.update(prompt_embeds=pe.to(dev, dt), pooled_prompt_embeds=pooled.to(dev, dt))
        else:
            kw["prompt"] = prompt
        img = pipe(num_inference_steps=4, guidance_scale=0.0, width=size[0], height=size[1], generator=g, **kw).images[0]
        torch.cuda.empty_cache()  # 그리는 동안 잡은 임시 메모리 반납 (TTS 등 다른 프로세스 몫)
    return img


def preload():
    """서버 시작 시 두 모델을 백그라운드로 미리 불러옴."""
    if S.get("preloading"):
        return
    S["preloading"] = True

    def run():
        for name, fn in (("stt", _stt), ("paint", _painter)):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                S["status"][name] = f"오류: {e}"
        try:  # 첫 그림은 느리므로 실제 크기로 한 장 미리 그려 둠
            paint("a cute rabbit in a meadow, watercolor")
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=run, daemon=True, name="story-preload").start()


def to_wav_bytes(x: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV")
    return buf.getvalue()
