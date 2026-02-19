"""
NanoDrop 데이터 파서
NanoDrop의 CSV/TXT 출력 파일에서 농도 및 순도 정보 추출
"""
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class NanoDropParser:
    """NanoDrop 데이터 파싱 클래스"""
    
    def __init__(self):
        self.supported_formats = ['.csv', '.txt', '.tsv']
    
    def parse_file(self, file_path: str) -> List[Dict]:
        """
        NanoDrop 파일 파싱
        
        Args:
            file_path: NanoDrop 결과 파일 경로
            
        Returns:
            측정 데이터 리스트 (각 샘플별 딕셔너리)
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        try:
            # NanoDrop은 보통 탭 구분 또는 CSV
            # 파일 형식에 따라 구분자 자동 감지
            df = self._read_file(file_path)
            
            # 데이터 추출
            results = self._extract_data(df, file_path)
            
            logger.info(f"Parsed {len(results)} samples from {file_path.name}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse NanoDrop file: {e}")
            raise
    
    def _read_file(self, file_path: Path) -> pd.DataFrame:
        """파일 읽기 (구분자 자동 감지)"""
        try:
            # CSV 형식 시도
            df = pd.read_csv(file_path, encoding='utf-8')
            if len(df.columns) == 1:
                # 탭 구분 시도
                df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
        except:
            # Latin-1 인코딩 시도
            try:
                df = pd.read_csv(file_path, encoding='latin-1')
                if len(df.columns) == 1:
                    df = pd.read_csv(file_path, sep='\t', encoding='latin-1')
            except Exception as e:
                raise ValueError(f"Cannot read file with standard encodings: {e}")
        
        return df
    
    def _extract_data(self, df: pd.DataFrame, file_path: Path) -> List[Dict]:
        """
        DataFrame에서 측정 데이터 추출
        
        NanoDrop 표준 출력 형식:
        - Sample ID / Sample Name
        - Nucleic Acid Conc. (ng/µl)
        - A260/A280
        - A260/A230
        """
        results = []
        
        # 컬럼명 정규화 (대소문자, 공백 무시)
        df.columns = df.columns.str.strip().str.lower()
        
        # 필수 컬럼 매핑
        column_mapping = self._detect_columns(df)
        
        if not column_mapping:
            raise ValueError("Cannot detect standard NanoDrop columns")
        
        for idx, row in df.iterrows():
            try:
                data = {
                    'sample_id': self._get_value(row, column_mapping.get('sample_id')),
                    'concentration': self._get_float_value(row, column_mapping.get('concentration')),
                    'purity_260_280': self._get_float_value(row, column_mapping.get('260_280')),
                    'purity_260_230': self._get_float_value(row, column_mapping.get('260_230')),
                    'instrument': 'NanoDrop',
                    'data_file': str(file_path)
                }
                
                # 유효한 데이터만 추가
                if data['sample_id'] and data['concentration']:
                    results.append(data)
                    
            except Exception as e:
                logger.warning(f"Skip row {idx}: {e}")
                continue
        
        return results
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """컬럼명 자동 감지"""
        mapping = {}
        
        # 샘플 ID 컬럼
        sample_id_keywords = ['sample id', 'sample_id', 'sampleid', 'id', 'sample name', 'name']
        for col in df.columns:
            if any(keyword in col for keyword in sample_id_keywords):
                mapping['sample_id'] = col
                break
        
        # 농도 컬럼
        conc_keywords = ['nucleic acid', 'concentration', 'conc', 'ng/ul', 'ng/µl']
        for col in df.columns:
            if any(keyword in col for keyword in conc_keywords):
                mapping['concentration'] = col
                break
        
        # 260/280 컬럼
        for col in df.columns:
            if '260/280' in col or '260_280' in col:
                mapping['260_280'] = col
                break
        
        # 260/230 컬럼
        for col in df.columns:
            if '260/230' in col or '260_230' in col:
                mapping['260_230'] = col
                break
        
        return mapping
    
    def _get_value(self, row: pd.Series, column: Optional[str]) -> Optional[str]:
        """행에서 값 추출 (문자열)"""
        if column is None or column not in row.index:
            return None
        value = row[column]
        return str(value).strip() if pd.notna(value) else None
    
    def _get_float_value(self, row: pd.Series, column: Optional[str]) -> Optional[float]:
        """행에서 값 추출 (실수)"""
        if column is None or column not in row.index:
            return None
        value = row[column]
        try:
            return float(value) if pd.notna(value) else None
        except (ValueError, TypeError):
            return None


# 편의 함수
def parse_nanodrop_file(file_path: str) -> List[Dict]:
    """NanoDrop 파일 파싱 헬퍼 함수"""
    parser = NanoDropParser()
    return parser.parse_file(file_path)
