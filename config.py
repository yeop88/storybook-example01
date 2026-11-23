"""공통 설정 (.env 로드)."""

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")  # 모델 라이브러리 임포트 전에 로드 (HF_HUB_OFFLINE 등)


def env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _path(p: str) -> Path:
    return (APP_DIR / p).resolve() if p.startswith(".") else Path(p)


# --- 폴더 -----------------------------------------------------------------
DATA_DIR = APP_DIR / "data"
CERT_DIR = APP_DIR / "certs"
# Streamlit 정적 파일 폴더: 만든 책(그림, 음성, book.json)을 /app/static/books/<id>/ 로 브라우저에 제공
STATIC_DIR = APP_DIR / "static"
BOOKS_DIR = STATIC_DIR / "books"
for _d in (DATA_DIR, BOOKS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

SERVER_IPS = [ip.strip() for ip in env("SERVER_IPS", "").split(",") if ip.strip()]

# --- TTS (tts_app_streaming 의 내부 API) ------------------------------------
TTS_API_URL = env("TTS_API_URL", "http://127.0.0.1:8601").rstrip("/")
SR = 24000

# --- STT / 그림 -------------------------------------------------------------
DEVICE = env("DEVICE", "cuda:0")
WHISPER_PATH = _path(env("WHISPER_PATH", "./models/whisper-large-v3-turbo"))
SDXL_BASE = _path(env("SDXL_BASE", "./models/sdxl-base"))
SDXL_VAE = _path(env("SDXL_VAE", "./models/sdxl-vae-fp16-fix"))
SDXL_UNET = _path(env("SDXL_UNET", "./models/sdxl-lightning/sdxl_lightning_4step_unet.safetensors"))
IMAGE_SIZE = (1024, 768)  # (가로, 세로) 4:3 — 빨리 그리면서도 SDXL 품질 유지
# 그림 모델을 GPU 에 상주 (1 = 상주, 0 = CPU 오프로드). 올린 뒤 GPU 여유가 이보다 적으면 자동으로 오프로드
PAINT_ON_GPU = env("PAINT_ON_GPU", "1") == "1"
PAINT_MIN_FREE_GB = float(env("PAINT_MIN_FREE_GB", "1.5"))
# 주인공 모습 일관성: 표지 그림을 참고해 모든 삽화의 인물을 같은 모습으로 (IP-Adapter Plus). 0 이면 끔
CHARACTER_REF = env("CHARACTER_REF", "1") == "1"
REF_SCALE = float(env("REF_SCALE", "0.2"))  # 참고 그림을 따르는 정도 (높을수록 비슷, 낮을수록 장면 설명을 잘 따름)
IP_ADAPTER_DIR = _path(env("IP_ADAPTER_DIR", "./models/ip-adapter"))
IP_ADAPTER = IP_ADAPTER_DIR / "sdxl_models" / "ip-adapter-plus_sdxl_vit-h.safetensors"
IP_ENCODER = IP_ADAPTER_DIR / "models" / "image_encoder" / "model.safetensors"

# --- 동화 옵션 --------------------------------------------------------------
AGES = {
    "3~5세": "3~5세 유아. 아주 쉬운 낱말, 짧은 문장, 반복되는 말과 의성어·의태어를 많이 사용",
    "6~8세": "6~8세 어린이. 쉬운 낱말과 짧은 문장, 재미있는 사건과 따뜻한 결말",
    "9~12세": "9~12세 어린이. 조금 더 풍부한 표현과 모험, 갈등과 해결이 있는 이야기",
}
CHAPTER_COUNTS = [1, 2, 3, 4, 5]      # 장(챕터) 수
PAGES_PER_CHAPTER = [2, 3, 4, 5, 6]  # 장마다 쪽수 (전체 쪽수 = 장 수 × 장마다 쪽수, 정확히 지킴)
# 해설자: 이름 → (TTS 화자, 음색 지시)
NARRATORS = {
    "여자 · 다정한": ("Sohee", ""),
    "젊은 여자 · 부드러운": ("Serena", "젊은 여성의 부드럽고 맑은 목소리로"),
    "남자 · 차분한": ("Ryan", "차분하고 따뜻한 어른 남성의 낮은 목소리로"),
    "젊은 남자 · 밝은": ("Aiden", "밝고 친근한 젊은 남성의 목소리로"),
    "할머니": ("Serena", "인자한 할머니처럼 느리고 다정하게, 손주에게 옛날이야기를 들려주듯"),
    "할아버지": ("Uncle_Fu", "인자한 할아버지처럼 낮고 느긋하게, 손주에게 옛날이야기를 들려주듯"),
}
STYLES = {
    "수채화": "soft watercolor children's book illustration, gentle pastel colors, paper texture",
    "크레파스": "crayon drawing children's book illustration, colorful, playful hand-drawn strokes",
    "3D 애니메이션": "3d animated movie style, cute characters, soft cinematic lighting, vibrant colors",
    "따뜻한 동화책": "classic storybook illustration, warm colors, detailed, cozy and whimsical",
    "종이 오리기": "paper cut-out collage illustration, layered paper craft, bright colors",
    "동양 수묵화": "korean traditional ink wash painting with soft colors, minimalist, elegant",
}
VOICES = {
    "다정한 엄마": "따뜻하고 다정한 목소리로, 아이에게 동화를 읽어 주듯 천천히 또박또박 읽어 주세요.",
    "동화 구연가": "생동감 있고 표정이 풍부한 동화 구연가처럼, 장면의 분위기에 맞게 감정을 살려 읽어 주세요.",
    "잠자리 동화": "아주 부드럽고 조용하게, 잠들기 전 속삭이듯 느리고 편안하게 읽어 주세요.",
    "신나는 모험": "밝고 신나는 목소리로, 모험 이야기처럼 활기차고 경쾌하게 읽어 주세요.",
    "기본": "",
}
SPEAKERS = {
    "Sohee": "따뜻한 여성",
    "Serena": "부드러운 여성",
    "Vivian": "밝은 여성",
    "Aiden": "밝은 남성",
    "Ryan": "힘찬 남성",
    "Uncle_Fu": "낮은 중년 남성",
}
LANGUAGES = {"Korean": "한국어", "English": "영어"}

# 등장인물 목소리 유형 → (TTS 화자, 기본 음색 지시). LLM 이 인물마다 유형을 고르고, 줄마다 감정 지시를 덧붙임.
VOICE_TYPES = {
    "girl":        ("Sohee",    "어린 여자아이처럼 맑고 높은 목소리로"),
    "boy":         ("Aiden",    "어린 남자아이처럼 씩씩하고 높은 목소리로"),
    "young_woman": ("Serena",   "젊은 여성의 부드럽고 상냥한 목소리로"),
    "young_man":   ("Ryan",     "젊은 남성의 활기찬 목소리로"),
    "woman":       ("Vivian",   "어른 여성의 따뜻하고 차분한 목소리로"),
    "man":         ("Ryan",     "어른 남성의 듬직하고 낮은 목소리로"),
    "grandma":     ("Serena",   "인자한 할머니처럼 느리고 다정한 목소리로"),
    "grandpa":     ("Uncle_Fu", "인자한 할아버지처럼 느리고 낮은 목소리로"),
    "creature":    ("Ono_Anna", "귀여운 동물 친구처럼 통통 튀는 목소리로"),
}
# 인물 목소리: "different" = 인물마다 다른 화자, "same" = 해설자 화자 하나로 음색 지시만 바꿈
CHARACTER_VOICE_MODES = {"different": "인물마다 다른 목소리", "same": "해설자 한 명이 연기 (말투·감정만 바꿈)"}
LINE_PAUSE = 0.35  # 줄 사이 쉼(초)

# 해설자와 겹쳐 다른 목소리를 고를 때의 후보 (같은 성별·나이대 안에서, 앞쪽이 우선)
VOICE_ALTS = {
    "girl":        ["Sohee", "Ono_Anna", "Vivian", "Serena"],
    "boy":         ["Aiden", "Ryan", "Eric", "Dylan"],
    "young_woman": ["Serena", "Vivian", "Sohee", "Ono_Anna"],
    "young_man":   ["Ryan", "Aiden", "Eric", "Dylan"],
    "woman":       ["Vivian", "Serena", "Sohee"],
    "man":         ["Ryan", "Dylan", "Uncle_Fu", "Eric"],
    "grandma":     ["Serena", "Vivian", "Sohee"],
    "grandpa":     ["Uncle_Fu", "Dylan", "Ryan"],
    "creature":    ["Ono_Anna", "Eric", "Vivian", "Aiden"],
}

# 누르자마자 읽는 인사말 (서버 시작 시 미리 만들어 둠 → 캐시에서 바로 재생, 그동안 LLM 이 제목을 씀)
GREETINGS = [
    "자, 오늘은 어떤 이야기가 펼쳐질까요? 귀를 쫑긋 세우고 들어 보세요.",
    "안녕, 친구들! 지금부터 아주 특별한 동화를 들려줄게요.",
    "오늘 밤 함께 읽을 이야기를 지금 막 만들고 있어요. 잠깐만 기다려 줄래요?",
]
GREETING_EMOTION = "설레고 다정하게, 아이에게 말을 건네듯 천천히"

# --- 운영 ---------------------------------------------------------------------
MAX_BOOKS_AT_ONCE = int(env("MAX_BOOKS_AT_ONCE", "2"))  # 동시에 만드는 책 수 (넘으면 대기열)
BOOK_KEEP_DAYS = int(env("BOOK_KEEP_DAYS", "0"))        # 이 날수보다 오래된 책 자동 삭제 (0 = 지우지 않음)

# --- LLM (내부 네트워크 OpenAI 호환 서버만 사용, think 끔) ---------------------
LLM_PROVIDERS = {
    name: {
        "base_url": env(f"{name}_BASE_URL"),
        "api_key": env(f"{name}_API_KEY", "EMPTY"),
        "model": env(f"{name}_MODEL"),  # 비우면 서버 /models 의 첫 모델
    }
    for name in ("STRATA", "FREETOKEN")
    if env(f"{name}_BASE_URL")
}
LLM_DEFAULT = env("LLM_DEFAULT", next(iter(LLM_PROVIDERS), ""))
