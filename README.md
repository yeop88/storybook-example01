# 📖 AI 동화 낭독기

말로 주제를 들려주면 AI가 그림 동화를 쓰고, 그림을 그리고, 등장인물마다 다른 목소리와 감정으로 **실시간으로** 읽어 주는 내부망 웹 서비스입니다.
TTS·받아쓰기·그림 모델은 이 PC의 GPU 에 이 앱이 직접 올리고, 이야기는 사내 LLM 서버(FREETOKEN) 또는 OpenAI API 로 씁니다. 다른 프로젝트에 기대지 않는 독립 앱입니다.

```
🎤 말로 주제 ──STT(Whisper)──▶ 주제 글
                                   │
                ┌──────────────────┘
                ▼
     ✍️ LLM (FREETOKEN / OpenAI, 스트리밍) ── 한 줄씩 ──┬──▶ 🔊 TTS 스트리밍 (줄마다 화자·말투·감정 지시)
        제목 / 등장인물 / 페이지 / 대사·해설        │        → 음성 조각을 바로 브라우저로
                                                  └──▶ 🎨 SDXL-Lightning (장면이 바뀌는 곳마다 삽화)
                                                              → 완성되는 대로 화면에
```

접속: **https://<서버-IP>:8502** (마이크 때문에 HTTPS)

---

## 설치 (처음 한 번)

### 0. 준비물

| 항목 | 요구 사항 | 확인 방법 |
|---|---|---|
| OS | Windows 10 / 11 (64비트) | |
| GPU | NVIDIA, VRAM 16GB 권장 (RTX 4080 SUPER 에서 실측 최대 13.7GB) | `nvidia-smi` |
| GPU 드라이버 | CUDA 12.8 을 지원하는 드라이버 (570 이상) | `nvidia-smi` 오른쪽 위 `CUDA Version` 이 12.8 이상 |
| 디스크 | 여유 공간 약 30GB (모델 약 16GB + 가상환경 약 8GB + 책 저장) | |
| RAM | 32GB 권장 (그림 인코더·받아쓰기 모델을 RAM 에 둠) | |
| [uv](https://docs.astral.sh/uv/) | Python 3.12 와 패키지를 설치하는 도구 | `uv --version` |
| [Git](https://git-scm.com/download/win) | TTS 패키지(qwen-tts)를 GitHub 에서 받을 때 필요 | `git --version` |
| 이야기 LLM | 사내 FREETOKEN 서버 주소·API 키, 또는 OpenAI API 키 (둘 중 하나 이상) | `scripts\check_llm.py` (아래 4단계) |

uv 가 없으면 PowerShell 에서 설치합니다 (설치 후 터미널을 새로 여세요).
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> 아래 명령은 모두 **명령 프롬프트(cmd)** 기준이며, 이 프로젝트 폴더에서 실행합니다.

### 1. 프로젝트 받기

```bat
git clone <저장소 주소> storybook-example01
cd storybook-example01
```

### 2. 가상환경 + 패키지 설치 (약 5~10분, 약 8GB)

```bat
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt --index-strategy unsafe-best-match
```
- torch(CUDA 12.8), Qwen3-TTS 스트리밍 변형판, diffusers, streamlit, openai 등이 `.venv\` 에 설치됩니다.
- 사내망 인증서 오류(`UnknownIssuer`, `certificate verify failed`)가 나면 두 명령 끝에 `--system-certs` 를 붙이세요.
- 설치 확인 — `True` 와 GPU 이름이 나오면 정상:
  ```bat
  .venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
  ```

### 3. 모델 받기 (약 16GB → `models\`)

```bat
.venv\Scripts\python.exe scripts\download_models.py
```
| 모델 | 용도 | 폴더 |
|---|---|---|
| Qwen3-TTS-12Hz-1.7B-CustomVoice | 낭독 (TTS) | `models\Qwen3-TTS-12Hz-1.7B-CustomVoice` |
| Whisper large-v3-turbo | 말로 주제·선택 받아쓰기 (STT) | `models\whisper-large-v3-turbo` |
| SDXL base + SDXL-Lightning 4단계 UNet + fp16 VAE | 삽화 | `models\sdxl-base`, `sdxl-lightning`, `sdxl-vae-fp16-fix` |
| IP-Adapter Plus (ViT-H) | 주인공 모습 유지 | `models\ip-adapter` |

- 이미 받은 파일은 건너뛰므로, 중간에 끊겨도 같은 명령을 다시 실행하면 이어서 받습니다.
- 다 받은 뒤에는 인터넷에 접속하지 않습니다 (`.env` 의 `HF_HUB_OFFLINE=1`).

### 4. 설정 파일 `.env` 만들기

```bat
copy .env.example .env
notepad .env
```
꼭 채울 값:

| 키 | 예시 | 설명 |
|---|---|---|
| `SERVER_IPS` | `192.168.0.10` | 이 PC 의 내부 IP (`ipconfig` 의 IPv4 주소). HTTPS 인증서에 들어감. 여러 개면 쉼표로 |
| `LLM_DEFAULT` | `FREETOKEN` | 처음에 고를 이야기 AI 서버 (`FREETOKEN` 또는 `OPENAI`) |
| `FREETOKEN_BASE_URL` | `http://<서버-IP>:<포트>/v1` | 사내 FREETOKEN 서버 주소 (끝이 `/v1`) |
| `FREETOKEN_API_KEY` | `sk-...` | FREETOKEN 서버 API 키 |
| `FREETOKEN_MODEL` | (비움) | 비우면 서버의 첫 번째 모델을 씀 |
| `OPENAI_API_KEY` | `sk-...` | OpenAI 도 쓸 때만 (유료). 비우면 OpenAI 는 꺼짐 |
| `OPENAI_MODEL` | (비움) | 비우면 `gpt-4.1-mini` |

- FREETOKEN · OpenAI 중 **값을 채운 서버만** 사이드바에 나타납니다. 둘 다 채우면 한쪽이 실패할 때 다른 쪽이 이어서 씁니다.
- 나머지 키(모델 경로·GPU 옵션 등)는 기본값 그대로 두면 됩니다. 전체 목록은 아래 [설정 (.env)](#설정-env) 참고.

**LLM 연결 확인** (TTS·그림 모델 없이도 바로 돎, 약 10~60초):
```bat
.venv\Scripts\python.exe scripts\check_llm.py
.venv\Scripts\python.exe scripts\check_llm.py FREETOKEN
```
첫 줄은 설정된 서버 모두, 둘째 줄은 하나만 확인합니다. `✅ 정상` 이 나오면 됩니다.
`❌` 가 나오면 함께 나온 안내를 따르세요 (401 = 키 오류, 연결 실패 = 주소·사내망 확인).

### 5. 방화벽 열기 (다른 PC 에서 접속할 때, 관리자 cmd 에서 한 번)

```bat
netsh advfirewall firewall add rule name="AI Story 8502" dir=in action=allow protocol=TCP localport=8502
```

---

## 사용법

### 1. 서버 켜기

```bat
run.bat
```
1. 처음 실행하면 HTTPS 인증서를 자동으로 만듭니다 (`certs\ca.crt`, `cert.pem`, `key.pem`, `install_cert.bat`).
2. TTS 작업 프로세스가 뜨고, 받아쓰기·그림 모델을 차례로 GPU 에 올립니다. `run.bat` 이 따로 띄우는 `story-warmup` 창이 첫 세션을 열어 모델을 미리 올려 둡니다.
3. 준비까지 **첫 실행 약 3분**(TTS 최적화 컴파일), 이후 약 1분. 브라우저 사이드바 **준비 상태** 세 줄(목소리·받아쓰기·그림)이 모두 ✅ 이면 시작할 수 있습니다. `🔄 상태 새로고침` 으로 다시 확인하세요.
- 서버를 끌 때까지 모델은 GPU 에 그대로 있습니다. 끄려면 `run.bat` 창에서 `Ctrl+C`.
- 서버 PC 에서는 `https://localhost:8502`, 다른 PC 에서는 `https://<SERVER_IPS 의 IP>:8502` 로 접속합니다.

### 2. 접속하는 PC: 인증서 설치 (PC 마다 한 번)

브라우저는 `http://IP주소` 에서 마이크를 막아서 HTTPS 로 엽니다. 내부 IP 는 공개 무료 인증서(Let's Encrypt 등)를 받을 수 없어서
**사내용 무료 인증기관(CA)** 으로 발급합니다 (mkcert 와 같은 원리).

1. `https://<서버-IP>:8502` 접속 → 처음 한 번만 "연결이 비공개로 설정되어 있지 않습니다" → **고급 → 계속**
2. 왼쪽 사이드바 **🔒 보안 연결(인증서) 설치 → 🪟 Windows 설치 파일** 내려받아 실행 → 보안 경고에서 **예** (관리자 권한 불필요)
3. 브라우저를 **모두 닫고** 다시 접속 → 주소창에 🔒
- Mac·휴대폰은 "📱 인증서 파일 (Mac·휴대폰용)" 을 받아 설치 (Android: 설정 → 보안 → 인증서 설치 → CA 인증서 / iPhone: 프로필 설치 → 설정 → 일반 → 정보 → 인증서 신뢰 설정에서 켜기)
- 여러 PC 에 한 번에: 관리자가 `certs\ca.crt` 를 그룹 정책(GPO)의 "신뢰할 수 있는 루트 인증 기관" 에 등록
- 이 CA 는 사설 IP·localhost 에만 발급하도록 이름 제약이 걸려 있어 키가 새어도 외부 사이트를 위장할 수 없습니다. 그래도 `certs\ca.key` 는 공유하지 마세요.

### 3. 화면 구성

| 위치 | 내용 |
|---|---|
| 왼쪽 사이드바 | 준비 상태(목소리·받아쓰기·그림), **이야기 AI 서버** 선택(FREETOKEN / OPENAI), 인증서 설치 |
| 위쪽 메뉴 | **✨ 동화 만들기** · **📚 책장** · **📊 통계** |
| ✨ 동화 만들기 | 왼쪽: 만들기 옵션 1~4단계 / 오른쪽: 책 재생기 ("📖 여기에 동화책이 펼쳐져요") |

### 4. 동화 만들기

**① 어떤 이야기를 들려줄까요?**
- 🎤 버튼을 누르고 주제를 말한 뒤 ⏹ → 녹음 파형과 "📝 녹음된 말" 이 보이고, 받아쓴 글이 **이야기 주제** 칸에 들어갑니다.
- 직접 입력하거나 **💡 예시 주제** 에서 골라도 됩니다. 예: "바닷속에서 길을 잃은 꼬마 문어가 친구들과 집을 찾는 이야기"

**② 꾸미기**
- 주인공 이름·담고 싶은 교훈 (선택, 비우면 AI 가 정함)
- **듣는 아이 나이**: 나이에 맞게 문장 길이·낱말을 조절 (기본 6~8세)
- **언어**: 한국어 / 영어 (영어를 고르면 본문만 영어, 말투 지시는 한국어)

**③ 구성**
- **장(챕터) 수** 1~5 × **쪽수(장마다)** 2~6 → 표지 + 전체 쪽수가 아래에 표시됩니다. 쪽수는 정확히 지켜요 (덜 쓰면 이어 쓰고, 더 쓰면 마지막 쪽에 붙임).
- 장이 2개 이상이면 **📝 장별 제목·줄거리 직접 정하기** 에서 장마다 제목·줄거리를 정할 수 있습니다 (비우면 AI 가 정함).
- **🔀 선택형 동화** (장 2개 이상): 장이 끝날 때마다 해설자가 질문하고, 아이가 ①② 버튼이나 🎤 말로 고르면 그 선택대로 다음 장이 이어집니다.

**④ 그림과 목소리**
- **그림체** 6가지, **해설 목소리** 6가지(여자·젊은 여자·남자·젊은 남자·할머니·할아버지), 해설 느낌
- **등장인물 대사**: 인물마다 다른 목소리로 연기할지, 해설자가 모두 읽을지

**⑤ ✨ 동화 만들기** → 오른쪽 재생기에서 바로 읽기 시작합니다 (첫 소리 약 0.2~0.5초). 인사말을 읽는 동안 AI 가 제목을 쓰고, 그 뒤로는 쓰는 대로 읽습니다.
- 다른 책을 만드는 중이면 버튼 위에 안내가 나오고, 동시 제작 한도(`MAX_BOOKS_AT_ONCE`, 기본 2권)를 넘으면 차례를 기다립니다.

### 5. 책 재생기

| 조작 | 동작 |
|---|---|
| ⏸ / ▶ | 멈춤 / 이어 읽기 |
| ◀ 이전 · 다음 ▶ | 쪽 이동 |
| ↺ 처음부터 | 표지부터 다시 |
| 장 버튼 | 해당 장으로 이동 (장이 여러 개일 때) |
| 줄 위에 마우스 | AI 가 정한 말투·감정 지시 보기 |

- 지금 읽는 줄이 강조되고, 읽은 글자가 진하게 바뀝니다(글자 따라 읽기). 쪽은 자동으로 넘어갑니다.
- 삽화는 장면이 바뀌는 줄에서 완성되는 대로 바뀝니다 (한 장 약 1.5~3초).
- 소리가 안 나면 재생기의 **"▶ 눌러서 소리 켜기"** 를 누르세요 (브라우저 자동 재생 차단).

### 6. 책장 · 통계

- **📚 책장**: 만든 책 목록 (제목·상태·만든 날·장·쪽수). 📖 다시 읽기 / 🗑️ 삭제. 위에 책 수와 사용 용량이 표시됩니다.
  `BOOK_KEEP_DAYS` 를 정하면 그 날수보다 오래된 책은 자동으로 지워집니다.
- **📊 통계**(관리자용): 지금 만드는 책·대기, 완료율, 첫 소리, 삽화 시간, 동화 길이, AI 서버 전환·외국 글자 수정 횟수, 책별 기록.

### 7. 개발 · 확인

```bat
:: 순수 규칙(domain) 단위 시험 — 모델 없이 바로 돎
.venv\Scripts\python.exe -m unittest discover -s tests -v

:: 이야기 LLM 서버 연결·속도 확인
.venv\Scripts\python.exe scripts\check_llm.py

:: 서버 IP 가 바뀌었을 때 인증서 다시 발급 (CA 는 유지 → 각 PC 재설치 불필요)
.venv\Scripts\python.exe scripts\make_cert.py
:: CA 부터 새로 (각 PC 에 다시 설치해야 함)
.venv\Scripts\python.exe scripts\make_cert.py --new-ca
```
코드나 `.env` 를 고치면 서버를 다시 켜야 반영됩니다 (`fileWatcherType = "none"`, 모델을 두 번 올리지 않기 위해).

### 8. 문제 해결

| 증상 | 원인 · 해결 |
|---|---|
| `run.bat` 이 ".venv not found" | 설치 2단계(가상환경)를 먼저 하세요 |
| 사이드바 "이야기 AI 서버" 목록이 비어 있음 / 만들기 버튼이 눌리지 않음 | `.env` 에 `FREETOKEN_BASE_URL` 또는 `OPENAI_API_KEY` 가 없음 → 채우고 서버 다시 켜기 |
| `check_llm.py` 가 401 Unauthorized | API 키가 틀렸거나 만료됨 → `.env` 의 `*_API_KEY` 확인 (앞뒤 공백·따옴표 없이) |
| `check_llm.py` 가 연결 실패 | `*_BASE_URL` 의 IP·포트 확인, 사내망(VPN) 접속, LLM 서버가 켜져 있는지 확인 |
| 준비 상태가 계속 ⏳ | 첫 실행은 TTS 컴파일로 약 3분. `run.bat` 창의 오류 확인. 모델 폴더가 없으면 설치 3단계 |
| `CUDA out of memory` | GPU 를 쓰는 다른 프로그램(다른 TTS 앱, Ollama 등)을 끄기. `.env` 에서 `PAINT_ON_GPU=0`(그림 CPU 오프로드, 한 장 약 4초) 또는 `STREAM_OPTIMIZE=0` |
| 🎤 버튼이 안 되거나 마이크 권한이 안 뜸 | `http://` 로 접속했거나 인증서 미설치 → `https://` 로 접속하고 사용법 2단계 인증서 설치 |
| "연결이 비공개로 설정되어 있지 않습니다" 가 계속 뜸 | 인증서 설치 후 브라우저를 **모두** 닫았다 다시 열기. 서버 IP 가 바뀌었으면 `scripts\make_cert.py` |
| 다른 PC 에서 접속이 안 됨 | 설치 5단계 방화벽 규칙, 같은 사내망인지, `SERVER_IPS` 가 실제 IP 인지 확인 |
| 소리가 안 남 | 재생기의 "▶ 눌러서 소리 켜기", 브라우저 탭 음소거·PC 볼륨 확인 |
| 포트 8502 가 이미 사용 중 | 이전 서버 창이 남아 있음 → 그 창에서 `Ctrl+C`, 또는 `.streamlit\config.toml` 의 `port` 변경 |

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
| 🛡️ 안정성 | 한국어 문장에 섞인 한자·중국어·영어 단어를 읽기 전에 한글로 고침 · LLM 서버가 응답하지 않으면 다른 서버(FREETOKEN ↔ OpenAI)가 이어서 씀 · 문장 앞 디코더 잡음 제거 |

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
storybook-example01/
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
│  │  ├─ llm.py                  이야기 LLM (FREETOKEN / OpenAI, 스트리밍, 이어 쓰기, 선택지 만들기, 외국 글자 고치기)
│  │  ├─ book_store.py           책 저장소 (static/books/<id>/)
│  │  └─ runtime.py              프로세스 공용 객체, GPU 잠금
│  ├─ application/               유스케이스
│  │  ├─ book_maker.py           책 만들기 (이야기·음성·그림을 동시에, 장·쪽수, 선택형)
│  │  ├─ scheduler.py            동시 제작 대기열
│  │  └─ startup.py              모델 미리 올리기, 인사말 미리 만들기
│  └─ ui/                        화면
│     ├─ sidebar.py · make_page.py · shelf_page.py · stats_page.py · style.py
│     └─ components/             player.py(책 재생기) · micviz.py(녹음 파형) · choice_panel.py(선택 칸)
├─ scripts/                      download_models.py · make_cert.py · warmup.py · check_llm.py
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
| `LLM_DEFAULT` | 기본 이야기 AI 서버 (`FREETOKEN` 또는 `OPENAI`) |
| `FREETOKEN_*` | 사내 OpenAI 호환 LLM 서버 (주소·키·모델) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | OpenAI API (키를 채우면 사용, 유료 · 모델 기본 `gpt-4.1-mini`) |
| `HF_HUB_OFFLINE` | `1` = 인터넷에 접속하지 않음 (모델은 models\ 에서만) |

> `.env` 에는 API 키가 들어 있으므로 공유·커밋하지 마세요 (`.gitignore` 에 포함).

## 라이선스 참고
- Qwen3-TTS (모델·코드), Qwen3-TTS-streaming 변형판: Apache 2.0
- Whisper large-v3-turbo: MIT
- SDXL base 1.0 / SDXL-Lightning / sdxl-vae-fp16-fix: CreativeML Open RAIL++-M (사용 제한 조항 확인)
- IP-Adapter (h94/IP-Adapter): Apache 2.0 / 이미지 인코더 OpenCLIP ViT-H: MIT
