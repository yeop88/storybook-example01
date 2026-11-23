"""사이드바: 모델 준비 상태, 이야기 AI 서버 선택, 인증서 설치 안내."""

import streamlit as st

from storybook import config
from storybook.application import startup


def render() -> dict:
    """사이드바를 그리고 {"llm": 고른 서버, "ready": TTS 준비 여부} 를 돌려줌."""
    with st.sidebar:
        st.title("📖 AI 동화 낭독기")
        st.caption("말로 주제를 들려주면 AI가 그림 동화를 만들어 읽어 줘요.")
        st.markdown("#### 준비 상태")
        s = startup.status()
        st.write(("✅" if s["tts_ready"] else "⏳") + f" 목소리(TTS): {s['tts']}")
        st.write(("✅" if s["stt"] == "준비 완료" else "⏳") + f" 받아쓰기(STT): {s['stt']}")
        st.write(("✅" if s["paint"].startswith("준비 완료") else "⏳") + f" 그림: {s['paint']}")
        if st.button("🔄 상태 새로고침", width="stretch"):
            st.rerun()
        st.divider()
        providers = list(config.LLM_PROVIDERS)
        llm = st.selectbox("이야기 AI 서버", providers,
                           index=providers.index(config.LLM_DEFAULT) if config.LLM_DEFAULT in providers else 0)
        _certificate_help()
    return {"llm": llm, "ready": s["tts_ready"] and bool(config.LLM_PROVIDERS), "tts_status": s["tts"]}


def _certificate_help():
    with st.expander("🔒 보안 연결(인증서) 설치"):
        st.caption("마이크는 HTTPS 에서만 동작해요. 아래 파일을 PC마다 **한 번** 실행하면 "
                   "'안전하지 않음' 경고 없이 접속돼요. (관리자 권한 불필요, 무료 사내 인증서)")
        bat, crt = config.CERT_DIR / "install_cert.bat", config.CERT_DIR / "ca.crt"
        if bat.exists():
            st.download_button("🪟 Windows 설치 파일", bat.read_bytes(), "install_cert.bat",
                               mime="application/octet-stream", width="stretch")
            st.caption("① 내려받은 파일 실행 → ② 보안 경고에서 '예' → ③ 브라우저를 모두 닫고 다시 접속")
        if crt.exists():
            st.download_button("📱 인증서 파일 (Mac·휴대폰용)", crt.read_bytes(), "ai_story_lan_ca.crt",
                               mime="application/x-x509-ca-cert", width="stretch")
            st.caption("Android: 설정 → 보안 → 인증서 설치 → CA 인증서 / iPhone: 프로필 설치 후 "
                       "설정 → 일반 → 정보 → 인증서 신뢰 설정에서 켜기")
