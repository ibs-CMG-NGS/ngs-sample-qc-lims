"""
Femto Pulse 5-file parser + folder scanner

Femto Pulse generates 5 CSV files per run:
  - Quality Table: 1 row per sample, DQN / Total conc
  - Peak Table: block-repeat structure, per-peak details + TIC/DQN summary
  - Electropherogram: Size(bp) x sample RFU (~3000 rows)
  - Size Calibration: Ladder Size(bp) vs Time(sec), 2 columns
  - Smear Analysis: sample x range combinations, yield per size range

Filename pattern: YYYY MM DD HHH MMM {file type}.csv
Sample ID format: SampB1 (Samp + 96-well address); last sample is always ladder.
"""
import pandas as pd
import numpy as np
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_csv_safe(path: str, **kwargs) -> pd.DataFrame:
    """Read CSV with UTF-8 / Latin-1 fallback encoding."""
    try:
        return pd.read_csv(path, encoding='utf-8', **kwargs)
    except (UnicodeDecodeError, Exception):
        return pd.read_csv(path, encoding='latin-1', **kwargs)


def _is_ladder(sample_id: str, dqn=None, conc=None) -> bool:
    """Detect ladder sample: last well + DQN & conc both empty."""
    if sample_id is None:
        return True
    sid = str(sample_id).strip().lower()
    if 'ladder' in sid:
        return True
    # DQN and concentration both missing -> ladder
    dqn_empty = dqn is None or (isinstance(dqn, float) and np.isnan(dqn))
    conc_empty = conc is None or (isinstance(conc, float) and np.isnan(conc))
    if dqn_empty and conc_empty:
        return True
    return False


def _safe_float(val) -> Optional[float]:
    """Convert value to float, returning None on failure."""
    if val is None:
        return None
    if isinstance(val, float) and np.isnan(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _strip_samp_prefix(sample_id: str) -> str:
    """Remove 'Samp' prefix: SampB1 -> B1."""
    if sample_id and sample_id.startswith('Samp'):
        return sample_id[4:]
    return sample_id or ''


# ---------------------------------------------------------------------------
# File-type detection
# ---------------------------------------------------------------------------

_TYPE_KEYWORDS = {
    'quality_table': ['quality table', 'quality_table'],
    'peak_table': ['peak table', 'peak_table'],
    'electropherogram': ['electropherogram'],
    'size_calibration': ['size calibration', 'size_calibration'],
    'smear_analysis': ['smear analysis', 'smear_analysis'],
}


def detect_file_type(file_path: str) -> str:
    """Detect Femto Pulse file type from filename keywords.

    Returns one of: quality_table, peak_table, electropherogram,
    size_calibration, smear_analysis, unknown.
    """
    name = Path(file_path).stem.lower()
    for type_name, keywords in _TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return type_name
    return 'unknown'


# ---------------------------------------------------------------------------
# Folder scanner
# ---------------------------------------------------------------------------

def scan_femtopulse_folder(folder_path: str) -> Dict[str, Optional[str]]:
    """Scan a folder and return {type_name: file_path or None} for 5 file types."""
    folder = Path(folder_path)
    result = {t: None for t in _TYPE_KEYWORDS}

    if not folder.is_dir():
        return result

    for f in folder.iterdir():
        if f.suffix.lower() != '.csv':
            continue
        ftype = detect_file_type(str(f))
        if ftype != 'unknown':
            result[ftype] = str(f)

    return result


def parse_femtopulse_folder(folder_path: str) -> Dict:
    """Parse all Femto Pulse files in a folder at once.

    Returns:
        {
            'folder': str,
            'files': {type_name: file_path or None},
            'quality_table': [...] or None,
            'peak_table': [...] or None,
            'electropherogram': {...} or None,
            'size_calibration': [...] or None,
            'smear_analysis': [...] or None,
        }
    """
    files = scan_femtopulse_folder(folder_path)
    data: Dict = {
        'folder': str(folder_path),
        'files': files,
    }

    parsers = {
        'quality_table': parse_quality_table,
        'peak_table': parse_peak_table,
        'electropherogram': parse_electropherogram,
        'size_calibration': parse_size_calibration,
        'smear_analysis': parse_smear_analysis,
    }

    for type_name, parser_fn in parsers.items():
        path = files.get(type_name)
        if path:
            try:
                data[type_name] = parser_fn(path)
            except Exception as e:
                logger.error(f"Failed to parse {type_name} ({path}): {e}")
                data[type_name] = None
        else:
            data[type_name] = None

    return data


# ---------------------------------------------------------------------------
# 1. Quality Table parser
# ---------------------------------------------------------------------------

def parse_quality_table(path: str) -> List[Dict]:
    """Parse Quality Table CSV.

    Returns list of dicts: {well, sample_id, dqn, threshold, total_concentration}
    Ladder rows are excluded.
    """
    df = _read_csv_safe(path)
    df.columns = df.columns.str.strip()

    # Auto-detect columns (case-insensitive matching)
    col_map = _detect_columns(df, {
        'well': ['well'],
        'sample_id': ['sample name', 'sample_name', 'sample id', 'name'],
        'dqn': ['dqn', 'gqn', 'quality number'],
        'threshold': ['threshold', 'quality threshold'],
        'total_concentration': ['total concentration', 'total conc', 'concentration', 'conc', 'ng/ul', 'ng/µl'],
    })

    results = []
    for _, row in df.iterrows():
        sid = _get_str(row, col_map.get('sample_id')) or _get_str(row, col_map.get('well'))
        dqn = _get_float(row, col_map.get('dqn'))
        conc = _get_float(row, col_map.get('total_concentration'))

        if _is_ladder(sid, dqn, conc):
            continue

        results.append({
            'well': _get_str(row, col_map.get('well')) or '',
            'sample_id': sid or '',
            'dqn': dqn,
            'threshold': _get_str(row, col_map.get('threshold')),
            'total_concentration': conc,
        })

    logger.info(f"Quality Table: {len(results)} samples from {Path(path).name}")
    return results


# ---------------------------------------------------------------------------
# 2. Peak Table parser
# ---------------------------------------------------------------------------

def parse_peak_table(path: str) -> List[Dict]:
    """Parse Peak Table CSV (block-repeat structure).

    Returns list of dicts:
        {well, sample_id, peaks: [{...}], tic, tim, total_conc, dqn}
    """
    df = _read_csv_safe(path)
    df.columns = df.columns.str.strip()

    col_map = _detect_columns(df, {
        'well': ['well'],
        'sample_id': ['sample name', 'sample_name', 'sample id', 'name'],
        'peak_id': ['peak id', 'peak', '#'],
        'size': ['size [bp]', 'size(bp)', 'size'],
        'pct_total': ['% (conc.)', '% total', 'pct total', '% conc'],
        'conc': ['nmole/l', 'nmole/l', 'ng/ul', 'ng/µl', 'conc'],
        'rfu': ['rfu', 'height', 'intensity'],
        'tic': ['total integrated conc.', 'tic', 'total integrated'],
        'tim': ['total integrated molarity', 'tim'],
        'total_conc': ['total conc.', 'total concentration'],
        'dqn': ['dqn', 'gqn', 'quality number'],
    })

    # Group by well/sample block
    well_col = col_map.get('well')
    sid_col = col_map.get('sample_id')

    results = []
    current_sample = None
    current_peaks = []

    for _, row in df.iterrows():
        well = _get_str(row, well_col) or ''
        sid = _get_str(row, sid_col) or well

        # New sample block
        if sid and sid != (current_sample or {}).get('sample_id'):
            if current_sample is not None:
                current_sample['peaks'] = current_peaks
                dqn_val = current_sample.get('_dqn')
                conc_val = current_sample.get('_conc')
                if not _is_ladder(current_sample['sample_id'], dqn_val, conc_val):
                    results.append(current_sample)
            current_sample = {
                'well': well,
                'sample_id': sid,
                'tic': _get_float(row, col_map.get('tic')),
                'tim': _get_float(row, col_map.get('tim')),
                'total_conc': _get_float(row, col_map.get('total_conc')),
                'dqn': _get_float(row, col_map.get('dqn')),
                '_dqn': _get_float(row, col_map.get('dqn')),
                '_conc': _get_float(row, col_map.get('total_conc')),
            }
            current_peaks = []

        peak_data = {
            'size': _get_float(row, col_map.get('size')),
            'pct_total': _get_float(row, col_map.get('pct_total')),
            'conc': _get_float(row, col_map.get('conc')),
            'rfu': _get_float(row, col_map.get('rfu')),
        }
        current_peaks.append(peak_data)

        # Update summary fields from any row that has them
        if current_sample:
            for field in ('tic', 'tim', 'total_conc', 'dqn'):
                val = _get_float(row, col_map.get(field))
                if val is not None:
                    current_sample[field] = val
                    if field in ('dqn',):
                        current_sample['_dqn'] = val
                    if field in ('total_conc',):
                        current_sample['_conc'] = val

    # Flush last sample
    if current_sample is not None:
        current_sample['peaks'] = current_peaks
        dqn_val = current_sample.get('_dqn')
        conc_val = current_sample.get('_conc')
        if not _is_ladder(current_sample['sample_id'], dqn_val, conc_val):
            results.append(current_sample)

    # Clean up internal keys
    for r in results:
        r.pop('_dqn', None)
        r.pop('_conc', None)

    logger.info(f"Peak Table: {len(results)} samples from {Path(path).name}")
    return results


# ---------------------------------------------------------------------------
# 3. Electropherogram parser
# ---------------------------------------------------------------------------

def parse_electropherogram(path: str) -> Dict:
    """Parse Electropherogram CSV.

    Returns:
        {
            'size_bp': ndarray,
            'samples': {column_name: ndarray of RFU values},
        }
    Includes all columns (including ladder).
    """
    df = _read_csv_safe(path)
    df.columns = df.columns.str.strip()

    # First column is typically Size [bp] or similar
    size_col = df.columns[0]
    size_bp = pd.to_numeric(df[size_col], errors='coerce').values

    samples = {}
    for col in df.columns[1:]:
        samples[col] = pd.to_numeric(df[col], errors='coerce').values

    logger.info(f"Electropherogram: {len(samples)} channels, {len(size_bp)} points from {Path(path).name}")
    return {
        'size_bp': size_bp,
        'samples': samples,
    }


# ---------------------------------------------------------------------------
# 4. Size Calibration parser
# ---------------------------------------------------------------------------

def parse_size_calibration(path: str) -> List[Dict]:
    """Parse Size Calibration CSV (2-column: Ladder Size(bp) vs Time(sec)).

    Returns list of dicts: {ladder_size_bp, time_sec}
    """
    df = _read_csv_safe(path)
    df.columns = df.columns.str.strip()

    results = []
    cols = df.columns.tolist()
    size_col = cols[0] if len(cols) > 0 else None
    time_col = cols[1] if len(cols) > 1 else None

    for _, row in df.iterrows():
        results.append({
            'ladder_size_bp': _safe_float(row[size_col]) if size_col else None,
            'time_sec': _safe_float(row[time_col]) if time_col else None,
        })

    logger.info(f"Size Calibration: {len(results)} points from {Path(path).name}")
    return results


# ---------------------------------------------------------------------------
# 5. Smear Analysis parser
# ---------------------------------------------------------------------------

def parse_smear_analysis(path: str) -> List[Dict]:
    """Parse Smear Analysis CSV.

    Returns list of dicts:
        {well, sample_id, range, pg_ul, pct_total, pmol_l, avg_size, cv, threshold, dqn}
    """
    df = _read_csv_safe(path)
    df.columns = df.columns.str.strip()

    col_map = _detect_columns(df, {
        'well': ['well'],
        'sample_id': ['sample name', 'sample_name', 'sample id', 'name'],
        'range': ['range', 'size range', 'from - to'],
        'pg_ul': ['pg/ul', 'pg/µl', 'conc', 'concentration'],
        'pct_total': ['% of total', '% total', 'pct total', '% (conc.)'],
        'pmol_l': ['pmol/l', 'nmole/l', 'molarity'],
        'avg_size': ['average size', 'avg. size', 'avg size', 'avg_size'],
        'cv': ['cv', 'coefficient of variation'],
        'threshold': ['threshold', 'quality threshold'],
        'dqn': ['dqn', 'gqn', 'quality number'],
    })

    results = []
    for _, row in df.iterrows():
        sid = _get_str(row, col_map.get('sample_id')) or _get_str(row, col_map.get('well'))
        dqn = _get_float(row, col_map.get('dqn'))
        conc = _get_float(row, col_map.get('pg_ul'))

        if _is_ladder(sid, dqn, conc):
            continue

        results.append({
            'well': _get_str(row, col_map.get('well')) or '',
            'sample_id': sid or '',
            'range': _get_str(row, col_map.get('range')) or '',
            'pg_ul': _get_float(row, col_map.get('pg_ul')),
            'pct_total': _get_float(row, col_map.get('pct_total')),
            'pmol_l': _get_float(row, col_map.get('pmol_l')),
            'avg_size': _get_float(row, col_map.get('avg_size')),
            'cv': _get_float(row, col_map.get('cv')),
            'threshold': _get_str(row, col_map.get('threshold')),
            'dqn': dqn,
        })

    logger.info(f"Smear Analysis: {len(results)} rows from {Path(path).name}")
    return results


# ---------------------------------------------------------------------------
# Column detection helpers
# ---------------------------------------------------------------------------

def _detect_columns(df: pd.DataFrame, mapping_spec: Dict[str, List[str]]) -> Dict[str, Optional[str]]:
    """Auto-detect column names using case-insensitive keyword matching.

    mapping_spec: {logical_name: [keyword, ...]}
    Returns: {logical_name: actual_column_name or None}
    """
    lower_cols = {c.lower(): c for c in df.columns}
    result = {}
    for logical, keywords in mapping_spec.items():
        result[logical] = None
        for kw in keywords:
            for lc, orig in lower_cols.items():
                if kw in lc:
                    result[logical] = orig
                    break
            if result[logical]:
                break
    return result


def _get_str(row: pd.Series, col: Optional[str]) -> Optional[str]:
    if col is None or col not in row.index:
        return None
    val = row[col]
    return str(val).strip() if pd.notna(val) else None


def _get_float(row: pd.Series, col: Optional[str]) -> Optional[float]:
    if col is None or col not in row.index:
        return None
    val = row[col]
    try:
        return float(val) if pd.notna(val) else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Backward-compatible API
# ---------------------------------------------------------------------------

class FemtoPulseParser:
    """Legacy class - maintained for backward compatibility."""

    def __init__(self):
        self.supported_formats = ['.csv', '.xml']

    def parse_file(self, file_path: str) -> List[Dict]:
        return parse_femtopulse_file(file_path)


def parse_femtopulse_file(file_path: str) -> List[Dict]:
    """Backward-compatible single-file parser.

    Detects file type and dispatches to the appropriate parser.
    Returns results in the legacy format: [{sample_id, gqn_rin, concentration,
    avg_size, peak_size, instrument, data_file}, ...]
    """
    file_path = str(file_path)
    ftype = detect_file_type(file_path)

    if ftype == 'quality_table':
        rows = parse_quality_table(file_path)
        return [
            {
                'sample_id': r['sample_id'],
                'gqn_rin': r.get('dqn'),
                'concentration': r.get('total_concentration'),
                'avg_size': None,
                'peak_size': None,
                'instrument': 'Femto Pulse',
                'data_file': file_path,
            }
            for r in rows
        ]

    if ftype == 'peak_table':
        rows = parse_peak_table(file_path)
        return [
            {
                'sample_id': r['sample_id'],
                'gqn_rin': r.get('dqn'),
                'concentration': r.get('total_conc'),
                'avg_size': None,
                'peak_size': r['peaks'][0]['size'] if r.get('peaks') else None,
                'instrument': 'Femto Pulse',
                'data_file': file_path,
            }
            for r in rows
        ]

    if ftype == 'smear_analysis':
        rows = parse_smear_analysis(file_path)
        seen = {}
        for r in rows:
            sid = r['sample_id']
            if sid not in seen:
                seen[sid] = {
                    'sample_id': sid,
                    'gqn_rin': r.get('dqn'),
                    'concentration': r.get('pg_ul'),
                    'avg_size': r.get('avg_size'),
                    'peak_size': None,
                    'instrument': 'Femto Pulse',
                    'data_file': file_path,
                }
        return list(seen.values())

    # Fallback: generic CSV parsing (original behavior)
    return _parse_generic_csv(file_path)


def _parse_generic_csv(file_path: str) -> List[Dict]:
    """Fallback generic CSV parser (original behavior)."""
    try:
        df = _read_csv_safe(file_path)
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        raise

    df.columns = df.columns.str.strip().str.lower()

    col_map = _detect_columns(df, {
        'sample_name': ['sample name', 'sample_name', 'name', 'well'],
        'gqn': ['gqn', 'quality number', 'rin', 'dqn'],
        'concentration': ['concentration', 'conc', 'ng/ul', 'ng/µl', 'total concentration'],
        'avg_size': ['average size', 'avg. size', 'avg size', 'mean size'],
        'peak_size': ['peak size', 'modal size'],
    })

    results = []
    for _, row in df.iterrows():
        sid = _get_str(row, col_map.get('sample_name'))
        if not sid:
            continue
        results.append({
            'sample_id': sid,
            'gqn_rin': _get_float(row, col_map.get('gqn')),
            'concentration': _get_float(row, col_map.get('concentration')),
            'avg_size': _get_float(row, col_map.get('avg_size')),
            'peak_size': _get_float(row, col_map.get('peak_size')),
            'instrument': 'Femto Pulse',
            'data_file': file_path,
        })

    logger.info(f"Generic CSV: {len(results)} samples from {Path(file_path).name}")
    return results


def get_sizing_curve(file_path: str, sample_id: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Extract sizing curve for a specific sample from an Electropherogram file."""
    ftype = detect_file_type(file_path)
    if ftype != 'electropherogram':
        return None

    try:
        data = parse_electropherogram(file_path)
        size_bp = data['size_bp']
        for col_name, rfu in data['samples'].items():
            if sample_id in col_name:
                return (size_bp, rfu)
    except Exception as e:
        logger.error(f"Failed to extract sizing curve: {e}")

    return None
