# NGS Sample QC LIMS 시작 가이드

## 빠른 시작

### 1. Conda 환경 설정 (권장)

```powershell
# Conda 환경 생성 (최초 1회)
conda env create -f environment.yml

# Conda 환경 활성화
conda activate ngs-sample-qc-lims

# 환경 확인
conda list
```

### 1-1. 대안: Python venv 사용

```powershell
# 가상환경 생성
python -m venv venv

# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt
```

### 2. 프로그램 실행

```powershell
# Option 1: 실행 스크립트 사용 (권장)
.\run.ps1

# Option 2: 직접 실행
conda run -n ngs-sample-qc-lims python main.py

# Option 3: 환경 활성화 후 실행
conda activate ngs-sample-qc-lims
python main.py
```

### 3. 테스트 실행

```powershell
# Option 1: 테스트 스크립트 사용 (권장)
.\test.ps1

# Option 2: 직접 실행
conda run -n ngs-sample-qc-lims python tests\test_basic.py
```

## 주요 기능 사용법

### 샘플 등록
1. 메인 화면에서 "New Sample" 버튼 클릭
2. 샘플 타입 선택 (WGS / mRNA-seq)
3. 샘플 정보 입력

### 데이터 업로드
1. "Upload" 탭으로 이동
2. QC 데이터 파일을 드래그 앤 드롭
3. 자동 파싱 및 DB 저장

### QC 분석
1. "Analysis" 탭에서 샘플 선택
2. Progress Chart 확인
3. QC 판정 결과 확인

### Molarity 계산
1. Tools → Molarity Calculator
2. 농도 및 크기 입력
3. nM 값 자동 계산

## 파일 구조

```
ngs-sample-qc-lims/
├── main.py              # 프로그램 진입점
├── config/              # 설정
├── database/            # 데이터베이스 모델
├── parsers/             # 데이터 파서
├── analysis/            # QC 분석 로직
├── ui/                  # PyQt6 UI
├── examples/            # 예제 파일
└── tests/               # 테스트
```

## 문제 해결

### PyQt6 설치 오류
```powershell
pip install --upgrade pip
pip install PyQt6 --no-cache-dir
```

### 한글 폰트 문제
- Windows: 자동으로 "맑은 고딕" 사용
- macOS/Linux: matplotlib 설정에서 폰트 변경 필요

## 다음 단계

- [ ] 샘플 등록 UI 완성
- [ ] 파일 업로드 기능 구현
- [ ] Dashboard 시각화 완성
- [ ] PDF 리포트 생성
