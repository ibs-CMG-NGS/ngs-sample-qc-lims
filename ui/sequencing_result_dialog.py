"""
Sequencing QC Import 다이얼로그
PacBio Revio QC HTML 리포트를 파싱하여 SequencingResult DB에 저장.
"""
import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QComboBox, QDateEdit, QSizePolicy,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont

from database import db_manager, get_all_samples, add_sequencing_result
from database.models import QCMetric
from parsers.revio_qc_parser import parse_revio_qc_report
from parsers.revio_csv import bc_for_well

logger = logging.getLogger(__name__)

_STATUS_COLOR = {'Pass': '#2E7D32', 'Warning': '#E65100', 'Fail': '#B71C1C', 'No Data': '#9E9E9E'}

SEQ_COLS = [
    "Barcode", "Sample (자동매칭)", "SMRT Cell", "Run ID",
    "Yield (Gb)", "Coverage (×)", "N50 (kb)", "Mean Len (kb)",
    "Quality (Q)", "Q30+ (%)", "P1 (%)", "Status",
]


class SequencingResultDialog(QDialog):
    """Revio QC HTML 리포트 → DB 저장 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequencing QC Import")
        self.setMinimumSize(1000, 520)
        self.resize(1100, 560)

        self._parsed_rows: list[dict] = []
        self._sample_map: dict[str, str] = {}   # barcode_id → sample_id
        self._all_sample_ids: list[str] = []

        self._load_sample_map()
        self._build_ui()

    # ── DB 샘플 로드 ──────────────────────────────────────────────────

    def _load_sample_map(self):
        """Library Prep index_no(well) → bc번호 → sample_id 매핑 구성."""
        try:
            with db_manager.session_scope() as session:
                samples = get_all_samples(session)
                self._all_sample_ids = [s.sample_id for s in samples]

                # index_no가 있는 Library Prep 레코드 조회
                metrics = (session.query(QCMetric)
                           .filter(QCMetric.step == "Library Prep",
                                   QCMetric.index_no.isnot(None))
                           .all())

                for m in metrics:
                    raw = (m.index_no or "").strip()
                    if not raw:
                        continue
                    # raw가 이미 bc2044 형식이면 그대로, 아니면 well → bc 변환
                    if raw.startswith('bc'):
                        bc = raw
                    else:
                        try:
                            bc = bc_for_well(raw)
                        except Exception:
                            bc = raw
                    # 같은 bc에 여러 sample이 있으면 최신 우선 (overwrite)
                    self._sample_map[bc] = m.sample_id

        except Exception as e:
            logger.warning(f"Sample map load failed: {e}")

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # ── 상단: 파일 선택 + 날짜 ───────────────────────────────────
        top_group = QGroupBox("HTML 리포트 선택")
        form = QFormLayout(top_group)
        form.setSpacing(4)
        form.setContentsMargins(8, 6, 8, 6)

        file_row = QHBoxLayout()
        self._file_edit = QLineEdit()
        self._file_edit.setPlaceholderText("QC_Report_rawdata_*.html")
        self._file_edit.setReadOnly(True)
        file_row.addWidget(self._file_edit)
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_html)
        file_row.addWidget(btn_browse)
        form.addRow("HTML Report:", file_row)

        self._date_edit = QDateEdit(QDate.currentDate())
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setFixedWidth(120)
        form.addRow("Run Date:", self._date_edit)

        root.addWidget(top_group)

        # ── 중단: 파싱 결과 테이블 ───────────────────────────────────
        preview_label = QLabel("파싱 결과 미리보기 — Sample 열에서 수동 수정 가능")
        preview_label.setStyleSheet("color: #555; font-style: italic;")
        root.addWidget(preview_label)

        self._table = QTableWidget()
        self._table.setColumnCount(len(SEQ_COLS))
        self._table.setHorizontalHeaderLabels(SEQ_COLS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(180)
        root.addWidget(self._table, stretch=1)

        # ── 하단: 버튼 바 ────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        self._btn_import = QPushButton("Import")
        self._btn_import.setDefault(True)
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._on_import)
        btn_bar.addWidget(self._btn_import)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_bar.addWidget(btn_close)
        root.addLayout(btn_bar)

    # ── 이벤트 ───────────────────────────────────────────────────────

    def _browse_html(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select QC Report HTML", "", "HTML Files (*.html *.htm)"
        )
        if not path:
            return
        self._file_edit.setText(path)
        self._parse_and_preview(path)

    def _parse_and_preview(self, path: str):
        try:
            self._parsed_rows = parse_revio_qc_report(path)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"HTML 파싱 실패:\n{e}")
            self._parsed_rows = []
            self._table.setRowCount(0)
            self._btn_import.setEnabled(False)
            return

        self._fill_table()
        self._btn_import.setEnabled(bool(self._parsed_rows))

    def _fill_table(self):
        self._table.setRowCount(0)
        # Sample 콤보를 위해 편집 가능하게
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self._sample_combos: list[QComboBox] = []

        bold = QFont(); bold.setBold(True)

        for row_idx, r in enumerate(self._parsed_rows):
            self._table.insertRow(row_idx)

            # 0: Barcode
            self._table.setItem(row_idx, 0, QTableWidgetItem(r['barcode_id'] or ''))

            # 1: Sample (QComboBox — 자동매칭 + 수동 수정)
            combo = QComboBox()
            combo.addItem("")
            for sid in self._all_sample_ids:
                combo.addItem(sid)
            matched = self._sample_map.get(r['barcode_id'], '')
            if matched:
                idx = combo.findText(matched)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._sample_combos.append(combo)
            self._table.setCellWidget(row_idx, 1, combo)

            # 2~3: SMRT Cell, Run ID
            self._table.setItem(row_idx, 2, QTableWidgetItem(r['smrt_cell'] or ''))
            run_short = (r['run_id'] or '')[:25]
            self._table.setItem(row_idx, 3, QTableWidgetItem(run_short))

            # 4~10: 수치
            nums = [
                r['hifi_yield_gb'], r['coverage_x'], r['read_length_n50_kb'],
                r['read_length_mean_kb'], r['read_quality_q'], r['q30_pct'], r['zmw_p1_pct'],
            ]
            for col_offset, val in enumerate(nums):
                txt = f"{val:.1f}" if val is not None else '-'
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row_idx, 4 + col_offset, item)

            # 11: Status
            status = r.get('status', 'No Data')
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(_STATUS_COLOR.get(status, '#9E9E9E')))
            status_item.setFont(bold)
            self._table.setItem(row_idx, 11, status_item)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def _on_import(self):
        if not self._parsed_rows:
            return

        qd = self._date_edit.date()
        measured_at = datetime(qd.year(), qd.month(), qd.day())

        success = 0
        skipped = []

        try:
            with db_manager.session_scope() as session:
                for row_idx, r in enumerate(self._parsed_rows):
                    combo = self._sample_combos[row_idx]
                    sample_id = combo.currentText().strip()
                    if not sample_id:
                        skipped.append(r['barcode_id'])
                        continue

                    data = {
                        'sample_id':           sample_id,
                        'run_id':              r['run_id'],
                        'smrt_cell':           r['smrt_cell'],
                        'barcode_id':          r['barcode_id'],
                        'measured_at':         measured_at,
                        'hifi_reads_m':        r['hifi_reads_m'],
                        'hifi_yield_gb':       r['hifi_yield_gb'],
                        'coverage_x':          r['coverage_x'],
                        'read_length_mean_kb': r['read_length_mean_kb'],
                        'read_length_n50_kb':  r['read_length_n50_kb'],
                        'read_quality_q':      r['read_quality_q'],
                        'q30_pct':             r['q30_pct'],
                        'zmw_p1_pct':          r['zmw_p1_pct'],
                        'missing_adapter_pct': r['missing_adapter_pct'],
                        'mean_passes':         r['mean_passes'],
                        'control_reads':       r['control_reads'],
                        'control_rl_mean_kb':  r['control_rl_mean_kb'],
                        'status':              r['status'],
                    }
                    add_sequencing_result(session, data)
                    success += 1

        except Exception as e:
            logger.error(f"Sequencing result import failed: {e}")
            QMessageBox.critical(self, "Import Error", f"저장 실패:\n{e}")
            return

        msg = f"{success}개 샘플 시퀀싱 결과 저장 완료."
        if skipped:
            msg += f"\n\nSample 미지정으로 건너뜀: {', '.join(skipped)}"
        QMessageBox.information(self, "Import Complete", msg)
        self.accept()
