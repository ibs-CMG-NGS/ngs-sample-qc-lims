# Conda 환경 관리 가이드

## 환경 생성 및 활성화

```powershell
# 1. 환경 생성 (최초 1회만)
conda env create -f environment.yml

# 2. 환경 활성화
conda activate ngs-sample-qc-lims

# 3. 설치된 패키지 확인
conda list
```

## 환경 업데이트

```powershell
# environment.yml 파일 수정 후
conda env update -f environment.yml --prune
```

## 환경 삭제

```powershell
# 환경 비활성화
conda deactivate

# 환경 삭제
conda env remove -n ngs-sample-qc-lims
```

## 환경 내보내기

```powershell
# 현재 환경의 정확한 패키지 버전 내보내기
conda env export > environment_locked.yml

# 또는 pip freeze 형식으로
pip freeze > requirements_locked.txt
```

## 환경 복제

```powershell
# 다른 머신에서 동일한 환경 재현
conda env create -f environment.yml
```

## 유용한 명령어

```powershell
# 모든 conda 환경 목록 보기
conda env list

# 현재 환경 정보
conda info

# 특정 패키지 검색
conda search <package_name>

# 패키지 추가 설치
conda install <package_name>
# 또는
pip install <package_name>

# 패키지 업데이트
conda update <package_name>

# 환경 변경사항 확인
conda list --revisions
```

## 프로젝트 실행

```powershell
# 1. 환경 활성화 확인
conda activate ngs-sample-qc-lims

# 2. 프로젝트 디렉토리로 이동
cd C:\Users\USER\Documents\GitHub\ngs-sample-qc-lims

# 3. 프로그램 실행
python main.py

# 또는 테스트 실행
python tests\test_basic.py
```

## 문제 해결

### PyQt6 import 오류
```powershell
pip install --upgrade PyQt6
```

### 환경 손상 시
```powershell
conda env remove -n ngs-sample-qc-lims
conda env create -f environment.yml
```

### 특정 패키지만 재설치
```powershell
pip install --force-reinstall <package_name>
```
