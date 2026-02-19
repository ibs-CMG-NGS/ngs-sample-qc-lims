# NGS Sample QC LIMS

Laboratory Information Management System for NGS Sample Quality Control

## 프로젝트 개요

Femto Pulse, NanoDrop, Qubit 등의 QC 장비 데이터를 통합하여 NGS 샘플의 품질을 관리하는 시스템입니다.

## 주요 기능

- 📊 다중 QC 장비 데이터 자동 파싱 (NanoDrop, Qubit, Femto Pulse)
- 🧬 WGS/mRNA-seq 워크플로우별 샘플 관리
- ✅ 자동 QC 판정 (Pass/Warning/Fail)
- 📈 단계별 Progress Chart 시각화
- 🧮 Molarity 자동 계산
- 💾 SQLite 기반 데이터베이스 관리

## 빠른 시작

### 1. 환경 설정

```powershell
# Conda 환경 생성
conda env create -f environment.yml

# 환경 활성화
conda activate ngs-sample-qc-lims
```

### 2. 실행

```powershell
# GUI 실행
.\run.ps1

# 또는 수동 실행
conda run -n ngs-sample-qc-lims python main.py
```

### 3. 테스트

```powershell
# 테스트 실행
.\test.ps1
```

## 기술 스택

- Python 3.11
- PyQt5 (GUI)
- SQLAlchemy + SQLite (Database)
- pandas, matplotlib, plotly (Data Processing & Visualization)

## 문서

- [QUICKSTART.md](QUICKSTART.md) - 빠른 시작 가이드
- [CONDA_GUIDE.md](CONDA_GUIDE.md) - Conda 환경 관리
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 문제 해결

## 라이센스

MIT License

## 버전

v1.0.0 - 초기 릴리스 (2026-01-26)
