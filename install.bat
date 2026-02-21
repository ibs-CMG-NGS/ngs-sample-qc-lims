@echo off
chcp 65001 > nul
setlocal

echo ============================================================
echo   NGS Sample QC LIMS - 설치 스크립트
echo ============================================================
echo.

REM ── Python 존재 확인 ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo Python 3.9 이상을 설치한 후 다시 실행하세요.
    echo 다운로드: https://www.python.org/downloads/
    echo.
    echo 설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER% 확인

REM ── 가상환경 생성 ─────────────────────────────────────────────
if exist venv\Scripts\python.exe (
    echo [OK] 가상환경이 이미 존재합니다. 건너뜁니다.
) else (
    echo.
    echo [1/2] 가상환경 생성 중...
    python -m venv venv
    if errorlevel 1 (
        echo [오류] 가상환경 생성 실패
        pause
        exit /b 1
    )
    echo [OK] 가상환경 생성 완료
)

REM ── 패키지 설치 ────────────────────────────────────────────────
echo.
echo [2/2] 패키지 설치 중... (인터넷 연결 필요)
venv\Scripts\pip install --upgrade pip -q
venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [오류] 패키지 설치 실패
    echo requirements.txt 확인 후 다시 시도하세요.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   설치 완료!
echo.
echo   실행 방법:
echo     - run.bat 더블클릭
echo     - 또는: venv\Scripts\python main.py
echo ============================================================
echo.
pause
