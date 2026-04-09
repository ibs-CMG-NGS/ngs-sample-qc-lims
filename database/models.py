"""
Database Models for NGS Sample QC LIMS
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class SampleType(enum.Enum):
    """샘플 타입 열거형"""
    WGS = "Whole Genome Sequencing"
    mRNA_seq = "mRNA Sequencing"
    ChIP_seq = "ChIP Sequencing"
    ATAC_seq = "ATAC Sequencing"


class QCStatus(enum.Enum):
    """QC 상태 열거형"""
    PASS = "Pass"
    WARNING = "Warning"
    FAIL = "Fail"
    PENDING = "Pending"


class Sample(Base):
    """샘플 정보 테이블"""
    __tablename__ = 'samples'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(String(100), unique=True, nullable=False, index=True)
    sample_name = Column(String(200))
    sample_type = Column(String(50), nullable=False)  # WGS, mRNA-seq, etc.
    species = Column(String(100))  # Human, Mouse, Rat, etc.
    material = Column(String(100))  # Blood, Tissue, Cultured Cell, FFPE, Saliva
    full_name = Column(String(200))  # Optional – 고객사 제공 명칭 등
    project = Column(String(200))    # Project name
    parent_sample_id = Column(String(100))  # 분기 원본 샘플 ID
    branch_type = Column(String(50))         # Re-extraction / Aliquot / Other
    source = Column(String(200))
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    qc_metrics = relationship("QCMetric", back_populates="sample", cascade="all, delete-orphan")
    raw_traces = relationship("RawTrace", back_populates="sample", cascade="all, delete-orphan")
    notes = relationship("SampleNote", back_populates="sample", cascade="all, delete-orphan")
    sequencing_results = relationship("SequencingResult", back_populates="sample", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Sample(id={self.sample_id}, type={self.sample_type})>"


class QCMetric(Base):
    """QC 측정 데이터 테이블"""
    __tablename__ = 'qc_metrics'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(String(100), ForeignKey('samples.sample_id'), nullable=False)
    step = Column(String(50), nullable=False)  # gDNA Extraction, SRE, DNA Shearing, Library Prep, Polymerase Binding
    
    # Concentration measurements
    concentration = Column(Float)  # ng/µl
    volume = Column(Float)  # µl
    total_amount = Column(Float)  # ng (calculated)
    
    # Purity measurements (NanoDrop)
    purity_260_280 = Column(Float)  # A260/A280 ratio
    purity_260_230 = Column(Float)  # A260/A230 ratio
    
    # Quality metrics
    gqn_rin = Column(Float)  # GQN for DNA, RIN for RNA
    avg_size = Column(Float)  # bp
    peak_size = Column(Float)  # bp
    
    # Molarity (calculated)
    molarity = Column(Float)  # nM
    
    # Status
    status = Column(String(20))  # Pass, Warning, Fail
    
    # Library index (e.g. A04, H03) — Library Prep 단계에서 사용
    index_no = Column(String(50))

    # Instrument and file info
    instrument = Column(String(50))  # NanoDrop, Qubit, Femto Pulse
    data_file = Column(String(500))  # Original data file path
    
    # Timestamps
    measured_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    sample = relationship("Sample", back_populates="qc_metrics")
    
    def __repr__(self):
        return f"<QCMetric(sample={self.sample_id}, step={self.step}, status={self.status})>"


class RawTrace(Base):
    """Femto Pulse Raw Data 경로 저장 테이블"""
    __tablename__ = 'raw_traces'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(String(100), ForeignKey('samples.sample_id'), nullable=False)
    step = Column(String(50))  # 어느 단계의 측정인지
    
    # File paths
    raw_file_path = Column(String(500))  # CSV/XML 원본 파일
    image_path = Column(String(500))  # 저장된 그래프 이미지
    
    # Metadata
    instrument_name = Column(String(100))
    assay_type = Column(String(100))  # Genomic DNA, High Sensitivity, etc.
    
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    sample = relationship("Sample", back_populates="raw_traces")
    
    def __repr__(self):
        return f"<RawTrace(sample={self.sample_id}, step={self.step})>"


class ExperimentBatch(Base):
    """실험 배치 정보 (향후 확장용)"""
    __tablename__ = 'experiment_batches'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(100), unique=True, nullable=False)
    batch_name = Column(String(200))
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<ExperimentBatch(id={self.batch_id})>"


class FemtoPulseRun(Base):
    """Femto Pulse 실행 단위 — 5종 파일 경로 추적"""
    __tablename__ = 'femtopulse_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_folder = Column(String(500), nullable=False)
    step = Column(String(50), nullable=False)

    quality_table_path = Column(String(500))
    peak_table_path = Column(String(500))
    electropherogram_path = Column(String(500))
    size_calibration_path = Column(String(500))
    smear_analysis_path = Column(String(500))

    measured_at = Column(DateTime)   # 실험자가 선택한 측정 날짜
    created_at = Column(DateTime, default=datetime.now)

    smear_analyses = relationship("SmearAnalysis", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FemtoPulseRun(id={self.id}, step={self.step})>"


class SmearAnalysis(Base):
    """Smear Analysis 결과 — 샘플 x range 별"""
    __tablename__ = 'smear_analyses'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(String(100), ForeignKey('samples.sample_id'), nullable=False)
    step = Column(String(50))
    run_id = Column(Integer, ForeignKey('femtopulse_runs.id'))

    range_text = Column(String(100))
    pg_ul = Column(Float)
    pct_total = Column(Float)
    pmol_l = Column(Float)
    avg_size = Column(Float)
    cv = Column(Float)
    threshold = Column(String(50))
    dqn = Column(Float)

    created_at = Column(DateTime, default=datetime.now)

    run = relationship("FemtoPulseRun", back_populates="smear_analyses")

    def __repr__(self):
        return f"<SmearAnalysis(sample={self.sample_id}, range={self.range_text})>"


class Project(Base):
    """프로젝트 — species/material/sample_type 등 공통 속성 저장"""
    __tablename__ = 'projects'

    id           = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String(200), unique=True, nullable=False, index=True)
    species      = Column(String(100))
    material     = Column(String(100))
    sample_type  = Column(String(50))   # WGS, mRNA-seq, 등
    description  = Column(String(500))
    created_at   = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Project(name={self.project_name})>"


class SequencingResult(Base):
    """PacBio Revio 시퀀싱 후 QC 결과 테이블"""
    __tablename__ = 'sequencing_results'

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    sample_id           = Column(String(100), ForeignKey('samples.sample_id'), nullable=False)
    run_id              = Column(String(200))   # r84285_20260402_061807
    smrt_cell           = Column(String(20))    # 1_A01
    barcode_id          = Column(String(20))    # bc2044
    measured_at         = Column(DateTime, default=datetime.now)
    created_at          = Column(DateTime, default=datetime.now)

    hifi_reads_m        = Column(Float)   # HiFi Reads (M)
    hifi_yield_gb       = Column(Float)   # HiFi Yield (Gb)
    coverage_x          = Column(Float)   # Est. Coverage (×)
    read_length_mean_kb = Column(Float)   # Read Length mean (kb)
    read_length_n50_kb  = Column(Float)   # Read Length N50 (kb)
    read_quality_q      = Column(Float)   # Read Quality median (Q값)
    q30_pct             = Column(Float)   # Q30+ Bases (%)
    zmw_p1_pct          = Column(Float)   # P1 ZMW Productivity (%)
    missing_adapter_pct = Column(Float)   # Missing Adapter (%)
    mean_passes         = Column(Float)   # Mean Passes
    control_reads       = Column(Integer) # Control Reads
    control_rl_mean_kb  = Column(Float)   # Control RL mean (kb)
    status              = Column(String(20))  # Pass / Warning / Fail

    sample = relationship("Sample", back_populates="sequencing_results")

    def __repr__(self):
        return f"<SequencingResult(sample={self.sample_id}, run={self.run_id}, status={self.status})>"


class SampleNote(Base):
    """샘플별 메모/노트"""
    __tablename__ = 'sample_notes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(String(100), ForeignKey('samples.sample_id'), nullable=False)
    note_text = Column(String(2000), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    sample = relationship("Sample", back_populates="notes")

    def __repr__(self):
        return f"<SampleNote(sample={self.sample_id}, id={self.id})>"
