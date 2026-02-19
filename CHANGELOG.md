# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### To Do
- [ ] 샘플 등록 다이얼로그 UI 구현
- [ ] 드래그 앤 드롭 파일 업로드 기능
- [ ] Dashboard 실시간 데이터 업데이트
- [ ] Femto Pulse 그래프 인터랙티브 오버레이
- [ ] PDF 리포트 자동 생성
- [ ] 배치별 통계 분석 기능

## [1.0.0] - 2026-01-26

### Added
- 초기 프로젝트 구조 설정
- NanoDrop 데이터 파서 구현
- Qubit 데이터 파서 구현
- Femto Pulse 데이터 파서 구현 (CSV/XML)
- SQLAlchemy 기반 데이터베이스 모델 (Samples, QC_Metrics, Raw_Traces)
- QC 자동 판정 시스템 (Pass/Warning/Fail)
- Molarity 계산기 (DNA/RNA)
- Progress Chart 시각화 (matplotlib)
- PyQt5 기반 메인 윈도우 GUI
- Conda 환경 관리 (environment.yml)
- 실행 스크립트 (run.ps1, test.ps1)
- 예제 데이터 파일 (NanoDrop, Qubit, Femto Pulse)
- 종합 테스트 스크립트

### Technical
- Python 3.11
- PyQt5 5.15.9 (Windows DLL 호환성)
- SQLAlchemy 2.0.25
- pandas 2.1.4
- matplotlib 3.8.2
- plotly 5.18.0

### Documentation
- README.md - 프로젝트 전체 문서
- QUICKSTART.md - 빠른 시작 가이드
- CONDA_GUIDE.md - Conda 환경 관리
- TROUBLESHOOTING.md - 문제 해결 가이드

### Fixed
- PyQt6 DLL 로드 오류 → PyQt5로 전환
- Conda 환경 PyQt 호환성 문제 해결
