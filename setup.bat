@echo off
cd /d %~dp0
python -m venv venv
if not exist venv\Scripts\activate.bat (
  echo Failed to create venv. Ensure Python 3.10+ installed.
  pause
  exit /b 1
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo Setup complete.
pause
