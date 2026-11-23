"""동화 낭독기 모델 다운로드 (STT: Whisper large-v3-turbo / 그림: SDXL + SDXL-Lightning 4step)."""
import os

import truststore

truststore.inject_into_ssl()  # 사내망 TLS 검사 인증서 → Windows 인증서 저장소 사용
from pathlib import Path

os.environ.pop("HF_HUB_OFFLINE", None)
from huggingface_hub import hf_hub_download, snapshot_download

M = Path(__file__).resolve().parent / "models"

snapshot_download("openai/whisper-large-v3-turbo", local_dir=M / "whisper-large-v3-turbo",
                  allow_patterns=["*.json", "*.txt", "model.safetensors"])
print("whisper ok", flush=True)
snapshot_download("stabilityai/stable-diffusion-xl-base-1.0", local_dir=M / "sdxl-base",
                  allow_patterns=["model_index.json", "scheduler/*", "tokenizer/*", "tokenizer_2/*", "unet/config.json",
                                  "text_encoder/config.json", "text_encoder/model.fp16.safetensors",
                                  "text_encoder_2/config.json", "text_encoder_2/model.fp16.safetensors"])
print("sdxl base ok", flush=True)
snapshot_download("madebyollin/sdxl-vae-fp16-fix", local_dir=M / "sdxl-vae-fp16-fix",
                  allow_patterns=["config.json", "diffusion_pytorch_model.safetensors"])
print("vae ok", flush=True)
hf_hub_download("ByteDance/SDXL-Lightning", "sdxl_lightning_4step_unet.safetensors", local_dir=M / "sdxl-lightning")
print("lightning ok", flush=True)
print("ALL DONE")

# 주인공 모습 일관성: IP-Adapter Plus (SDXL, ViT-H 이미지 인코더) — 표지 그림을 참고해 모든 삽화의 인물을 같게
snapshot_download("h94/IP-Adapter", local_dir=M / "ip-adapter",
                  allow_patterns=["sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors",
                                  "models/image_encoder/config.json", "models/image_encoder/model.safetensors"])
print("ip-adapter ok", flush=True)
