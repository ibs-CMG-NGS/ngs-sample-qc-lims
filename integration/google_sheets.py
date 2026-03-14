"""
Google Sheets 양방향 동기화 모듈

Push: DB → Google Sheets (Samples / QC_Metrics / Notes 시트)
Pull: Google Sheets → DB (upsert, 타임스탬프 기준 최신 우선)

인증: Service Account JSON (gspread >= 6.0)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── 헤더 정의 ─────────────────────────────────────────────────────────────

SAMPLES_HEADERS = [
    "Sample ID", "Sample Name", "Full Name", "Type",
    "Species", "Material", "Project", "Source", "Description", "Created",
]

QC_METRICS_HEADERS = [
    "Sample ID", "Step", "Instrument",
    "Conc (ng/ul)", "Volume (ul)", "Total (ng)",
    "260/280", "260/230", "GQN/RIN", "Avg Size (bp)",
    "Status", "Measured At",
]

NOTES_HEADERS = [
    "Sample ID", "Note", "Created",
]


def _norm(key: str) -> str:
    """헤더명 정규화: 소문자 + 공백→_ + 괄호 제거."""
    import re
    return re.sub(r"[^a-z0-9_]", "_", key.strip().lower())


# ── 헤더→DB 필드 매핑 ──────────────────────────────────────────────────────

_SAMPLE_MAP = {
    _norm("Sample ID"):   "sample_id",
    _norm("Sample Name"): "sample_name",
    _norm("Full Name"):   "full_name",
    _norm("Type"):        "sample_type",
    _norm("Species"):     "species",
    _norm("Material"):    "material",
    _norm("Project"):     "project",
    _norm("Source"):      "source",
    _norm("Description"): "description",
    _norm("Created"):     "created_at",
}

_METRIC_MAP = {
    _norm("Sample ID"):    "sample_id",
    _norm("Step"):         "step",
    _norm("Instrument"):   "instrument",
    _norm("Conc (ng/ul)"): "concentration",
    _norm("Volume (ul)"):  "volume",
    _norm("Total (ng)"):   "total_amount",
    _norm("260/280"):      "purity_260_280",
    _norm("260/230"):      "purity_260_230",
    _norm("GQN/RIN"):      "gqn_rin",
    _norm("Avg Size (bp)"): "avg_size",
    _norm("Status"):       "status",
    _norm("Measured At"):  "measured_at",
}

_NOTE_MAP = {
    _norm("Sample ID"): "sample_id",
    _norm("Note"):       "note_text",
    _norm("Created"):    "created_at",
}


def _parse_dt(value) -> datetime | None:
    """다양한 형식의 날짜 문자열을 datetime으로 파싱."""
    if not value or str(value).strip() in ("", "None", "-"):
        return None
    try:
        from dateutil import parser as dtparser
        return dtparser.parse(str(value))
    except Exception:
        return None


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value) -> float | None:
    try:
        return float(value) if str(value).strip() not in ("", "-", "None") else None
    except (ValueError, TypeError):
        return None


# ── GSheetSync 클래스 ───────────────────────────────────────────────────────

class GSheetSync:
    """Google Sheets ↔ LIMS DB 양방향 동기화."""

    def __init__(self, credentials_path: str, spreadsheet_id: str,
                 sheet_names: dict):
        """
        Args:
            credentials_path: Service Account JSON 파일 경로
            spreadsheet_id:   Google Spreadsheet ID
            sheet_names:      {'samples': ..., 'qc_metrics': ..., 'notes': ...}
        """
        self._cred_path = credentials_path
        self._sid = spreadsheet_id
        self._sheet_names = sheet_names
        self._client = None
        self._spreadsheet = None

    # ── 인증 / 연결 ────────────────────────────────────────────────────

    def _get_spreadsheet(self):
        """인증 후 spreadsheet 반환 (캐시)."""
        import gspread
        from google.oauth2.service_account import Credentials

        if self._spreadsheet is None:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ]
            creds = Credentials.from_service_account_file(
                self._cred_path, scopes=scopes
            )
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open_by_key(self._sid)
        return self._spreadsheet

    def test_connection(self) -> tuple[bool, str]:
        """연결 테스트.

        Returns:
            (success: bool, message: str)
        """
        try:
            ss = self._get_spreadsheet()
            title = ss.title
            return True, f"연결 성공: '{title}'"
        except FileNotFoundError:
            return False, "Service Account JSON 파일을 찾을 수 없습니다."
        except Exception as e:
            return False, f"연결 실패: {e}"

    def _get_or_create_sheet(self, name: str):
        """시트 이름으로 워크시트 반환. 없으면 새로 생성."""
        ss = self._get_spreadsheet()
        try:
            return ss.worksheet(name)
        except Exception:
            return ss.add_worksheet(title=name, rows=1000, cols=20)

    # ── Push (DB → Sheets) ─────────────────────────────────────────────

    def push(self, session) -> dict:
        """DB 전체 데이터를 Google Sheets로 내보내기.

        Returns:
            {'samples': N, 'metrics': M, 'notes': K}
        """
        from database.models import Sample, QCMetric, SampleNote

        counts = {"samples": 0, "metrics": 0, "notes": 0}

        # ── Samples 시트 ──
        ws = self._get_or_create_sheet(self._sheet_names["samples"])
        samples = session.query(Sample).order_by(Sample.sample_id).all()
        rows = [SAMPLES_HEADERS]
        for s in samples:
            rows.append([
                s.sample_id or "",
                s.sample_name or "",
                s.full_name or "",
                s.sample_type or "",
                s.species or "",
                s.material or "",
                s.project or "",
                s.source or "",
                s.description or "",
                _fmt_dt(s.created_at),
            ])
        ws.clear()
        ws.update(rows, value_input_option="USER_ENTERED")
        counts["samples"] = len(samples)
        logger.info(f"Push: {len(samples)} samples")

        # ── QC_Metrics 시트 ──
        ws = self._get_or_create_sheet(self._sheet_names["qc_metrics"])
        metrics = session.query(QCMetric).order_by(
            QCMetric.sample_id, QCMetric.step, QCMetric.measured_at
        ).all()
        rows = [QC_METRICS_HEADERS]
        for m in metrics:
            rows.append([
                m.sample_id or "",
                m.step or "",
                m.instrument or "",
                m.concentration if m.concentration is not None else "",
                m.volume if m.volume is not None else "",
                m.total_amount if m.total_amount is not None else "",
                m.purity_260_280 if m.purity_260_280 is not None else "",
                m.purity_260_230 if m.purity_260_230 is not None else "",
                m.gqn_rin if m.gqn_rin is not None else "",
                m.avg_size if m.avg_size is not None else "",
                m.status or "",
                _fmt_dt(m.measured_at),
            ])
        ws.clear()
        ws.update(rows, value_input_option="USER_ENTERED")
        counts["metrics"] = len(metrics)
        logger.info(f"Push: {len(metrics)} metrics")

        # ── Notes 시트 ──
        ws = self._get_or_create_sheet(self._sheet_names["notes"])
        notes = session.query(SampleNote).order_by(
            SampleNote.sample_id, SampleNote.created_at
        ).all()
        rows = [NOTES_HEADERS]
        for n in notes:
            rows.append([
                n.sample_id or "",
                n.note_text or "",
                _fmt_dt(n.created_at),
            ])
        ws.clear()
        ws.update(rows, value_input_option="USER_ENTERED")
        counts["notes"] = len(notes)
        logger.info(f"Push: {len(notes)} notes")

        return counts

    # ── Push TG Template (DB → Sheets, 가로 형식) ──────────────────────

    def push_tg_template(self, session, sample_ids: list | None = None) -> int:
        """DB 데이터를 TG_varient_progress 템플릿 형식으로 내보내기.

        한 행 = 한 샘플, 각 QC 단계가 가로로 배치됨.
        Args:
            sample_ids: 내보낼 샘플 ID 목록. None이면 전체 샘플.
        Returns:
            내보낸 샘플 수
        """
        from database.models import Sample, QCMetric, SampleNote

        sheet_name = self._sheet_names.get("tg_process", "TG_process")
        ws = self._get_or_create_sheet(sheet_name)

        # ── 헤더 3행 ──
        header_row1 = [
            "\\", "Sample information", "gDNA QC", None, None, None, None, None, None,
            "SRE", None, None, None,
            "Shearing", None, None, None,
            "Library", None, None, None, None, None,
            "Binding Complex", None,
            "Note",
        ]
        header_row2 = [
            None, "ID", "Prep date",
            "Nanodrop", None, None, "Qubit", "Volume\n(ul)", "Total amount\n(ng)",
            "Pre", "Post_Qubit", None, None,
            "Pre", "Post", None, None,
            None, None, None, None, None, None,
            None, None,
            None,
        ]
        header_row3 = [
            None, None, None,
            "Conc.\n(ng/ul)", "260/280", "260/230", "Conc.\n(ng/ul)", None, None,
            "Input\n(ng)", "Conc.\n(ng/ul)", "Volume\n(ul)", "Total\n(ng)",
            "Input\n(ng)", "Conc.\n(ng/ul)", "Volume\n(ul)", "Total\n(ng)",
            "Index", "Conc.\n(ng/ul)", "Vol.\n(ul)", "Total\n(ng)", "Yield\n(%)", "Avg. Size\n(bp)",
            "Conc.\n(ng/ul)", "Vol.\n(ul)",
            None,
        ]

        # ── 샘플별 데이터 수집 ──
        q = session.query(Sample).order_by(Sample.sample_id)
        if sample_ids is not None:
            q = q.filter(Sample.sample_id.in_(sample_ids))
        samples = q.all()
        data_rows = []

        for i, s in enumerate(samples, start=1):
            metrics = session.query(QCMetric).filter(
                QCMetric.sample_id == s.sample_id
            ).all()

            def _get(step, instrument):
                for m in metrics:
                    if m.step == step and m.instrument == instrument:
                        return m
                return None

            gdna_nd  = _get("gDNA Extraction", "NanoDrop")
            gdna_qb  = _get("gDNA Extraction", "Qubit")
            sre_qb   = _get("SRE", "Qubit")
            shear_qb = _get("DNA Shearing", "Qubit")
            lib_qb   = _get("Library Prep", "Qubit")
            lib_fp   = _get("Library Prep", "Femto Pulse")
            bind_qb  = _get("Polymerase Binding", "Qubit")

            # 날짜: gDNA Extraction Qubit 또는 NanoDrop 측정일
            prep_dt = None
            if gdna_qb and gdna_qb.measured_at:
                prep_dt = gdna_qb.measured_at.strftime("%Y-%m-%d")
            elif gdna_nd and gdna_nd.measured_at:
                prep_dt = gdna_nd.measured_at.strftime("%Y-%m-%d")

            # Note: 가장 최근 노트 1개
            note_obj = session.query(SampleNote).filter(
                SampleNote.sample_id == s.sample_id
            ).order_by(SampleNote.created_at.desc()).first()
            note_text = note_obj.note_text if note_obj else ""

            r = i + 3  # 실제 시트 행 번호 (헤더 3행 이후)

            def _v(m, field):
                return getattr(m, field) if m and getattr(m, field) is not None else ""

            row = [
                i,                              # A: 번호
                s.sample_id,                    # B: Sample ID
                prep_dt or "",                  # C: Prep date
                _v(gdna_nd, "concentration"),   # D: Nanodrop Conc
                _v(gdna_nd, "purity_260_280"),  # E: 260/280
                _v(gdna_nd, "purity_260_230"),  # F: 260/230
                _v(gdna_qb, "concentration"),   # G: Qubit Conc
                _v(gdna_qb, "volume"),          # H: Volume
                f"=G{r}*H{r}",                  # I: Total = Qubit Conc × Vol
                f"=I{r}",                       # J: SRE Pre Input = gDNA Total
                _v(sre_qb, "concentration"),    # K: SRE Post Qubit Conc
                _v(sre_qb, "volume"),           # L: SRE Post Volume
                f"=K{r}*L{r}",                  # M: SRE Post Total
                f"=M{r}",                       # N: Shearing Pre Input = SRE Total
                _v(shear_qb, "concentration"),  # O: Shearing Post Conc
                _v(shear_qb, "volume"),         # P: Shearing Post Volume
                f"=O{r}*P{r}",                  # Q: Shearing Post Total
                _v(lib_qb, "index_no"),         # R: Library Index
                _v(lib_qb, "concentration"),    # S: Library Conc
                _v(lib_qb, "volume"),           # T: Library Vol
                f"=S{r}*T{r}",                  # U: Library Total
                f"=U{r}/I{r}*100",              # V: Yield (%)
                _v(lib_fp, "avg_size"),         # W: Avg Size (bp)
                _v(bind_qb, "concentration"),   # X: Binding Complex Conc
                _v(bind_qb, "volume"),          # Y: Binding Complex Vol
                note_text,                      # Z: Note
            ]
            data_rows.append(row)

        all_rows = [header_row1, header_row2, header_row3] + data_rows
        ws.clear()
        ws.update(all_rows, value_input_option="USER_ENTERED")
        logger.info(f"push_tg_template: {len(data_rows)} samples → '{sheet_name}'")
        return len(data_rows)

    # ── Pull (Sheets → DB) ─────────────────────────────────────────────

    def pull(self, session) -> dict:
        """Google Sheets → DB upsert. 타임스탬프 기준 최신 우선.

        Returns:
            {'samples_new': a, 'samples_updated': b,
             'metrics_new': c, 'metrics_updated': d,
             'notes_new': e}
        """
        counts = {
            "samples_new": 0, "samples_updated": 0,
            "metrics_new": 0, "metrics_updated": 0,
            "notes_new": 0,
        }

        counts.update(self._pull_samples(session))
        counts.update(self._pull_metrics(session))
        counts.update(self._pull_notes(session))
        session.commit()
        return counts

    def _sheet_to_dicts(self, sheet_name: str, field_map: dict) -> list[dict]:
        """시트 데이터를 [{db_field: value}] 형태로 반환."""
        ws = self._get_or_create_sheet(sheet_name)
        all_rows = ws.get_all_values()
        if len(all_rows) < 2:
            return []
        headers = [_norm(h) for h in all_rows[0]]
        result = []
        for row in all_rows[1:]:
            if not any(c.strip() for c in row):
                continue   # 빈 행 건너뜀
            record = {}
            for col_idx, raw_header in enumerate(headers):
                db_field = field_map.get(raw_header)
                if db_field and col_idx < len(row):
                    record[db_field] = row[col_idx].strip()
            result.append(record)
        return result

    def _pull_samples(self, session) -> dict:
        from database.models import Sample

        records = self._sheet_to_dicts(self._sheet_names["samples"], _SAMPLE_MAP)
        new_count = upd_count = 0

        for rec in records:
            sid = rec.get("sample_id", "").strip()
            if not sid:
                continue

            existing = session.query(Sample).filter(
                Sample.sample_id == sid
            ).first()

            sheets_updated = _parse_dt(rec.get("created_at"))

            if existing is None:
                s = Sample(
                    sample_id=sid,
                    sample_name=rec.get("sample_name") or None,
                    full_name=rec.get("full_name") or None,
                    sample_type=rec.get("sample_type") or "WGS",
                    species=rec.get("species") or None,
                    material=rec.get("material") or None,
                    project=rec.get("project") or None,
                    source=rec.get("source") or None,
                    description=rec.get("description") or None,
                )
                session.add(s)
                new_count += 1
            else:
                # 타임스탬프 비교: Sheets가 더 최신이면 업데이트
                db_ts = existing.updated_at or existing.created_at
                if sheets_updated and db_ts and sheets_updated <= db_ts:
                    continue  # DB가 최신 → 건너뜀
                for field in ("sample_name", "full_name", "sample_type",
                              "species", "material", "project", "source",
                              "description"):
                    val = rec.get(field)
                    if val:
                        setattr(existing, field, val)
                upd_count += 1

        logger.info(f"Pull Samples: new={new_count}, updated={upd_count}")
        return {"samples_new": new_count, "samples_updated": upd_count}

    def _pull_metrics(self, session) -> dict:
        from database.models import QCMetric, Sample

        records = self._sheet_to_dicts(self._sheet_names["qc_metrics"], _METRIC_MAP)
        new_count = upd_count = 0

        for rec in records:
            sid = rec.get("sample_id", "").strip()
            if not sid:
                continue

            # 참조 Sample이 없으면 기본 샘플 생성
            if not session.query(Sample).filter(Sample.sample_id == sid).first():
                session.add(Sample(sample_id=sid, sample_type="WGS"))

            step       = rec.get("step", "").strip()
            instrument = rec.get("instrument", "").strip()
            measured_at = _parse_dt(rec.get("measured_at"))

            # 복합키: sample_id + step + instrument + measured_at(날짜 수준)
            existing = None
            if measured_at:
                existing = session.query(QCMetric).filter(
                    QCMetric.sample_id == sid,
                    QCMetric.step == step,
                    QCMetric.instrument == instrument,
                    QCMetric.measured_at == measured_at,
                ).first()

            if existing is None:
                m = QCMetric(
                    sample_id=sid,
                    step=step,
                    instrument=instrument or None,
                    concentration=_safe_float(rec.get("concentration")),
                    volume=_safe_float(rec.get("volume")),
                    total_amount=_safe_float(rec.get("total_amount")),
                    purity_260_280=_safe_float(rec.get("purity_260_280")),
                    purity_260_230=_safe_float(rec.get("purity_260_230")),
                    gqn_rin=_safe_float(rec.get("gqn_rin")),
                    avg_size=_safe_float(rec.get("avg_size")),
                    status=rec.get("status") or "Pending",
                    measured_at=measured_at or datetime.now(),
                )
                session.add(m)
                new_count += 1
            else:
                # 타임스탬프 비교
                db_ts = existing.created_at
                if measured_at and db_ts and measured_at <= db_ts:
                    continue
                for field, key in [
                    ("concentration", "concentration"),
                    ("volume", "volume"),
                    ("total_amount", "total_amount"),
                    ("purity_260_280", "purity_260_280"),
                    ("purity_260_230", "purity_260_230"),
                    ("gqn_rin", "gqn_rin"),
                    ("avg_size", "avg_size"),
                    ("status", "status"),
                ]:
                    val = rec.get(key)
                    if val:
                        parsed = _safe_float(val) if field != "status" else val
                        setattr(existing, field, parsed)
                upd_count += 1

        logger.info(f"Pull Metrics: new={new_count}, updated={upd_count}")
        return {"metrics_new": new_count, "metrics_updated": upd_count}

    def _pull_notes(self, session) -> dict:
        from database.models import SampleNote, Sample

        records = self._sheet_to_dicts(self._sheet_names["notes"], _NOTE_MAP)
        new_count = 0

        for rec in records:
            sid = rec.get("sample_id", "").strip()
            note_text = rec.get("note_text", "").strip()
            if not sid or not note_text:
                continue

            if not session.query(Sample).filter(Sample.sample_id == sid).first():
                session.add(Sample(sample_id=sid, sample_type="WGS"))

            created_at = _parse_dt(rec.get("created_at"))

            # 같은 (sample_id, note_text) 조합이 없을 때만 추가
            dup = session.query(SampleNote).filter(
                SampleNote.sample_id == sid,
                SampleNote.note_text == note_text,
            ).first()
            if dup is None:
                session.add(SampleNote(
                    sample_id=sid,
                    note_text=note_text,
                    created_at=created_at or datetime.now(),
                ))
                new_count += 1

        logger.info(f"Pull Notes: new={new_count}")
        return {"notes_new": new_count}
