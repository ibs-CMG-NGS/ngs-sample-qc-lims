"""
PacBio Revio 시퀀싱 QC HTML 리포트 파서

HTML 리포트 구조:
  <table class="qc-table"> 첫 번째 테이블 = QC Metrics Summary Table
  헤더: Sample, Run, Well, Barcode, Overall, HiFi Reads (M), HiFi Yield (Gb),
         Est. Coverage, Read Length mean (kb), Read Length N50 (kb),
         Read Quality (median), Q30+ Bases (%), P1 (%), Missing Adapter (%),
         Mean Passes, Control Reads, Control RL mean (kb)
"""
import re
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def _clean(text: str) -> str:
    """셀 텍스트에서 뱃지(⚠️ WARNING, ✅ PASS) 및 단위 suffix 제거 → 숫자 문자열."""
    # 유니코드 배지·이모지 제거
    text = re.sub(r'[⚠️✅❌]+', '', text)
    # PASS / WARNING / FAIL 텍스트 제거
    text = re.sub(r'\b(PASS|WARNING|FAIL)\b', '', text, flags=re.IGNORECASE)
    # 단위 제거: ×, %, kb, Gb, M, Q 접두사
    text = text.strip()
    # "Q31" → "31", "31.5×" → "31.5", "92.4%" → "92.4"
    text = re.sub(r'^Q(\d)', r'\1', text)       # Q31 → 31
    text = text.rstrip('×%')                    # trailing × or %
    return text.strip()


def _to_float(text: str):
    try:
        return float(_clean(text))
    except (ValueError, TypeError):
        return None


def _to_int(text: str):
    try:
        return int(float(_clean(text)))
    except (ValueError, TypeError):
        return None


def _status(text: str) -> str:
    """Overall 셀 → 'Pass' / 'Warning' / 'Fail'."""
    t = text.upper()
    if 'PASS' in t:
        return 'Pass'
    if 'WARNING' in t or '⚠' in t:
        return 'Warning'
    if 'FAIL' in t:
        return 'Fail'
    return 'No Data'


def parse_revio_qc_report(html_path: str) -> list[dict]:
    """
    HTML 리포트 파싱 → 샘플별 dict 리스트 반환.

    반환 dict 키:
        sample_name, run_id, smrt_cell, barcode_id, status,
        hifi_reads_m, hifi_yield_gb, coverage_x,
        read_length_mean_kb, read_length_n50_kb,
        read_quality_q, q30_pct, zmw_p1_pct,
        missing_adapter_pct, mean_passes,
        control_reads, control_rl_mean_kb
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("beautifulsoup4가 설치되어 있지 않습니다. pip install beautifulsoup4")

    path = Path(html_path)
    if not path.exists():
        raise FileNotFoundError(f"HTML 리포트를 찾을 수 없습니다: {html_path}")

    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = path.read_text(encoding='latin-1')

    soup = BeautifulSoup(text, 'html.parser')

    # 첫 번째 qc-table = QC Metrics Summary Table
    table = soup.find('table', class_='qc-table')
    if table is None:
        raise ValueError("HTML에서 QC 테이블(class='qc-table')을 찾을 수 없습니다.")

    thead = table.find('thead')
    tbody = table.find('tbody')
    if not thead or not tbody:
        raise ValueError("QC 테이블에 thead/tbody가 없습니다.")

    raw_headers = [th.get_text(separator=' ', strip=True) for th in thead.find_all('th')]
    logger.debug(f"QC table headers: {raw_headers}")

    # 헤더 인덱스 매핑 (부분 문자열 매칭)
    def _idx(keyword: str) -> int:
        for i, h in enumerate(raw_headers):
            if keyword.lower() in h.lower():
                return i
        return -1

    col = {
        'sample':      _idx('Sample'),
        'run':         _idx('Run'),
        'well':        _idx('Well'),
        'barcode':     _idx('Barcode'),
        'overall':     _idx('Overall'),
        'reads':       _idx('HiFi Reads'),
        'yield':       _idx('HiFi Yield'),
        'coverage':    _idx('Coverage'),
        'rl_mean':     _idx('mean'),
        'rl_n50':      _idx('N50'),
        'quality':     _idx('Quality'),
        'q30':         _idx('Q30'),
        'p1':          _idx('P1'),
        'missing':     _idx('Missing'),
        'passes':      _idx('Passes'),
        'ctrl_reads':  _idx('Control Reads'),
        'ctrl_rl':     _idx('Control RL'),
    }

    results = []
    for tr in tbody.find_all('tr'):
        cells = tr.find_all('td')
        if not cells:
            continue

        def _cell(key: str) -> str:
            idx = col.get(key, -1)
            if idx < 0 or idx >= len(cells):
                return ''
            return cells[idx].get_text(separator=' ', strip=True)

        record = {
            'sample_name':          _cell('sample'),
            'run_id':               _cell('run'),
            'smrt_cell':            _cell('well'),
            'barcode_id':           _cell('barcode'),
            'status':               _status(_cell('overall')),
            'hifi_reads_m':         _to_float(_cell('reads')),
            'hifi_yield_gb':        _to_float(_cell('yield')),
            'coverage_x':           _to_float(_cell('coverage')),
            'read_length_mean_kb':  _to_float(_cell('rl_mean')),
            'read_length_n50_kb':   _to_float(_cell('rl_n50')),
            'read_quality_q':       _to_float(_cell('quality')),
            'q30_pct':              _to_float(_cell('q30')),
            'zmw_p1_pct':           _to_float(_cell('p1')),
            'missing_adapter_pct':  _to_float(_cell('missing')),
            'mean_passes':          _to_float(_cell('passes')),
            'control_reads':        _to_int(_cell('ctrl_reads')),
            'control_rl_mean_kb':   _to_float(_cell('ctrl_rl')),
        }
        results.append(record)
        logger.debug(f"Parsed: {record['barcode_id']} / {record['sample_name']} → {record['status']}")

    if not results:
        raise ValueError("QC 테이블에서 샘플 데이터를 추출하지 못했습니다.")

    logger.info(f"Revio QC report parsed: {len(results)} samples from {path.name}")
    return results
