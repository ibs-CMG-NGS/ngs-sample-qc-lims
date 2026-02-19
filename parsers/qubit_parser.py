"""
Qubit 데이터 파서
Qubit의 CSV/Excel 출력 파일에서 농도 정보 추출
"""
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class QubitParser:
    """Qubit 데이터 파싱 클래스"""
    
    def __init__(self):
        self.supported_formats = ['.csv', '.xlsx', '.xls']
    
    def parse_file(self, file_path: str) -> List[Dict]:
        """
        Qubit 파일 파싱
        
        Args:
            file_path: Qubit 결과 파일 경로
            
        Returns:
            측정 데이터 리스트 (각 샘플별 딕셔너리)
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        try:
            # 파일 형식에 따라 읽기
            df = self._read_file(file_path)
            
            # 데이터 추출
            results = self._extract_data(df, file_path)
            
            logger.info(f"Parsed {len(results)} samples from {file_path.name}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse Qubit file: {e}")
            raise
    
    def _read_file(self, file_path: Path) -> pd.DataFrame:
        """파일 읽기"""
        if file_path.suffix.lower() == '.csv':
            # CSV 파일
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
            except:
                df = pd.read_csv(file_path, encoding='latin-1')
        else:
            # Excel 파일
            df = pd.read_excel(file_path, engine='openpyxl')
        
        return df
    
    def _extract_data(self, df: pd.DataFrame, file_path: Path) -> List[Dict]:
        """
        DataFrame에서 측정 데이터 추출
        
        Qubit 표준 출력 형식:
        - Sample Name / Test Name
        - Original sample conc. (ng/µl)
        - Qubit tube conc. (ng/µl)
        - Units
        """
        results = []
        
        # 컬럼명 정규화
        df.columns = df.columns.str.strip().str.lower()
        
        # 필수 컬럼 매핑
        column_mapping = self._detect_columns(df)
        
        if not column_mapping:
            raise ValueError("Cannot detect standard Qubit columns")
        
        for idx, row in df.iterrows():
            try:
                # Qubit는 보통 Original sample conc. 사용
                concentration = self._get_float_value(row, column_mapping.get('concentration'))
                
                # 없으면 Qubit tube conc. 사용
                if concentration is None:
                    concentration = self._get_float_value(row, column_mapping.get('tube_conc'))
                
                data = {
                    'sample_id': self._get_value(row, column_mapping.get('sample_name')),
                    'concentration': concentration,
                    'assay_type': self._get_value(row, column_mapping.get('test_name')),
                    'instrument': 'Qubit',
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
        
        # 샘플명 컬럼
        sample_keywords = ['sample name', 'sample_name', 'samplename', 'name']
        for col in df.columns:
            if any(keyword in col for keyword in sample_keywords):
                mapping['sample_name'] = col
                break
        
        # Test Name 컬럼 (dsDNA, RNA 등)
        test_keywords = ['test name', 'test_name', 'assay', 'kit']
        for col in df.columns:
            if any(keyword in col for keyword in test_keywords):
                mapping['test_name'] = col
                break
        
        # Original sample concentration
        conc_keywords = ['original sample conc', 'original conc', 'sample conc']
        for col in df.columns:
            if any(keyword in col for keyword in conc_keywords):
                mapping['concentration'] = col
                break
        
        # Qubit tube concentration (fallback)
        tube_keywords = ['qubit tube conc', 'tube conc']
        for col in df.columns:
            if any(keyword in col for keyword in tube_keywords):
                mapping['tube_conc'] = col
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
def parse_qubit_file(file_path: str) -> List[Dict]:
    """Qubit 파일 파싱 헬퍼 함수"""
    parser = QubitParser()
    return parser.parse_file(file_path)
