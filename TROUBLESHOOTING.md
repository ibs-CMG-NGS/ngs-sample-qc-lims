# 문제 해결 가이드

## PyQt DLL 로드 오류

### 증상
```
ImportError: DLL load failed while importing QtCore
```

### 해결 방법

이 오류는 PyQt6의 Qt 라이브러리 DLL 버전 불일치로 발생합니다. 다음과 같이 해결했습니다:

1. **PyQt5로 전환** (권장)
   - PyQt5는 더 안정적이며 conda와 호환성이 좋습니다
   - 현재 프로젝트는 PyQt5를 사용하도록 설정되어 있습니다

2. **환경 재생성**
```powershell
# 기존 환경 제거
conda env remove -n ngs-sample-qc-lims -y

# 새 환경 생성
conda env create -f environment.yml
```

3. **프로그램 실행**
```powershell
# conda run 사용 (권장)
conda run -n ngs-sample-qc-lims python main.py

# 또는 실행 스크립트
.\run.ps1
```

## 데이터베이스 UNIQUE 제약조건 오류

### 증상
```
sqlite3.IntegrityError: UNIQUE constraint failed: samples.sample_id
```

### 해결 방법

테스트 실행 시 동일한 sample_id로 중복 삽입을 시도할 때 발생합니다.

```powershell
# 데이터베이스 파일 삭제 후 재실행
Remove-Item data\lims.db -ErrorAction SilentlyContinue
python tests\test_basic.py
```

## Conda 환경 활성화 문제

### 증상
PowerShell에서 `conda activate`가 작동하지 않음

### 해결 방법

1. **conda run 사용** (가장 안정적)
```powershell
conda run -n ngs-sample-qc-lims python main.py
```

2. **PowerShell conda 초기화**
```powershell
conda init powershell
# PowerShell 재시작 후
conda activate ngs-sample-qc-lims
```

3. **실행 스크립트 사용**
```powershell
.\run.ps1  # 자동으로 conda run 사용
```

## Import 오류

### 증상
```
ModuleNotFoundError: No module named 'PyQt5'
```

### 해결 방법

올바른 conda 환경에서 실행하고 있는지 확인:

```powershell
# 현재 환경 확인
conda info --envs

# 패키지 설치 확인
conda run -n ngs-sample-qc-lims pip list | Select-String "PyQt"

# 누락된 경우 재설치
conda env update -f environment.yml --prune
```

## 한글 깨짐 문제

### 증상
콘솔에서 한글이 깨져서 표시됨

### 해결 방법

이는 Windows PowerShell의 인코딩 문제입니다. 정상 작동에는 영향이 없지만, 해결하려면:

```powershell
# PowerShell 프로필에 추가
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 또는 실행 시 적용
$OutputEncoding = [System.Text.Encoding]::UTF8
conda run -n ngs-sample-qc-lims python main.py
```

## matplotlib 한글 폰트 문제

### 증상
그래프에서 한글이 □□□로 표시됨

### 해결 방법

`analysis/visualizer.py`에서 이미 "맑은 고딕" 폰트를 설정했습니다. 
다른 폰트를 사용하려면:

```python
plt.rcParams['font.family'] = '원하는 폰트명'
```

## 일반적인 문제 해결 순서

1. **환경 확인**
```powershell
conda env list
conda list -n ngs-sample-qc-lims
```

2. **환경 재생성**
```powershell
conda env remove -n ngs-sample-qc-lims -y
conda env create -f environment.yml
```

3. **데이터베이스 초기화**
```powershell
Remove-Item data\lims.db -ErrorAction SilentlyContinue
```

4. **테스트 실행**
```powershell
.\test.ps1
```

5. **프로그램 실행**
```powershell
.\run.ps1
```
