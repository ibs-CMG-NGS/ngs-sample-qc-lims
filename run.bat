@echo off
chcp 65001 > nul
setlocal

REM ── 가상환경 우선 사용, 없으면 시스템 Python ──────────────────
if exist venv\Scripts\python.exe (
    venv\Scripts\python main.py
) else (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [오류] Python을 찾을 수 없습니다.
        echo install.bat을 먼저 실행하세요.
        pause
        exit /b 1
    )
    python main.py
)
