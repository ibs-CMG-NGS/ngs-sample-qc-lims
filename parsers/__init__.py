"""Parsers package initialization"""
from parsers.nanodrop_parser import NanoDropParser, parse_nanodrop_file
from parsers.qubit_parser import QubitParser, parse_qubit_file
from parsers.femtopulse_parser import (
    FemtoPulseParser,
    parse_femtopulse_file,
    get_sizing_curve,
    detect_file_type,
    scan_femtopulse_folder,
    parse_femtopulse_folder,
    parse_quality_table,
    parse_peak_table,
    parse_electropherogram,
    parse_size_calibration,
    parse_smear_analysis,
    _strip_samp_prefix,
)

__all__ = [
    'NanoDropParser',
    'QubitParser',
    'FemtoPulseParser',
    'parse_nanodrop_file',
    'parse_qubit_file',
    'parse_femtopulse_file',
    'get_sizing_curve',
    'detect_file_type',
    'scan_femtopulse_folder',
    'parse_femtopulse_folder',
    'parse_quality_table',
    'parse_peak_table',
    'parse_electropherogram',
    'parse_size_calibration',
    'parse_smear_analysis',
    '_strip_samp_prefix',
]
