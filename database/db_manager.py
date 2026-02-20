"""
Database Manager - SQLAlchemy Session 및 DB 연결 관리
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
import logging

from config.settings import DATABASE_URL
from database.models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """데이터베이스 연결 및 세션 관리 클래스"""
    
    def __init__(self, database_url=None):
        """
        Args:
            database_url: SQLAlchemy 데이터베이스 URL
        """
        self.database_url = database_url or DATABASE_URL
        self.engine = None
        self.session_factory = None
        self.Session = None
        
    def initialize(self):
        """데이터베이스 엔진 초기화 및 테이블 생성"""
        try:
            # SQLite 엔진 생성 (Thread-safe)
            self.engine = create_engine(
                self.database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=False  # SQL 로그 출력 (디버깅 시 True)
            )
            
            # 세션 팩토리 생성
            self.session_factory = sessionmaker(bind=self.engine)
            self.Session = scoped_session(self.session_factory)
            
            # 테이블 생성
            Base.metadata.create_all(self.engine)
            
            logger.info(f"Database initialized: {self.database_url}")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def get_session(self):
        """새로운 세션 반환"""
        if self.Session is None:
            self.initialize()
        return self.Session()
    
    @contextmanager
    def session_scope(self):
        """
        Context manager로 세션 관리
        
        Usage:
            with db_manager.session_scope() as session:
                session.add(sample)
                session.commit()
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session rollback due to: {e}")
            raise
        finally:
            session.close()
    
    def close(self):
        """세션 및 엔진 종료"""
        if self.Session:
            self.Session.remove()
        if self.engine:
            self.engine.dispose()
        logger.info("Database connection closed")
    
    def reset_database(self):
        """데이터베이스 초기화 (모든 테이블 삭제 후 재생성)"""
        try:
            Base.metadata.drop_all(self.engine)
            Base.metadata.create_all(self.engine)
            logger.warning("Database has been reset!")
            return True
        except Exception as e:
            logger.error(f"Database reset failed: {e}")
            return False


# 전역 데이터베이스 매니저 인스턴스
db_manager = DatabaseManager()


# CRUD 헬퍼 함수들
def add_sample(session, sample_data):
    """샘플 추가"""
    from database.models import Sample
    
    sample = Sample(**sample_data)
    session.add(sample)
    session.flush()  # ID 생성
    return sample


def get_sample_by_id(session, sample_id):
    """샘플 ID로 조회"""
    from database.models import Sample
    return session.query(Sample).filter(Sample.sample_id == sample_id).first()


def delete_sample(session, sample_id):
    """샘플 및 관련 QC 데이터/Raw Trace 삭제"""
    from database.models import Sample, QCMetric, RawTrace

    session.query(RawTrace).filter(RawTrace.sample_id == sample_id).delete()
    session.query(QCMetric).filter(QCMetric.sample_id == sample_id).delete()
    count = session.query(Sample).filter(Sample.sample_id == sample_id).delete()
    session.flush()
    return count > 0


def get_all_samples(session, sample_type=None):
    """모든 샘플 조회 (타입 필터 옵션)"""
    from database.models import Sample
    
    query = session.query(Sample)
    if sample_type:
        query = query.filter(Sample.sample_type == sample_type)
    return query.order_by(Sample.created_at.desc()).all()


def add_qc_metric(session, qc_data):
    """QC 측정값 추가"""
    from database.models import QCMetric
    
    qc_metric = QCMetric(**qc_data)
    session.add(qc_metric)
    session.flush()
    return qc_metric


def get_qc_metrics_by_sample(session, sample_id):
    """특정 샘플의 모든 QC 측정값 조회"""
    from database.models import QCMetric
    
    return session.query(QCMetric)\
        .filter(QCMetric.sample_id == sample_id)\
        .order_by(QCMetric.measured_at)\
        .all()


def get_latest_qc_metric(session, sample_id, step=None):
    """샘플의 최신 QC 측정값 조회"""
    from database.models import QCMetric
    
    query = session.query(QCMetric).filter(QCMetric.sample_id == sample_id)
    if step:
        query = query.filter(QCMetric.step == step)
    return query.order_by(QCMetric.measured_at.desc()).first()


def get_qc_metric_by_id(session, metric_id):
    """QC 측정값 PK로 조회"""
    from database.models import QCMetric
    return session.query(QCMetric).filter(QCMetric.id == metric_id).first()


def update_qc_metric(session, metric_id, update_data):
    """QC 측정값 수정"""
    metric = get_qc_metric_by_id(session, metric_id)
    if not metric:
        return None
    for key, value in update_data.items():
        if hasattr(metric, key):
            setattr(metric, key, value)
    session.flush()
    return metric


def delete_qc_metric(session, metric_id):
    """QC 측정값 삭제 — Femto Pulse인 경우 RawTrace, SmearAnalysis도 함께 삭제"""
    from database.models import RawTrace, SmearAnalysis

    metric = get_qc_metric_by_id(session, metric_id)
    if not metric:
        return False

    if metric.instrument == 'Femto Pulse':
        session.query(RawTrace).filter(
            RawTrace.sample_id == metric.sample_id,
            RawTrace.step == metric.step,
            RawTrace.instrument_name == 'Femto Pulse',
        ).delete()
        session.query(SmearAnalysis).filter(
            SmearAnalysis.sample_id == metric.sample_id,
            SmearAnalysis.step == metric.step,
        ).delete()

    session.delete(metric)
    session.flush()
    return True


def update_sample(session, sample_id, update_data):
    """샘플 정보 수정"""
    sample = get_sample_by_id(session, sample_id)
    if not sample:
        return None
    for key, value in update_data.items():
        if hasattr(sample, key):
            setattr(sample, key, value)
    session.flush()
    return sample


def add_raw_trace(session, trace_data):
    """Raw trace 파일 정보 추가"""
    from database.models import RawTrace

    trace = RawTrace(**trace_data)
    session.add(trace)
    session.flush()
    return trace


def add_femtopulse_run(session, data):
    """FemtoPulseRun 레코드 생성"""
    from database.models import FemtoPulseRun

    run = FemtoPulseRun(**data)
    session.add(run)
    session.flush()
    return run


def get_femtopulse_run(session, run_id):
    """FemtoPulseRun PK로 조회"""
    from database.models import FemtoPulseRun
    return session.query(FemtoPulseRun).filter(FemtoPulseRun.id == run_id).first()


def add_smear_analysis(session, data):
    """SmearAnalysis 레코드 생성"""
    from database.models import SmearAnalysis

    sa = SmearAnalysis(**data)
    session.add(sa)
    session.flush()
    return sa


def get_smear_analyses_by_sample(session, sample_id, step=None):
    """특정 샘플의 SmearAnalysis 조회 (step 필터 옵션)"""
    from database.models import SmearAnalysis

    query = session.query(SmearAnalysis).filter(SmearAnalysis.sample_id == sample_id)
    if step:
        query = query.filter(SmearAnalysis.step == step)
    return query.order_by(SmearAnalysis.created_at).all()
