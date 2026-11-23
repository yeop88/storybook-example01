# 📖 AI 동화 낭독기

말로 주제를 들려주면 AI가 그림 동화를 쓰고, 그림을 그리고, 등장인물마다 다른 목소리와 감정으로 **실시간으로** 읽어 주는 내부망 웹 서비스입니다.
외부 유료 API 없이 이 PC의 GPU(TTS·받아쓰기·그림 모델을 이 앱이 직접 올림)와 사내 LLM 서버만 사용합니다. 다른 프로젝트에 기대지 않는 독립 앱입니다.

```
🎤 말로 주제 ──STT(Whisper)──▶ 주제 글
                                   │
                ┌──────────────────┘
                ▼
     ✍️ 사내 LLM (스트리밍, think 끔) ── 한 줄씩 ──┬──▶ 🔊 TTS 스트리밍 (줄마다 화자·말투·감정 지시)
        제목 / 등장인물 / 페이지 / 대사·해설        │        → 음성 조각을 바로 브라우저로
                                                  └──▶ 🎨 SDXL-Lightning (장면이 바뀌는 곳마다 삽화)
                                                              → 완성되는 대로 화면에
```

접속: **https://<서버-IP>:8502** (마이크 때문에 HTTPS)

---

## 사용법

### 1. 설치 (처음 한 번)

준비물: Windows, NVIDIA GPU(16GB 권장, CUDA 12.8), [uv](https://docs.astral.sh/uv/), 사내 LLM 서버 주소·키

```bat
cd story_app

:: 1) 가상환경 + 패키지 (torch CUDA 12.8, Qwen3-TTS 스트리밍 변형판 등)
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt --index-strategy unsafe-best-match
::    사내망 인증서 오류(UnknownIssuer)가 나면 두 명령에 --system-certs 를 붙이세요

:: 2) 모델 받기 (약 16GB → models\)
.venv\Scripts\python.exe scripts\download_models.py

:: 3) 설정: .env.example 을 .env 로 복사한 뒤 LLM 서버 주소·키, 이 PC 의 내부 IP(SERVER_IPS) 를 채움
copy .env.example .env
```

방화벽 (관리자 cmd, 한 번): `netsh advfirewall firewall add rule name="AI Story 8502" dir=in action=allow protocol=TCP localport=8502`

### 2. 서버 켜기

```bat
run.bat
```
- 처음 실행하면 HTTPS 인증서를 자동으로 만들고(`certs\`), 모델을 GPU 에 올립니다.
  준비까지 첫 실행 약 3분(TTS 최적화 컴파일), 이후 약 1분. 사이드바 **준비 상태**가 모두 ✅ 이면 시작할 수 있어요.
- 서버를 끌 때까지 모델은 GPU 에 그대로 있습니다. 끄려면 창에서 `Ctrl+C`.

### 3. 접속하는 PC: 인증서 설치 (PC 마다 한 번)

브라우저는 `http://IP주소` 에서 마이크를 막아서 HTTPS 로 엽니다. 내부 IP 는 공개 무료 인증서(Let's Encrypt 등)를 받을 수 없어서
**사내용 무료 인증기관(CA)** 으로 발급합니다 (mkcert 와 같은 원리).

1. `https://<서버-IP>:8502` 접속 → 처음 한 번만 "연결이 비공개로 설정되어 있지 않습니다" → **고급 → 계속**
2. 왼쪽 사이드바 **🔒 보안 연결(인증서) 설치 → 🪟 Windows 설치 파일** 내려받아 실행 → 보안 경고에서 **예** (관리자 권한 불필요)
3. 브라우저를 **모두 닫고** 다시 접속 → 주소창에 🔒
- Mac·휴대폰은 "📱 인증서 파일" 을 받아 설치 (Android: 설정 → 보안 → 인증서 설치 → CA 인증서 / iPhone: 프로필 설치 → 일반 → 정보 → 인증서 신뢰 설정)
- 여러 PC 에 한 번에: 관리자가 `certs\ca.crt` 를 그룹 정책(GPO)의 "신뢰할 수 있는 루트 인증 기관" 에 등록
- 이 CA 는 사설 IP·localhost 에만 발급하도록 이름 제약이 걸려 있어 키가 새어도 외부 사이트를 위장할 수 없습니다. 그래도 `certs\ca.key` 는 공유하지 마세요.

### 4. 동화 만들기 (✨ 동화 만들기 화면)

1. **주제 말하기**: 🎤 버튼을 누르고 말한 뒤 ⏹ — 녹음 파형과 "📝 녹음된 말" 이 보이고 주제 칸에 들어가요. 직접 입력하거나 💡 예시 주제를 골라도 돼요.
2. **꾸미기**: 주인공 이름·교훈(선택), 듣는 아이 나이, 언어(한국어/영어)
3. **구성**: 장(챕터) 수 1~5 × 장마다 쪽수 2~6 (쪽수는 정확히 지켜요). 장별 제목·줄거리를 직접 정할 수 있어요.
   - **🔀 선택형 동화**(장 2개 이상): 장이 끝날 때마다 해설자가 질문하고, 아이가 ①② 버튼이나 🎤 말로 고르면 그 선택대로 다음 장이 이어져요.
4. **그림과 목소리**: 그림체 6가지, 해설 목소리 6가지(여자·젊은 여자·남자·젊은 남자·할머니·할아버지), 해설 느낌, 등장인물 대사 방식
5. **✨ 동화 만들기** → 오른쪽 재생기에서 바로 읽기 시작해요 (첫 소리 약 0.2~0.5초).
   - 지금 읽는 줄이 강조되고, 읽은 글자는 진하게 표시돼요(글자 따라 읽기). 줄 위에 마우스를 올리면 AI 가 정한 말투가 보여요.
   - ⏸ 멈춤 / ◀ 이전 / 다음 ▶ / ↺ 처음부터, 장 버튼으로 장 이동
   - 소리가 안 나면 재생기의 "▶ 눌러서 소리 켜기" 를 누르세요 (브라우저 자동 재생 차단).

### 5. 책장 · 통계

- **📚 책장**: 만든 책을 다시 읽기(📖) / 삭제(🗑️). 책 수와 사용 용량 표시.
- **📊 통계**(관리자용): 지금 만드는 책·대기, 완료율, 첫 소리, 삽화 시간, 동화 길이, AI 서버 전환·외국 글자 수정 횟수, 책별 기록.

### 6. 개발 · 확인

```bat
:: 순수 규칙(domain) 단위 시험 — 모델 없이 바로 돎
.venv\Scripts\python.exe -m unittest discover -s tests -v

:: 서버 IP 가 바뀌었을 때 인증서 다시 발급 (CA 는 유지 → 각 PC 재설치 불필요)
.venv\Scripts\python.exe scripts\make_cert.py
:: CA 부터 새로 (각 PC 에 다시 설치해야 함)
.venv\Scripts\python.exe scripts\make_cert.py --new-ca
```
코드를 고치면 서버를 다시 켜야 반영됩니다 (`fileWatcherType = "none"`, 모델을 두 번 올리지 않기 위해).

---

## 기능

| 기능 | 설명 |
|---|---|
| 🎤 말로 주제 말하기 | 브라우저 마이크 녹음 → Whisper large-v3-turbo 받아쓰기. 녹음 중 실시간 파형, 끝나면 전체 파형과 "📝 녹음된 말" 표시 |
| ✍️ 실시간 이야기 | LLM 이 JSON Lines 로 한 줄씩 쓰면 그 줄을 바로 읽기 시작. 누르자마자 미리 만들어 둔 인사말을 읽는 동안 제목을 씀 |
| 🎭 대사 연기 | 등장인물마다 목소리 유형(아이·어른·할머니·동물 등) → 화자 자동 배정 (해설자와 겹치면 같은 성별·나이대 후보 안에서). 줄마다 감정 지시 (예: "깜짝 놀라 숨을 들이켜며 높고 빠르게") |
| 🎨 삽화 | SDXL + SDXL-Lightning 4단계. 장면이 바뀌는 줄에서 그림이 바뀜. 표지를 참고(IP-Adapter Plus)해 주인공 모습 유지 |
| 📚 장 · 쪽수 | 장 1~5 × 장마다 2~6쪽, "제1장. 제목." 낭독, 장 이동. 쪽수는 코드가 강제 (덜 쓰면 이어 쓰기, 더 쓰면 마지막 쪽에 붙임) |
| 🔀 선택형 동화 | 장 끝마다 질문 → 버튼·말로 선택 → 그 선택대로 다음 장. 장 경계는 코드가 지킴 (LLM 이 질문을 빠뜨리면 따로 만듦) |
| 📖 책 재생기 | 음성 조각을 끊김 없이 이어 재생, 줄 강조 + 글자 따라 읽기, 자동 페이지 넘김. 소리가 한 번 끊기면 그 뒤로는 약 2초분 모아 두고 재생 |
| ⏳ 동시 사용 | 동시에 최대 2권(`MAX_BOOKS_AT_ONCE`), 넘으면 대기열. TTS 는 곧 소리가 끊길 책의 문장부터 만듦 |
| 🔢 숫자 읽기 | "3살" → "세 살", "20마리" → "스무 마리", "2025년" → "이천이십오년" (읽을 글에만) |
| 🛡️ 안정성 | 한국어 문장에 섞인 한자·중국어·영어 단어를 읽기 전에 한글로 고침 · LLM 서버가 응답하지 않으면 다른 사내 서버가 이어서 씀 · 문장 앞 디코더 잡음 제거 |

### 성능 (RTX 4080 SUPER 16GB, 2장×2쪽 선택형 동화, 실제 브라우저 측정)
| 항목 | 혼자 | 두 명이 동시에 |
|---|---|---|
| 버튼 클릭 → 첫 소리 | 0.2~0.5초 | 0.2초 / 0.2초 |
| 문장 중간 끊김 | 없음 | 없음 (쪽 넘김 쉼 약 1.2초) |
| 삽화 한 장 | 약 1.5~2초 | 약 1.5~3초 |
| 선택 → 다음 장 첫 음성 | 약 3초 ("좋아요!" 응답 0.3초) | |
| GPU 메모리 | 평소 약 11.8GB, 최대 약 13.7GB | |

---

## 구조 (계층형)

바깥으로 갈수록 바뀌기 쉬운 것(화면·모델·서버)이고, 안쪽 규칙(domain)은 그런 것에 의존하지 않습니다.
화면(ui) → 유스케이스(application) → 규칙(domain) · 어댑터(infra) 방향으로만 import 합니다.

```
story_app/
├─ app.py                        Streamlit 진입점 (화면 조립만)
├─ storybook/
│  ├─ config.py                  설정 (.env)
│  ├─ domain/                    순수 규칙 — 모델·파일·네트워크 없음 (tests/ 에서 단위 시험)
│  │  ├─ story_format.py         LLM 이야기 형식(JSON Lines) 해석, 깨진 줄 복구, 외국 글자 판별, 이어 쓰기용 원문 자르기
│  │  ├─ choices.py              선택형 질문 문장, 말한 대답 → 선택지 번호
│  │  ├─ voices.py               등장인물 화자 고르기, 줄마다 말투 지시
│  │  └─ textnorm.py             숫자·기호를 읽는 말로
│  ├─ infra/                     바깥 자원 어댑터
│  │  ├─ tts/                    TTS: 전용 작업 프로세스(worker.py) + 스트리밍 엔진(engine.py, streaming.py)
│  │  ├─ stt.py                  Whisper 받아쓰기
│  │  ├─ painter.py              SDXL-Lightning + IP-Adapter 그림
│  │  ├─ llm.py                  사내 LLM (스트리밍, 이어 쓰기, 선택지 만들기, 외국 글자 고치기)
│  │  ├─ book_store.py           책 저장소 (static/books/<id>/)
│  │  └─ runtime.py              프로세스 공용 객체, GPU 잠금
│  ├─ application/               유스케이스
│  │  ├─ book_maker.py           책 만들기 (이야기·음성·그림을 동시에, 장·쪽수, 선택형)
│  │  ├─ scheduler.py            동시 제작 대기열
│  │  └─ startup.py              모델 미리 올리기, 인사말 미리 만들기
│  └─ ui/                        화면
│     ├─ sidebar.py · make_page.py · shelf_page.py · stats_page.py · style.py
│     └─ components/             player.py(책 재생기) · micviz.py(녹음 파형) · choice_panel.py(선택 칸)
├─ scripts/                      download_models.py · make_cert.py · warmup.py
├─ tests/test_domain.py          domain 단위 시험
├─ requirements.txt · run.bat · .env.example · .streamlit/config.toml
├─ models/  certs/  data/  static/books/      (git 에 올리지 않음)
```

설계 메모
- **TTS 는 전용 작업 프로세스**에서 돕니다. 웹·LLM·그림 스레드와 한 프로세스에 두면 Python 잠금(GIL)을 나눠 써서
  두 권을 동시에 만들 때 낭독이 크게 끊겼습니다 (측정: 최대 41초 → 분리 후 끊김 없음).
- 받아쓰기·그림 모델은 한 스레드에서 **차례대로** 불러옵니다 (`from_pretrained(dtype=fp16)` 가 불러오는 동안 전역 기본 자료형을 바꿔 다른 스레드를 깨뜨림).
- 그림 모델의 UNet·VAE·IP-Adapter 는 GPU, 텍스트·이미지 인코더는 CPU(한 장에 약 0.3초) → GPU 메모리 절약.
  GPU 여유가 `PAINT_MIN_FREE_GB` 보다 적으면 자동으로 CPU 오프로드(한 장 약 4초).
- 받아쓰기 모델은 평소 RAM 에 두고 받아쓸 때만 GPU 로 옮깁니다.
- 책마다 `static/books/<id>/` 에 `book.json`(내용·진행 상황), `p<쪽>_<조각>.pcm`(음성 조각), `img_<번호>.png`(삽화)를 쓰고,
  브라우저 재생기가 이 파일들을 바로 읽어 갑니다. 책 주소는 날짜 + 추측할 수 없는 64비트 난수.

### GPU 메모리
| 모델 | 메모리 | 위치 |
|---|---|---|
| TTS Qwen3-TTS 1.7B CustomVoice (bf16, 최적화 컴파일) | 약 5GB | GPU, TTS 작업 프로세스 |
| 그림 UNet·VAE + IP-Adapter (fp16) | 약 6GB | GPU |
| 그림 텍스트·이미지 인코더 | 약 4GB | RAM (CPU) |
| 받아쓰기 Whisper large-v3-turbo (fp16) | 약 1.6GB | RAM, 받아쓸 때만 GPU |
| **합계 (화면 표시 포함, 실측)** | 평소 약 11.8GB, 최대 약 13.7GB / 16GB | |

GPU 를 쓰는 다른 프로그램(다른 TTS 앱, Ollama 등)을 함께 켜면 모자랄 수 있습니다.

## 설정 (.env)

| 키 | 설명 |
|---|---|
| `SERVER_IPS` | HTTPS 인증서에 넣을 이 PC 의 내부 IP (쉼표로 여러 개) |
| `TTS_MODEL` / `TTS_ATTN` / `STREAM_OPTIMIZE` | TTS 모델 경로 / 어텐션(sdpa) / 최적화 컴파일 (1 = 켬) |
| `WHISPER_PATH`, `SDXL_*`, `IP_ADAPTER_DIR` | 모델 경로 (기본 `./models/...`) |
| `PAINT_ON_GPU` / `PAINT_MIN_FREE_GB` | 그림 모델 GPU 상주 / 상주 후 최소 GPU 여유 (부족하면 자동 오프로드) |
| `CHARACTER_REF` / `REF_SCALE` | 주인공 모습 유지 켜기 / 표지를 따르는 정도 (기본 0.2, 0.3 이상이면 장면까지 표지를 닮아 감) |
| `MAX_BOOKS_AT_ONCE` | 동시에 만드는 책 수 (기본 2) |
| `BOOK_KEEP_DAYS` | 이 날수보다 오래된 책 자동 삭제 (기본 0 = 지우지 않음) |
| `LLM_DEFAULT` | 기본 이야기 AI 서버 (`FREETOKEN` 권장) |
| `STRATA_*`, `FREETOKEN_*` | 사내 OpenAI 호환 LLM 서버 (외부 유료 API 사용 안 함) |
| `HF_HUB_OFFLINE` | `1` = 인터넷에 접속하지 않음 (모델은 models\ 에서만) |

> `.env` 에는 API 키가 들어 있으므로 공유·커밋하지 마세요 (`.gitignore` 에 포함).

## 라이선스 참고
- Qwen3-TTS (모델·코드), Qwen3-TTS-streaming 변형판: Apache 2.0
- Whisper large-v3-turbo: MIT
- SDXL base 1.0 / SDXL-Lightning / sdxl-vae-fp16-fix: CreativeML Open RAIL++-M (사용 제한 조항 확인)
- IP-Adapter (h94/IP-Adapter): Apache 2.0 / 이미지 인코더 OpenCLIP ViT-H: MIT
