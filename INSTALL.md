# NGS Sample QC LIMS — 설치 가이드

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Windows 10 64-bit | Windows 11 64-bit |
| Python | 3.9 | 3.11 ~ 3.14 |
| RAM | 4 GB | 8 GB 이상 |
| 디스크 | 500 MB | 1 GB 이상 |
| 인터넷 | 설치 시 필요 | — |

> macOS / Linux에서도 동작하지만 Windows 환경에서 개발·테스트되었습니다.

---

## 방법 1 — 원클릭 설치 (Windows 권장)

### 1단계: Python 설치

1. [python.org/downloads](https://www.python.org/downloads/) 에서 **Python 3.11 이상** 다운로드
2. 설치 시 반드시 **"Add Python to PATH"** 체크 후 설치

   ![Python PATH 체크 화면 예시](docs/images/python_install_path.png)

3. 설치 완료 후 확인:
   ```
   Win + R → cmd → python --version
   ```
   `Python 3.11.x` 와 같이 출력되면 정상

### 2단계: 소스코드 준비

**방법 A: Git으로 클론 (Git 설치 필요)**
```bat
git clone https://github.com/your-org/ngs-sample-qc-lims.git
cd ngs-sample-qc-lims
```

**방법 B: ZIP 다운로드**
- GitHub 페이지 → `Code` → `Download ZIP`
- 압축 해제 후 폴더로 이동

### 3단계: 설치 및 실행

탐색기에서 프로젝트 폴더를 열고:

```
install.bat  ← 더블클릭 (최초 1회)
run.bat      ← 더블클릭 (이후 실행)
```

---

## 방법 2 — 수동 설치 (pip + venv)

```bat
REM 프로젝트 폴더에서 실행
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

이후 실행할 때마다:
```bat
venv\Scripts\activate
python main.py
```

또는 가상환경 활성화 없이:
```bat
venv\Scripts\python main.py
```

---

## 방법 3 — Conda 환경

Anaconda 또는 Miniconda가 설치된 경우:

```bat
conda env create -f environment.yml
conda activate ngs-qc-lims
python main.py
```

이후 실행:
```bat
conda activate ngs-qc-lims
python main.py
```

---

## 데이터베이스 위치

프로그램이 처음 실행되면 자동으로 생성됩니다:

```
ngs-sample-qc-lims/
└── data/
    └── lims.db        ← SQLite 데이터베이스 (샘플·QC 데이터 저장)
```

> **다른 PC로 데이터 이전 시** `data/lims.db` 파일을 복사하면 됩니다.

---

## GUI 설정 파일 위치

창 크기·위치, 테이블 컬럼 너비 등의 화면 설정은 아래에 저장됩니다:

```
ngs-sample-qc-lims/
└── config/
    └── gui_state.ini  ← 자동 생성, 삭제해도 무방 (기본값으로 초기화됨)
```

---

## 문제 해결

### `python` 명령을 찾을 수 없음
- Python 설치 시 **"Add Python to PATH"** 를 체크했는지 확인
- 또는 `py --version` (Windows Python Launcher) 으로 시도
- 그래도 안 되면 Python을 재설치

### 패키지 설치 중 오류 (`pip install` 실패)
```bat
REM pip 업그레이드 후 재시도
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\pip install -r requirements.txt
```

### PyQt5 관련 DLL 오류 (Windows)
Microsoft Visual C++ 재배포 패키지가 필요합니다:
- [Visual C++ 재배포 패키지 다운로드](https://aka.ms/vs/17/release/vc_redist.x64.exe)
- 설치 후 재시도

### Conda 환경에서 PyQt5 화면이 안 보임
```bat
conda install -c conda-forge pyqt
```

### `No module named 'PyQt5'` 오류
가상환경이 활성화되지 않은 상태에서 실행 중입니다:
```bat
REM run.bat 사용 권장, 또는:
venv\Scripts\python main.py
```

### 데이터베이스 오류 (`no such column`)
스키마 마이그레이션이 자동으로 실행됩니다. 오류가 지속되면:
```bat
REM data/lims.db 삭제 후 재실행 (데이터가 모두 삭제되니 주의)
del data\lims.db
python main.py
```

---

## 의존 패키지 목록

| 패키지 | 용도 | 최소 버전 |
|--------|------|-----------|
| PyQt5 | GUI 프레임워크 | 5.15 |
| SQLAlchemy | 데이터베이스 ORM | 2.0 |
| matplotlib | 차트 + PDF 리포트 | 3.7 |
| pandas | 데이터 파싱·처리 | 2.0 |
| numpy | 수치 계산 | 1.24 |
| openpyxl | Excel 읽기/쓰기 | 3.1 |

---

## 업데이트

```bat
REM Git 사용 시
git pull
venv\Scripts\pip install -r requirements.txt

REM 또는 install.bat 재실행 (가상환경이 이미 있으면 패키지만 재설치)
install.bat
```

---

## 개발 환경 설정 (코드 수정·기여 목적)

사용 목적이 아닌 **개발·수정** 목적으로 설치하는 경우 아래 단계를 추가로 진행합니다.

### 1단계: Git 설치 및 설정

1. [git-scm.com](https://git-scm.com/download/win) 에서 Git for Windows 설치
2. 설치 후 사용자 정보 등록:
   ```bat
   git config --global user.name "Your Name"
   git config --global user.email "your@email.com"
   ```

### 2단계: 소스코드 클론

ZIP 다운로드 대신 반드시 Git으로 클론합니다 (push/pull을 위해):

```bat
git clone https://github.com/ibs-CMG-NGS/ngs-sample-qc-lims.git
cd ngs-sample-qc-lims
```

> Private 저장소인 경우 GitHub Personal Access Token(PAT) 또는 SSH 키 설정이 필요합니다.
> - PAT: GitHub → Settings → Developer settings → Personal access tokens → Generate new token
> - 클론 시 비밀번호 대신 PAT를 입력

### 3단계: Python 가상환경 및 패키지 설치

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 4단계: VSCode 설치 및 설정

1. [code.visualstudio.com](https://code.visualstudio.com/) 에서 VSCode 설치
2. 아래 익스텐션 설치 (VSCode 내 Extensions 탭에서 검색):

   | 익스텐션 | 용도 |
   |----------|------|
   | Python (Microsoft) | 자동완성, 디버깅, 린팅 |
   | Pylance | 타입 힌트, 코드 분석 |
   | GitLens | Git 히스토리·blame 시각화 |

3. VSCode에서 프로젝트 폴더 열기:
   ```bat
   code ngs-sample-qc-lims
   ```

4. Python 인터프리터 선택: `Ctrl+Shift+P` → "Python: Select Interpreter" → `venv\Scripts\python.exe` 선택

### 5단계: Claude Code 설치 (AI 코딩 어시스턴트, 선택)

Node.js가 필요합니다:

1. [nodejs.org](https://nodejs.org/) 에서 Node.js LTS 설치
2. Claude Code 설치:
   ```bat
   npm install -g @anthropic-ai/claude-code
   ```
3. 프로젝트 폴더에서 실행:
   ```bat
   cd ngs-sample-qc-lims
   claude
   ```

### 개발 워크플로

```bat
REM 1. 최신 코드 받기
git pull

REM 2. 가상환경 활성화
venv\Scripts\activate

REM 3. 앱 실행 (코드 수정 후 확인)
python main.py

REM 4. 변경사항 커밋
git add .
git commit -m "설명"
git push
```

### 데이터베이스 공유

`data/lims.db`는 `.gitignore`에 포함되어 **Git으로 공유되지 않습니다.** PC 간 데이터 이전이 필요하면 파일을 직접 복사합니다:

```bat
REM 다른 PC → 이 PC로 복사
copy \\other-pc\share\lims.db data\lims.db
```

> 두 PC에서 동시에 데이터를 입력하는 경우 나중에 병합이 필요하므로, 한 대를 주 입력용으로 지정하는 것을 권장합니다.

---

## 디렉터리 구조

```
ngs-sample-qc-lims/
├── main.py                 # 진입점
├── install.bat             # 원클릭 설치 (Windows)
├── run.bat                 # 원클릭 실행 (Windows)
├── requirements.txt        # pip 의존 패키지
├── environment.yml         # Conda 환경 정의
├── config/
│   ├── settings.py         # 앱 설정
│   ├── gui_state.py        # GUI 상태 저장 유틸리티
│   └── gui_state.ini       # GUI 상태 파일 (자동 생성, git 제외)
├── database/
│   ├── models.py           # DB 스키마 (SQLAlchemy)
│   └── db_manager.py       # DB 연결·마이그레이션
├── parsers/                # NanoDrop / Qubit / Femto Pulse 파서
├── analysis/               # QC 판정·시각화
├── ui/                     # PyQt5 GUI
│   ├── main_window.py
│   ├── dashboard_tab.py
│   ├── sample_tab.py
│   ├── analysis_tab.py
│   ├── reports_tab.py
│   └── dialogs.py
└── data/
    └── lims.db             # SQLite DB (자동 생성, git 제외)
```
