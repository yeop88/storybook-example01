"""동화 낭독기에 필요한 모델을 models/ 에 받음 (약 16GB, 처음 한 번).

  TTS  : Qwen3-TTS-12Hz-1.7B-CustomVoice (스트리밍 낭독)
  STT  : Whisper large-v3-turbo (말로 주제·선택 받아쓰기)
  그림 : SDXL base + SDXL-Lightning 4단계 UNet + fp16 VAE + IP-Adapter Plus (주인공 모습 유지)

사용: .venv\\Scripts\\python.exe scripts\\download_models.py   (이미 받은 파일은 건너뜀)
"""

import os
from pathlib import Path

import truststore

truststore.inject_into_ssl()  # 사내망 TLS 검사 인증서 → Windows 인증서 저장소 사용
os.environ.pop("HF_HUB_OFFLINE", None)

from huggingface_hub import hf_hub_download, snapshot_download  # noqa: E402

M = Path(__file__).resolve().parents[1] / "models"

snapshot_download("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", local_dir=M / "Qwen3-TTS-12Hz-1.7B-CustomVoice")
print("tts ok", flush=True)
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
snapshot_download("h94/IP-Adapter", local_dir=M / "ip-adapter",
                  allow_patterns=["sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors",
                                  "models/image_encoder/config.json", "models/image_encoder/model.safetensors"])
print("ip-adapter ok", flush=True)
print("ALL DONE")
