# NGS Sample QC LIMS

NGS 실험 샘플의 품질 관리를 위한 경량 Laboratory Information Management System.  
PacBio Revio 시퀀싱 워크플로우 전체(전처리 QC → 런 설계 → 시퀀싱 결과)를 단일 앱에서 추적합니다.

---

## 주요 기능

### 샘플 관리 (Sample 탭)
- 샘플 등록 / 편집 / 삭제 — Project, 종(Species), 재료(Material), 유형(WGS / mRNA-seq) 포함
- **Branch 샘플** 지원: Re-extraction / Aliquot / Other 유형으로 원본 샘플에서 파생 이력 추적
- Project / Type / Branch 필터 콤보 + 전체 텍스트 검색
- 샘플 선택 시 QC 지표 상세 테이블 + 시퀀싱 결과 서브테이블 표시
- QC 지표 및 시퀀싱 결과 개별 삭제 (우클릭 컨텍스트 메뉴)

### 데이터 업로드 — 전처리 QC
| 기기 | 업로드 방법 | 추출 지표 |
|------|------------|---------|
| NanoDrop | CSV 드래그 앤 드롭 | 농도, A260/280, A260/230 |
| Qubit | CSV 드래그 앤 드롭 | 농도 (ng/µl) |
| Femto Pulse | XML/ZIP 드래그 앤 드롭 | GQN, Peak Size, Avg Size, 전기영동 그래프 |
| Qubit (라이브러리) | CSV 드래그 앤 드롭 | 농도 + Molarity 자동 계산 |

- Molarity 자동 계산: `(ng/µl × 10⁶) / (avg_size[bp] × 650)`
- Femto Pulse 전기영동 오버레이 (단계 전/후 비교)

### Revio Run Designer (Tools 메뉴)
- SMRT Cell 1~4개 설정 (Loading Conc, On-plate Conc, Movie Time)
- 어댑터 플레이트 96A — 샘플별 Well(A01~H12) 선택, bc 번호 자동 매핑
- 플레이트 바코드 서브필드 입력 (REF / LOT / SN / Exp) → 자동 조합
- 설계 JSON 저장 / 불러오기
- PacBio Revio v1 형식 CSV 내보내기

### 시퀀싱 QC 임포트 (Tools 메뉴 → Import Sequencing QC…)
- Revio QC HTML 리포트 파싱 (BeautifulSoup)
- Barcode → Library Prep index_no 역매핑으로 샘플 자동 매칭
- 미매칭 샘플은 콤보박스에서 수동 지정
- DB 저장 지표: Yield (Gb), Coverage (×), Read Length mean/N50 (kb), Read Quality (Q), Q30+ (%), P1 (%), Missing Adapter (%), Mean Passes, Control Reads

### 대시보드 (Dashboard 탭)
- 단계별 KPI 카드: 총 샘플 수 / QC Pass 수 / 라이브러리 완료 수 / 시퀀싱 완료 수
- 최근 업데이트 샘플 리스트 (좌) + Project별 현황 테이블 (우)

### 분석 탭 (Analysis 탭)
- **Chart 1**: QC 단계별 통과율 막대 차트 (Pass/Warning/Fail 스택)
- **Chart 2**: 단계별 회수율 라인 차트 (샘플별 컬러, 범례 적응형)
- **Chart 3**: GQN 분포 히스토그램 (상태별 그룹)
- **Chart 4**: 라이브러리 배치별 몰라리티 막대 차트
- 프로젝트 / 날짜 범위 필터 적용

---

## 데이터베이스 스키마

### `samples`
| 컬럼 | 설명 |
|------|------|
| `sample_id` (PK) | 샘플 고유 ID |
| `project_id` | 소속 프로젝트 |
| `sample_type` | WGS / mRNA-seq |
| `species`, `material` | 종, 재료 |
| `origin_sample_id` | Branch 원본 샘플 ID |
| `branch_type` | Re-extraction / Aliquot / Other |

### `qc_metrics`
| 컬럼 | 설명 |
|------|------|
| `step` | Extraction / Library Prep / … |
| `concentration` | ng/µl (Qubit) |
| `purity_260_280`, `purity_260_230` | NanoDrop 순도 |
| `gqn_rin` | GQN (DNA) / RIN (RNA) |
| `avg_size`, `peak_size` | bp (Femto Pulse) |
| `molarity_nm` | 자동 계산 몰라리티 |
| `index_no` | Library Prep Well (예: D08) |
| `status` | Pass / Warning / Fail |

### `sequencing_results`
| 컬럼 | 설명 |
|------|------|
| `run_id`, `smrt_cell`, `barcode_id` | 런 식별 정보 |
| `hifi_yield_gb`, `coverage_x` | 수율, 커버리지 |
| `read_length_n50_kb`, `read_length_mean_kb` | 리드 길이 |
| `read_quality_q`, `q30_pct` | 품질 지표 |
| `zmw_p1_pct`, `missing_adapter_pct` | ZMW 효율 |
| `status` | Pass / Warning / Fail |

---

## QC 판정 기준

### DNA Extraction (WGS)
- **Pass**: GQN ≥ 7.0, 260/280 ≥ 1.8
- **Warning**: GQN 5.0–7.0 또는 260/280 1.7–1.8
- **Fail**: GQN < 5.0

### RNA Extraction (mRNA-seq)
- **Pass**: RIN ≥ 8.0
- **Warning**: RIN 6.0–8.0
- **Fail**: RIN < 6.0

---

## 기술 스택

| 영역 | 라이브러리 |
|------|-----------|
| GUI | PyQt5 ≥ 5.15 |
| Database | SQLite + SQLAlchemy ≥ 2.0 |
| Data | pandas, numpy, openpyxl |
| Visualization | Matplotlib (Malgun Gothic 폰트, 한글 지원) |
| HTML 파싱 | beautifulsoup4 |
| 날짜 처리 | python-dateutil |

---

## 설치

### Conda (권장)
```bash
conda env create -f environment.yml
conda activate ngs-sample-qc-lims
python main.py
```

### pip venv
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## 프로젝트 구조

```
ngs-sample-qc-lims/
├── main.py                        # 진입점
├── requirements.txt
├── config/
│   └── settings.py               # QC 기준값, 경로 등 설정
├── database/
│   ├── models.py                 # SQLAlchemy 모델 (Sample, QCMetric, SequencingResult, …)
│   ├── db_manager.py             # DB 초기화, 마이그레이션, CRUD
│   └── __init__.py
├── parsers/
│   ├── nanodrop_parser.py        # NanoDrop CSV
│   ├── qubit_parser.py           # Qubit CSV
│   ├── femtopulse_parser.py      # Femto Pulse XML/ZIP
│   ├── revio_csv.py              # Revio Run Design CSV 생성 + bc_for_well()
│   └── revio_qc_parser.py        # Revio QC HTML 리포트 파싱
├── analysis/
│   └── qc_judge.py               # QC 자동 판정 로직
├── ui/
│   ├── main_window.py            # 메인 윈도우, 탭, Tools 메뉴
│   ├── dashboard_tab.py          # 대시보드 KPI + 프로젝트 현황
│   ├── sample_tab.py             # 샘플 목록, QC 상세, 시퀀싱 결과
│   ├── analysis_tab.py           # 분석 차트 4종
│   ├── revio_dialog.py           # Revio Run Designer
│   ├── sequencing_result_dialog.py  # Sequencing QC 임포트
│   └── dialogs.py                # 샘플 등록/편집, FemtoPulse 업로드 등
└── data/                         # SQLite DB 파일 저장 위치
```
