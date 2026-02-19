# Contributing to NGS Sample QC LIMS

프로젝트에 기여해 주셔서 감사합니다! 🎉

## 개발 환경 설정

1. **저장소 클론**
```bash
git clone https://github.com/yourusername/ngs-sample-qc-lims.git
cd ngs-sample-qc-lims
```

2. **Conda 환경 생성**
```bash
conda env create -f environment.yml
conda activate ngs-sample-qc-lims
```

3. **개발 브랜치 생성**
```bash
git checkout -b feature/your-feature-name
```

## 코드 스타일

- **Python**: PEP 8 준수
- **Docstrings**: Google Style 사용
- **Type Hints**: 가능한 곳에 타입 힌트 추가
- **주석**: 한글 또는 영어 (일관성 유지)

## 커밋 메시지 규칙

```
<type>: <subject>

<body (optional)>

<footer (optional)>
```

### Type
- `feat`: 새로운 기능
- `fix`: 버그 수정
- `docs`: 문서 수정
- `style`: 코드 포맷팅 (기능 변경 없음)
- `refactor`: 코드 리팩토링
- `test`: 테스트 추가/수정
- `chore`: 빌드, 설정 파일 수정

### 예시
```
feat: Add NanoDrop CSV parser

- Implement automatic column detection
- Support multiple file encodings
- Add unit tests

Closes #123
```

## Pull Request 프로세스

1. **기능 개발**
   - 새 브랜치에서 작업
   - 커밋 메시지 규칙 준수
   - 테스트 작성 및 실행

2. **테스트 실행**
```bash
python tests/test_basic.py
```

3. **PR 생성**
   - 명확한 제목과 설명
   - 변경 사항 요약
   - 관련 이슈 번호 명시

4. **코드 리뷰**
   - 리뷰 피드백 반영
   - 필요시 추가 커밋

## 디렉토리 구조

```
ngs-sample-qc-lims/
├── config/          # 설정 파일
├── database/        # DB 모델 및 관리
├── parsers/         # 데이터 파서
├── analysis/        # QC 분석 로직
├── ui/             # PyQt5 GUI
├── examples/        # 예제 데이터
└── tests/          # 테스트 코드
```

## 새로운 파서 추가

1. `parsers/` 디렉토리에 파일 생성
2. 기본 구조 따르기:

```python
class NewInstrumentParser:
    def parse_file(self, file_path: str) -> List[Dict]:
        """파일 파싱 메인 함수"""
        pass
```

3. `parsers/__init__.py`에 추가
4. 테스트 작성

## 버그 리포트

GitHub Issues에 다음 정보 포함:
- 문제 설명
- 재현 단계
- 기대 동작
- 실제 동작
- 환경 정보 (OS, Python 버전)
- 오류 메시지/스크린샷

## 질문 및 토론

- GitHub Discussions 사용
- 명확하고 구체적으로 작성
- 관련 코드/로그 첨부

## 라이센스

기여한 코드는 MIT 라이센스 하에 배포됩니다.
