# NGS Sample QC LIMS (Light Version)

NGS 실험 샘플의 품질 관리를 위한 경량 Laboratory Information Management System

## 🎯 주요 기능

### 1. 샘플 타입별 워크플로우 관리
- **Whole Genome Sequencing (WGS)**: DNA extraction → Fragmentation → Library Prep → Pooling
- **mRNA-seq**: RNA extraction → QC → Library Prep → Pooling

### 2. 자동화된 데이터 처리
- **NanoDrop/Qubit**: CSV/Excel 파일 드래그 앤 드롭 자동 업로드
- **Femto Pulse**: GQN, Peak Size, Average Size 자동 추출
- **Molarity 자동 계산**: Qubit 농도 + Femto Pulse 크기 → nM 변환

### 3. 실시간 QC 모니터링
- 단계별 Progress Chart (신호등: Pass/Warning/Fail)
- Femto Pulse 전/후 sizing 그래프 오버레이
- 인터랙티브 데이터 시각화

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────┐
│         데이터 입력 (파일 업로드)            │
│   NanoDrop │ Qubit │ Femto Pulse            │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│           데이터 파서 모듈                   │
│  CSV/Excel/XML → 표준화된 데이터 구조       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│        SQLite 데이터베이스                   │
│  Samples │ QC_Metrics │ Raw_Traces          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│     PyQt6 GUI + 시각화                       │
│  Dashboard │ Charts │ Reports               │
└─────────────────────────────────────────────┘
```

## 📦 설치 방법

### Option 1: Conda 환경 (권장)

```bash
# Conda 환경 생성
conda env create -f environment.yml

# 환경 활성화
conda activate ngs-sample-qc-lims

# 프로그램 실행
python main.py
```

### Option 2: Python venv

```bash
# 가상환경 생성
python -m venv venv
venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 프로그램 실행
python main.py
```

## 🗄️ 데이터베이스 스키마

### Samples 테이블
- `sample_id` (PK): 샘플 고유 ID
- `sample_type`: WGS / mRNA-seq
- `source`: 샘플 출처 정보
- `created_at`: 등록 일시

### QC_Metrics 테이블
- `metric_id` (PK)
- `sample_id` (FK)
- `step`: Extraction / Fragmentation / Library / Pooling
- `concentration`: ng/µl
- `purity_260_280`: NanoDrop 순도
- `gqn_rin`: GQN (DNA) 또는 RIN (RNA)
- `avg_size`: bp
- `status`: Pass / Warning / Fail
- `measured_at`: 측정 일시

### Raw_Traces 테이블
- `trace_id` (PK)
- `sample_id` (FK)
- `file_path`: Femto Pulse 원본 데이터 경로
- `image_path`: 저장된 그래프 이미지 경로

## 🔬 QC 판정 기준

### DNA (WGS)
- **Pass**: GQN ≥ 7.0, Library Size 300-700 bp
- **Warning**: GQN 5.0-7.0 또는 Size 범위 미달
- **Fail**: GQN < 5.0

### RNA (mRNA-seq)
- **Pass**: RIN ≥ 8.0
- **Warning**: RIN 6.0-8.0
- **Fail**: RIN < 6.0

## 📊 Molarity 계산식

```
Molarity (nM) = (Concentration [ng/µl] × 10^6) / (Average Size [bp] × 650)
```
- 650: DNA 1bp의 평균 분자량 (g/mol)

## 🛠️ 기술 스택

- **Backend**: Python 3.11
- **Database**: SQLite + SQLAlchemy ORM
- **GUI**: PyQt5 (안정적인 Qt5 기반)
- **Data Processing**: pandas, openpyxl
- **Visualization**: Matplotlib, Plotly
- **Parsing**: lxml (XML 처리)

## 📝 사용 가이드

1. **샘플 등록**: 메인 화면에서 샘플 타입 선택 및 정보 입력
2. **데이터 업로드**: 각 단계별 QC 파일 드래그 앤 드롭
3. **자동 분석**: 시스템이 자동으로 데이터 파싱 및 판정
4. **결과 확인**: Dashboard에서 진행 상황 및 그래프 확인
5. **리포트 생성**: 샘플별 종합 QC 리포트 PDF 출력

## 📂 프로젝트 구조

```
ngs-sample-qc-lims/
├── main.py                 # 프로그램 진입점
├── requirements.txt        # Python 의존성
├── config/
│   └── settings.py        # 설정 파일
├── database/
│   ├── models.py          # SQLAlchemy 모델
│   └── db_manager.py      # DB 연결 관리
├── parsers/
│   ├── nanodrop_parser.py
│   ├── qubit_parser.py
│   └── femtopulse_parser.py
├── ui/
│   ├── main_window.py     # 메인 윈도우
│   ├── dashboard.py       # 대시보드
│   └── widgets/           # 커스텀 위젯
├── analysis/
│   ├── qc_judge.py        # QC 판정 로직
│   ├── molarity_calc.py   # Molarity 계산
│   └── visualizer.py      # 차트 생성
└── data/                  # 샘플 데이터 저장소
```

## 🚀 향후 개발 계획

- [ ] 다중 샘플 일괄 업로드
- [ ] 통계 분석 기능 (배치별 품질 비교)
- [ ] 클라우드 연동 (Google Sheets API)
- [ ] 자동 알림 시스템 (QC Fail 시 이메일)
- [ ] 시퀀싱 리드 매핑 결과 통합

## 📄 라이센스

MIT License

## 👥 기여자

개발 및 유지보수를 환영합니다!
