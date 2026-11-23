"""AI 동화 낭독기 — Streamlit 진입점 (화면 조립만, 실제 일은 storybook 패키지).

실행: run.bat  (또는 .venv\\Scripts\\python.exe -m streamlit run app.py)
"""

from storybook import config  # noqa: F401  (.env 를 가장 먼저 로드)

import streamlit as st

st.set_page_config(page_title="AI 동화 낭독기", page_icon="📖", layout="wide")

from storybook.application import startup  # noqa: E402
from storybook.ui import make_page, shelf_page, sidebar, stats_page, style  # noqa: E402

startup.start()  # TTS·STT·그림 모델을 백그라운드로 올리고 인사말을 미리 만들어 둠 (프로세스당 한 번)
style.apply()
ctx = sidebar.render()

view = st.radio("화면", ["✨ 동화 만들기", "📚 책장", "📊 통계"], horizontal=True, label_visibility="collapsed",
                key="view")
if view == "✨ 동화 만들기":
    make_page.render(ctx)
elif view == "📚 책장":
    shelf_page.render()
else:
    stats_page.render()
