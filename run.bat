@echo off
REM AI Story Reader on LAN (HTTPS for microphone): https://<this-PC-IP>:8502
REM Standalone app: loads its own TTS / STT / image models (first start takes about 2-3 min).
cd /d %~dp0
set PY=.venv\Scripts\python.exe
if not exist %PY% (echo .venv not found. See README: create it with uv first. & pause & exit /b 1)
if not exist certs\ca.crt %PY% scripts\make_cert.py
start "story-warmup" /min cmd /c "ping -n 9 127.0.0.1 >nul && %PY% scripts\warmup.py"
%PY% -m streamlit run app.py
