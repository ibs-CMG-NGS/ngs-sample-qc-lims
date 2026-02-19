"""
Femto Pulse 데이터 파서
Femto Pulse의 CSV/XML 출력 파일에서 GQN, Peak Size, Sizing 데이터 추출
"""
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FemtoPulseParser:
    """Femto Pulse 데이터 파싱 클래스"""
    
    def __init__(self):
        self.supported_formats = ['.csv', '.xml']
    
    def parse_file(self, file_path: str) -> List[Dict]:
        """
        Femto Pulse 파일 파싱
        
        Args:
            file_path: Femto Pulse 결과 파일 경로
            
        Returns:
            측정 데이터 리스트 (각 샘플별 딕셔너리)
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")
        
        try:
            if file_path.suffix.lower() == '.csv':
                results = self._parse_csv(file_path)
            else:
                results = self._parse_xml(file_path)
            
            logger.info(f"Parsed {len(results)} samples from {file_path.name}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse Femto Pulse file: {e}")
            raise
    
    def _parse_csv(self, file_path: Path) -> List[Dict]:
        """CSV 형식 파싱"""
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
        except:
            df = pd.read_csv(file_path, encoding='latin-1')
        
        # 컬럼명 정규화
        df.columns = df.columns.str.strip().str.lower()
        
        results = []
        column_mapping = self._detect_csv_columns(df)
        
        for idx, row in df.iterrows():
            try:
                data = {
                    'sample_id': self._get_value(row, column_mapping.get('sample_name')),
                    'gqn_rin': self._get_float_value(row, column_mapping.get('gqn')),
                    'concentration': self._get_float_value(row, column_mapping.get('concentration')),
                    'avg_size': self._get_float_value(row, column_mapping.get('avg_size')),
                    'peak_size': self._get_float_value(row, column_mapping.get('peak_size')),
                    'instrument': 'Femto Pulse',
                    'data_file': str(file_path)
                }
                
                # 유효한 데이터만 추가
                if data['sample_id']:
                    results.append(data)
                    
            except Exception as e:
                logger.warning(f"Skip row {idx}: {e}")
                continue
        
        return results
    
    def _parse_xml(self, file_path: Path) -> List[Dict]:
        """XML 형식 파싱 (상세 trace 데이터 포함)"""
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        results = []
        
        # XML 구조는 기기 설정에 따라 다를 수 있음
        # 일반적인 구조: <Samples><Sample>...</Sample></Samples>
        for sample in root.findall('.//Sample'):
            try:
                data = {
                    'sample_id': sample.findtext('Name', '').strip(),
                    'gqn_rin': self._parse_xml_float(sample.findtext('GQN')),
                    'concentration': self._parse_xml_float(sample.findtext('Concentration')),
                    'avg_size': self._parse_xml_float(sample.findtext('AverageSize')),
                    'peak_size': self._parse_xml_float(sample.findtext('PeakSize')),
                    'instrument': 'Femto Pulse',
                    'data_file': str(file_path)
                }
                
                # Trace 데이터 추출 (선택적)
                trace_data = self._extract_trace_data(sample)
                if trace_data:
                    data['trace_data'] = trace_data
                
                if data['sample_id']:
                    results.append(data)
                    
            except Exception as e:
                logger.warning(f"Skip XML sample: {e}")
                continue
        
        return results
    
    def _detect_csv_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """CSV 컬럼명 자동 감지"""
        mapping = {}
        
        # 샘플명
        sample_keywords = ['sample name', 'sample_name', 'name', 'well']
        for col in df.columns:
            if any(keyword in col for keyword in sample_keywords):
                mapping['sample_name'] = col
                break
        
        # GQN (Genomic Quality Number)
        gqn_keywords = ['gqn', 'quality number', 'rin']
        for col in df.columns:
            if any(keyword in col for keyword in gqn_keywords):
                mapping['gqn'] = col
                break
        
        # 농도
        conc_keywords = ['concentration', 'conc', 'ng/ul', 'ng/µl']
        for col in df.columns:
            if any(keyword in col for keyword in conc_keywords):
                mapping['concentration'] = col
                break
        
        # Average Size
        avg_keywords = ['average size', 'avg size', 'mean size']
        for col in df.columns:
            if any(keyword in col for keyword in avg_keywords):
                mapping['avg_size'] = col
                break
        
        # Peak Size
        peak_keywords = ['peak size', 'modal size']
        for col in df.columns:
            if any(keyword in col for keyword in peak_keywords):
                mapping['peak_size'] = col
                break
        
        return mapping
    
    def _extract_trace_data(self, sample_element) -> Optional[Dict]:
        """XML에서 trace 데이터 추출 (sizing curve)"""
        try:
            trace = sample_element.find('.//Trace')
            if trace is None:
                return None
            
            # Time/Size와 Intensity 데이터
            time_data = trace.findtext('TimeData', '')
            intensity_data = trace.findtext('IntensityData', '')
            
            if time_data and intensity_data:
                times = [float(x) for x in time_data.split(',') if x.strip()]
                intensities = [float(x) for x in intensity_data.split(',') if x.strip()]
                
                return {
                    'time': times,
                    'intensity': intensities
                }
        except Exception as e:
            logger.warning(f"Failed to extract trace data: {e}")
        
        return None
    
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
    
    def _parse_xml_float(self, value: Optional[str]) -> Optional[float]:
        """XML 텍스트를 float로 변환"""
        if value is None:
            return None
        try:
            return float(value.strip())
        except (ValueError, TypeError):
            return None
    
    def extract_sizing_curve(self, file_path: str, sample_id: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        특정 샘플의 sizing curve 데이터 추출
        
        Args:
            file_path: Femto Pulse 파일 경로
            sample_id: 샘플 ID
            
        Returns:
            (size_array, intensity_array) 또는 None
        """
        file_path = Path(file_path)
        
        if file_path.suffix.lower() == '.xml':
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            for sample in root.findall('.//Sample'):
                name = sample.findtext('Name', '').strip()
                if name == sample_id:
                    trace_data = self._extract_trace_data(sample)
                    if trace_data:
                        return (
                            np.array(trace_data['time']),
                            np.array(trace_data['intensity'])
                        )
        
        return None


# 편의 함수
def parse_femtopulse_file(file_path: str) -> List[Dict]:
    """Femto Pulse 파일 파싱 헬퍼 함수"""
    parser = FemtoPulseParser()
    return parser.parse_file(file_path)


def get_sizing_curve(file_path: str, sample_id: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Sizing curve 추출 헬퍼 함수"""
    parser = FemtoPulseParser()
    return parser.extract_sizing_curve(file_path, sample_id)
