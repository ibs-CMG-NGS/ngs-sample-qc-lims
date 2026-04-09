"""
Database Manager - SQLAlchemy Session 및 DB 연결 관리
"""
from sqlalchemy import create_engine, text
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

            # 스키마 마이그레이션 (기존 DB에 누락된 컬럼 추가)
            self._run_migrations()
            # 기존 프로젝트명을 projects 테이블로 seed
            self._seed_projects_from_samples()

            logger.info(f"Database initialized: {self.database_url}")
            return True
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def _run_migrations(self):
        """기존 DB에 누락된 컬럼을 안전하게 추가 (idempotent)."""
        migrations = [
            "ALTER TABLE samples ADD COLUMN species VARCHAR(100)",
            "ALTER TABLE samples ADD COLUMN material VARCHAR(100)",
            "ALTER TABLE samples ADD COLUMN full_name VARCHAR(200)",
            "ALTER TABLE samples ADD COLUMN project VARCHAR(200)",
            "ALTER TABLE samples ADD COLUMN parent_sample_id VARCHAR(100)",
            "ALTER TABLE samples ADD COLUMN branch_type VARCHAR(50)",
            "ALTER TABLE femtopulse_runs ADD COLUMN measured_at DATETIME",
            "ALTER TABLE qc_metrics ADD COLUMN index_no VARCHAR(50)",
            # sequencing_results 테이블은 Base.metadata.create_all()이 생성하므로
            # 기존 DB에 누락된 경우를 대비해 CREATE TABLE IF NOT EXISTS로 처리
            """CREATE TABLE IF NOT EXISTS sequencing_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id VARCHAR(100) REFERENCES samples(sample_id),
                run_id VARCHAR(200),
                smrt_cell VARCHAR(20),
                barcode_id VARCHAR(20),
                measured_at DATETIME,
                created_at DATETIME,
                hifi_reads_m FLOAT,
                hifi_yield_gb FLOAT,
                coverage_x FLOAT,
                read_length_mean_kb FLOAT,
                read_length_n50_kb FLOAT,
                read_quality_q FLOAT,
                q30_pct FLOAT,
                zmw_p1_pct FLOAT,
                missing_adapter_pct FLOAT,
                mean_passes FLOAT,
                control_reads INTEGER,
                control_rl_mean_kb FLOAT,
                status VARCHAR(20)
            )""",
        ]
        with self.engine.connect() as conn:
            for sql in migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Migration applied: {sql}")
                except Exception:
                    # 컬럼이 이미 존재하면 무시
                    pass

    def _seed_projects_from_samples(self):
        """samples 테이블의 distinct project 값을 projects 테이블로 마이그레이션 (idempotent)."""
        from database.models import Project
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT DISTINCT project FROM samples WHERE project IS NOT NULL AND project != ''")
                ).fetchall()
            if not rows:
                return
            session = self.session_factory()
            try:
                for (name,) in rows:
                    exists = session.query(Project).filter(Project.project_name == name).first()
                    if not exists:
                        session.add(Project(project_name=name))
                session.commit()
                logger.info(f"Seeded {len(rows)} project(s) from samples table")
            except Exception as e:
                session.rollback()
                logger.warning(f"Project seed failed: {e}")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Project seed skipped: {e}")

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


# ── SampleNote CRUD ───────────────────────────────────────────────

def add_note(session, sample_id: str, note_text: str):
    """샘플 메모 추가"""
    from database.models import SampleNote
    note = SampleNote(sample_id=sample_id, note_text=note_text)
    session.add(note)
    session.flush()
    return note


def get_notes_by_sample(session, sample_id: str):
    """샘플의 모든 메모 조회 (최신순)"""
    from database.models import SampleNote
    return (session.query(SampleNote)
            .filter(SampleNote.sample_id == sample_id)
            .order_by(SampleNote.created_at.desc())
            .all())


def update_note(session, note_id: int, note_text: str):
    """메모 수정"""
    from database.models import SampleNote
    note = session.query(SampleNote).filter(SampleNote.id == note_id).first()
    if note:
        note.note_text = note_text
        session.flush()
    return note


def delete_note(session, note_id: int):
    """메모 삭제"""
    from database.models import SampleNote
    note = session.query(SampleNote).filter(SampleNote.id == note_id).first()
    if note:
        session.delete(note)
        session.flush()
    return note is not None


# ── Project CRUD ───────────────────────────────────────────────────

def get_all_projects(session):
    """모든 프로젝트 조회 (이름 순)"""
    from database.models import Project
    return session.query(Project).order_by(Project.project_name).all()


def get_project_by_name(session, name: str):
    """프로젝트 이름으로 조회"""
    from database.models import Project
    return session.query(Project).filter(Project.project_name == name).first()


def add_project(session, data: dict):
    """프로젝트 추가"""
    from database.models import Project
    proj = Project(**data)
    session.add(proj)
    session.flush()
    return proj


def update_project(session, project_name: str, data: dict):
    """프로젝트 수정"""
    proj = get_project_by_name(session, project_name)
    if not proj:
        return None
    for key, value in data.items():
        if hasattr(proj, key):
            setattr(proj, key, value)
    session.flush()
    return proj


# ── Re-extraction lineage ──────────────────────────────────────────

def get_children_by_sample(session, sample_id: str):
    """특정 샘플을 부모로 하는 재추출 샘플 목록 (생성순)."""
    from database.models import Sample
    return (session.query(Sample)
            .filter(Sample.parent_sample_id == sample_id)
            .order_by(Sample.created_at)
            .all())


def get_re_extraction_count(session, sample_id: str) -> int:
    """해당 샘플의 현재까지 재추출 횟수 (직계 자녀 수)."""
    from database.models import Sample
    return (session.query(Sample)
            .filter(Sample.parent_sample_id == sample_id)
            .count())


# ── Sequencing Results ────────────────────────────────────────────

def add_sequencing_result(session, data: dict):
    """SequencingResult 레코드 추가."""
    from database.models import SequencingResult
    rec = SequencingResult(**data)
    session.add(rec)
    session.flush()
    return rec


def get_sequencing_results_by_sample(session, sample_id: str):
    """특정 샘플의 SequencingResult 목록 (측정일 오름차순)."""
    from database.models import SequencingResult
    return (session.query(SequencingResult)
            .filter(SequencingResult.sample_id == sample_id)
            .order_by(SequencingResult.measured_at)
            .all())


def delete_sequencing_result(session, result_id: int):
    """SequencingResult 레코드 삭제."""
    from database.models import SequencingResult
    rec = session.query(SequencingResult).filter(SequencingResult.id == result_id).first()
    if rec:
        session.delete(rec)


def get_all_sequencing_results(session):
    """전체 SequencingResult 목록 (Dashboard/Analysis용)."""
    from database.models import SequencingResult
    return session.query(SequencingResult).order_by(SequencingResult.measured_at).all()

