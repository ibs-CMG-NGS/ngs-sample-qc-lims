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
    source = Column(String(200))
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    qc_metrics = relationship("QCMetric", back_populates="sample", cascade="all, delete-orphan")
    raw_traces = relationship("RawTrace", back_populates="sample", cascade="all, delete-orphan")
    
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
