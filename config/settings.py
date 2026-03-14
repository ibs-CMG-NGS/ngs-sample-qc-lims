"""
NGS Sample QC LIMS - Configuration Settings
"""
import json
import os
from pathlib import Path

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database Configuration
DATABASE_PATH = BASE_DIR / "data" / "lims.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Data Directories
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
FEMTOPULSE_IMAGES_DIR = DATA_DIR / "femtopulse_images"
REPORTS_DIR = BASE_DIR / "reports"

# Create directories if they don't exist
for directory in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, 
                  FEMTOPULSE_IMAGES_DIR, REPORTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Sample Types
SAMPLE_TYPES = {
    "WGS": "Whole Genome Sequencing",
    "mRNA-seq": "mRNA Sequencing",
    "ChIP-seq": "ChIP Sequencing",
    "ATAC-seq": "ATAC Sequencing"
}

# Species
SPECIES_LIST = ["Human", "Mouse", "Rat"]

# Sample Material
MATERIAL_LIST = ["Blood", "Tissue", "Cultured Cell", "FFPE", "Saliva"]

# QC Steps (DNA)
QC_STEPS = [
    "gDNA Extraction",
    "SRE",
    "DNA Shearing",
    "Library Prep",
    "Polymerase Binding",
]

# QC Steps (RNA)
RNA_QC_STEPS = [
    "RNA Extraction",
    "mRNA Elution",
    "Library Prep (RNA)",
]

# QC Judgment Criteria
QC_CRITERIA = {
    "WGS": {
        "GQN": {
            "pass": 7.0,
            "warning": 5.0
        },
        "library_size": {
            "min": 300,
            "max": 700
        }
    },
    "mRNA-seq": {
        "RIN": {
            "pass": 8.0,
            "warning": 6.0
        },
        "purity_260_280": {
            "pass": 2.0,
            "warning": 1.8
        },
        "purity_260_230": {
            "pass": 1.8,
            "warning": 1.5
        },
        "concentration": {
            "warning": 5.0   # ng/µl 미만 → Warning
        }
    }
}

# UI Settings
WINDOW_TITLE = "NGS Sample QC LIMS"
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

# Status Colors
STATUS_COLORS = {
    "Pass": "#4CAF50",      # Green
    "Warning": "#FF9800",   # Orange
    "Fail": "#F44336"       # Red
}

# Chart Settings
CHART_DPI = 100
CHART_FIGSIZE = (10, 6)

# File Format Settings
SUPPORTED_FORMATS = {
    "nanodrop": [".txt", ".csv"],
    "qubit": [".csv", ".xlsx"],
    "femtopulse": [".csv", ".xml"]
}

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = BASE_DIR / "logs" / "lims.log"

# Create logs directory
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Google Sheets 연동 기본값 ──────────────────────────────────────────────
GSHEETS_DEFAULTS = {
    "credentials_path": "",       # Service Account JSON 파일 경로
    "spreadsheet_id": "",         # Google Spreadsheet ID (URL에서 추출)
    "sheet_names": {
        "samples":    "Samples",
        "qc_metrics": "QC_Metrics",
        "notes":      "Notes",
        "tg_process": "TG_process",
    },
}

_LOCAL_SETTINGS_PATH = BASE_DIR / "config" / "settings.local.json"


def load_local_settings() -> dict:
    """settings.local.json 로드. 파일 없으면 빈 dict 반환."""
    if _LOCAL_SETTINGS_PATH.exists():
        try:
            return json.loads(_LOCAL_SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_local_settings(data: dict) -> None:
    """settings.local.json에 저장. 기존 내용과 병합."""
    current = load_local_settings()
    current.update(data)
    _LOCAL_SETTINGS_PATH.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_gsheets_config() -> dict:
    """로컬 설정에서 Google Sheets 설정 로드. 없으면 기본값 반환."""
    import copy
    cfg = copy.deepcopy(GSHEETS_DEFAULTS)
    local = load_local_settings().get("google_sheets", {})
    cfg["credentials_path"] = local.get("credentials_path", cfg["credentials_path"])
    cfg["spreadsheet_id"]   = local.get("spreadsheet_id",   cfg["spreadsheet_id"])
    cfg["sheet_names"].update(local.get("sheet_names", {}))
    return cfg


def save_gsheets_config(credentials_path: str, spreadsheet_id: str,
                        sheet_names: dict) -> None:
    """Google Sheets 설정을 settings.local.json에 저장."""
    save_local_settings({
        "google_sheets": {
            "credentials_path": credentials_path,
            "spreadsheet_id":   spreadsheet_id,
            "sheet_names":      sheet_names,
        }
    })
