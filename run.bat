@echo off
REM AI Story Reader on LAN (HTTPS for microphone): https://<this-PC-IP>:8502
REM Needs tts_app_streaming running on this PC (shares its TTS model via http://127.0.0.1:8601).
cd /d %~dp0
set PY=..\tts_streaming\.venv\Scripts\python.exe
if not exist certs\ca.crt %PY% make_cert.py
start "story-warmup" /min cmd /c "ping -n 9 127.0.0.1 >nul && %PY% warmup.py"
%PY% -m streamlit run app.py
