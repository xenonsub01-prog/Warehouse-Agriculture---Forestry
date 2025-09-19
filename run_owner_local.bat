@echo off
cd /d %~dp0
if not exist venv\Scripts\activate.bat (
  echo Please run setup.bat first.
  pause
  exit /b 1
)
call venv\Scripts\activate
start "" http://localhost:8502/?admin=admin12345
streamlit run app.py --server.port=8502
