"""
NGS Sample QC LIMS - Configuration Settings
"""
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

# QC Steps
QC_STEPS = [
    "gDNA Extraction",
    "SRE",
    "DNA Shearing",
    "Library Prep",
    "Polymerase Binding",
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
        }
    }
}

# Molarity Calculation Constants
DNA_MW_PER_BP = 650  # g/mol per bp (average)
RNA_MW_PER_BASE = 330  # g/mol per base (average)

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
