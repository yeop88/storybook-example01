"""그림 어댑터: SDXL + SDXL-Lightning 4단계 (+ IP-Adapter Plus 로 주인공 모습 유지).

- UNet·VAE(·IP-Adapter)는 GPU 상주 (한 장 약 1초), 글/그림 이해 모델(텍스트·이미지 인코더)은 CPU (한 장에 약 0.3초)
- GPU 여유가 PAINT_MIN_FREE_GB 보다 적으면 전체를 CPU 오프로드(필요할 때만 GPU 로, 한 장 약 4초)로 물러남
"""

import threading

import torch

from storybook import config
from storybook.infra.runtime import GPU_LOCK, shared


class _Painter:
    def __init__(self):
        self.lock = threading.Lock()
        self.pipe = None
        self.status = "대기"
        self.ref = False        # IP-Adapter 를 쓸 수 있는지
        self.split = False      # 인코더 CPU / UNet GPU 로 나눠 올렸는지
        self.text_encoders = None
        self.ref_cache: dict = {}

    # --- 불러오기 -------------------------------------------------------------
    def load(self):
        with self.lock:
            if self.pipe is None:
                self._load()
        return self.pipe

    def _load(self):
        from diffusers import AutoencoderKL, EulerDiscreteScheduler, StableDiffusionXLPipeline, UNet2DConditionModel
        from safetensors.torch import load_file

        self.status = "불러오는 중"
        base = str(config.SDXL_BASE)
        unet = UNet2DConditionModel.from_config(UNet2DConditionModel.load_config(base, subfolder="unet"))
        unet.load_state_dict(load_file(str(config.SDXL_UNET)))
        unet.to(torch.float16)
        vae = AutoencoderKL.from_pretrained(str(config.SDXL_VAE), torch_dtype=torch.float16)
        pipe = StableDiffusionXLPipeline.from_pretrained(base, unet=unet, vae=vae, torch_dtype=torch.float16,
                                                         variant="fp16")
        # Lightning 은 trailing 타임스텝 + 4단계 + guidance 0 으로 학습됨
        pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
        pipe.set_progress_bar_config(disable=True)
        pipe.enable_vae_tiling()  # 그림 마무리(VAE 디코딩) 때 메모리 순간 사용량을 줄임
        if config.CHARACTER_REF and config.IP_ADAPTER.exists() and config.IP_ENCODER.exists():
            pipe.load_ip_adapter(str(config.IP_ADAPTER_DIR), subfolder="sdxl_models", weight_name=config.IP_ADAPTER.name,
                                 image_encoder_folder="models/image_encoder", torch_dtype=torch.float16)
            self.ref = True
        mode = self._place(pipe)
        self.pipe = pipe
        self.status = f"준비 완료 ({mode}{', 주인공 모습 유지' if self.ref else ''})"

    def _place(self, pipe) -> str:
        gpu = int(config.DEVICE.split(":")[-1]) if ":" in config.DEVICE else 0
        if config.PAINT_ON_GPU and torch.cuda.is_available():
            try:
                for m in (pipe.text_encoder, pipe.text_encoder_2, getattr(pipe, "image_encoder", None)):
                    if m is not None:
                        m.to("cpu", torch.float32)  # CPU 에서는 fp32 가 빠름
                pipe.unet.to(config.DEVICE)
                pipe.vae.to(config.DEVICE)
                free, _ = torch.cuda.mem_get_info(gpu)
                if free >= config.PAINT_MIN_FREE_GB * 1e9:
                    self.split = True
                    # 글 이해 모델은 파이프라인에서 떼어 보관 (붙어 있으면 diffusers 가 결과를 fp32 로 바꿔 UNet(fp16)과 안 맞음)
                    self.text_encoders = (pipe.text_encoder, pipe.text_encoder_2)
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

    # --- 그리기 ---------------------------------------------------------------
    def _ref_embeds(self, ref):
        """참고 그림 → IP-Adapter 이미지 임베딩 (책마다 한 번만 계산해 캐시)."""
        key = id(ref) if ref is not None else "blank"
        if key not in self.ref_cache:
            from PIL import Image
            img = ref if ref is not None else Image.new("RGB", (224, 224), (128, 128, 128))
            dev = "cpu" if self.split else config.DEVICE
            emb = self.pipe.prepare_ip_adapter_image_embeds(ip_adapter_image=[img], ip_adapter_image_embeds=None,
                                                            device=dev, num_images_per_prompt=1,
                                                            do_classifier_free_guidance=False)
            if len(self.ref_cache) > 8:
                self.ref_cache.clear()
            self.ref_cache[key] = emb
        return self.ref_cache[key]

    def paint(self, prompt: str, seed: int, size, ref, ref_scale):
        pipe = self.load()
        dev, dt = config.DEVICE, torch.float16
        with GPU_LOCK, torch.inference_mode():
            g = torch.Generator("cpu").manual_seed(seed)
            kw = {}
            if self.ref:
                pipe.set_ip_adapter_scale(0.0 if ref is None else (config.REF_SCALE if ref_scale is None else ref_scale))
                emb = self._ref_embeds(ref)
                kw["ip_adapter_image_embeds"] = [e.to(dev, dt) for e in emb] if self.split else emb
            if self.split:  # 글 이해는 CPU 에서 → 결과만 GPU 로
                pipe.text_encoder, pipe.text_encoder_2 = self.text_encoders
                try:
                    pe, _, pooled, _ = pipe.encode_prompt(prompt=prompt, device="cpu", num_images_per_prompt=1,
                                                          do_classifier_free_guidance=False)
                finally:
                    pipe.text_encoder = pipe.text_encoder_2 = None
                kw.update(prompt_embeds=pe.to(dev, dt), pooled_prompt_embeds=pooled.to(dev, dt))
            else:
                kw["prompt"] = prompt
            img = pipe(num_inference_steps=4, guidance_scale=0.0, width=size[0], height=size[1], generator=g,
                       **kw).images[0]
            torch.cuda.empty_cache()  # 그리는 동안 잡은 임시 메모리 반납
        return img


def _painter() -> _Painter:
    return shared("painter", _Painter)


def load():
    _painter().load()


def status() -> str:
    return _painter().status


def paint(prompt: str, seed: int = 0, size=config.IMAGE_SIZE, ref=None, ref_scale: float | None = None):
    """프롬프트(영어) → PIL 이미지. ref(PIL)를 주면 그 그림 속 인물 모습을 따라 그림."""
    return _painter().paint(prompt, seed, size, ref, ref_scale)
