"""
다이얼로그 모음 - SampleDialog, NanoDropDialog, QubitDialog, FemtoPulseDialog
"""
import os
from datetime import date, datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QLabel, QPushButton, QDialogButtonBox,
    QFileDialog, QTableWidget, QTableWidgetItem, QMessageBox,
    QHeaderView, QDoubleSpinBox, QTextEdit, QAbstractItemView,
    QDateEdit,
)
from PyQt5.QtCore import Qt, QDate
import logging

from config.settings import SAMPLE_TYPES, QC_STEPS
from database import (
    db_manager, add_sample, get_sample_by_id, update_sample,
    add_qc_metric, get_qc_metrics_by_sample, add_raw_trace,
    get_qc_metric_by_id, update_qc_metric,
    add_femtopulse_run, add_smear_analysis,
)
from parsers import (
    parse_femtopulse_file,
    scan_femtopulse_folder,
    parse_quality_table,
    parse_smear_analysis,
    parse_femtopulse_folder,
    _strip_samp_prefix,
)

logger = logging.getLogger(__name__)


class SampleDialog(QDialog):
    """샘플 등록/수정 다이얼로그

    Args:
        parent: parent widget
        edit_sample_id: 수정할 샘플 ID. None이면 신규 등록 모드.
    """

    def __init__(self, parent=None, edit_sample_id=None):
        super().__init__(parent)
        self._edit_sample_id = edit_sample_id
        self.setWindowTitle("Edit Sample" if edit_sample_id else "New Sample")
        self.setMinimumWidth(400)
        self._build_ui()
        if edit_sample_id:
            self._load_sample(edit_sample_id)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.sample_id_edit = QLineEdit()
        self.sample_id_edit.setPlaceholderText("Required")
        form.addRow("Sample ID:", self.sample_id_edit)

        self.sample_name_edit = QLineEdit()
        form.addRow("Sample Name:", self.sample_name_edit)

        self.type_combo = QComboBox()
        for key, desc in SAMPLE_TYPES.items():
            self.type_combo.addItem(f"{key} ({desc})", key)
        form.addRow("Sample Type:", self.type_combo)

        self.source_edit = QLineEdit()
        form.addRow("Source:", self.source_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        form.addRow("Description:", self.desc_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_sample(self, sample_id):
        """편집 모드: 기존 샘플 데이터 로드."""
        try:
            with db_manager.session_scope() as session:
                sample = get_sample_by_id(session, sample_id)
                if not sample:
                    return
                self.sample_id_edit.setText(sample.sample_id)
                self.sample_id_edit.setReadOnly(True)
                self.sample_name_edit.setText(sample.sample_name or "")
                # type combo
                idx = self.type_combo.findData(sample.sample_type)
                if idx >= 0:
                    self.type_combo.setCurrentIndex(idx)
                self.source_edit.setText(sample.source or "")
                self.desc_edit.setPlainText(sample.description or "")
        except Exception as e:
            logger.error(f"Failed to load sample: {e}")

    def _on_accept(self):
        sample_id = self.sample_id_edit.text().strip()
        if not sample_id:
            QMessageBox.warning(self, "Validation", "Sample ID is required.")
            return

        data = {
            "sample_name": self.sample_name_edit.text().strip() or None,
            "sample_type": self.type_combo.currentData(),
            "source": self.source_edit.text().strip() or None,
            "description": self.desc_edit.toPlainText().strip() or None,
        }

        try:
            with db_manager.session_scope() as session:
                if self._edit_sample_id:
                    # 수정 모드
                    update_sample(session, self._edit_sample_id, data)
                else:
                    # 신규 등록 모드
                    if get_sample_by_id(session, sample_id):
                        QMessageBox.warning(
                            self, "Duplicate",
                            f"Sample ID '{sample_id}' already exists.",
                        )
                        return
                    data["sample_id"] = sample_id
                    add_sample(session, data)
            self.accept()
        except Exception as e:
            logger.error(f"Failed to save sample: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save sample:\n{e}")


class NanoDropDialog(QDialog):
    """NanoDrop 측정값 입력/수정 다이얼로그

    Args:
        sample_id: 샘플 ID
        parent: parent widget
        edit_metric_id: 수정할 QCMetric PK. None이면 신규 입력 모드.
    """

    def __init__(self, sample_id, parent=None, edit_metric_id=None):
        super().__init__(parent)
        self.sample_id = sample_id
        self._edit_metric_id = edit_metric_id
        title = "Edit NanoDrop" if edit_metric_id else "NanoDrop"
        self.setWindowTitle(f"{title} - {sample_id}")
        self.setMinimumWidth(350)
        self._build_ui()
        if edit_metric_id:
            self._load_metric(edit_metric_id)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.conc_spin = QDoubleSpinBox()
        self.conc_spin.setRange(0, 99999)
        self.conc_spin.setDecimals(2)
        self.conc_spin.setSuffix(" ng/ul")
        form.addRow("Concentration:", self.conc_spin)

        self.r280_spin = QDoubleSpinBox()
        self.r280_spin.setRange(0, 9.99)
        self.r280_spin.setDecimals(2)
        self.r280_spin.setValue(1.80)
        form.addRow("260/280:", self.r280_spin)

        self.r230_spin = QDoubleSpinBox()
        self.r230_spin.setRange(0, 9.99)
        self.r230_spin.setDecimals(2)
        self.r230_spin.setSpecialValueText("N/A")
        form.addRow("260/230:", self.r230_spin)

        self.step_combo = QComboBox()
        for s in QC_STEPS:
            self.step_combo.addItem(s)
        form.addRow("Step:", self.step_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Measured Date:", self.date_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_metric(self, metric_id):
        """편집 모드: 기존 측정값 로드."""
        try:
            with db_manager.session_scope() as session:
                m = get_qc_metric_by_id(session, metric_id)
                if not m:
                    return
                if m.concentration is not None:
                    self.conc_spin.setValue(m.concentration)
                if m.purity_260_280 is not None:
                    self.r280_spin.setValue(m.purity_260_280)
                if m.purity_260_230 is not None:
                    self.r230_spin.setValue(m.purity_260_230)
                idx = self.step_combo.findText(m.step)
                if idx >= 0:
                    self.step_combo.setCurrentIndex(idx)
                if m.measured_at:
                    self.date_edit.setDate(QDate(
                        m.measured_at.year, m.measured_at.month, m.measured_at.day
                    ))
        except Exception as e:
            logger.error(f"Failed to load metric: {e}")

    def _on_accept(self):
        step = self.step_combo.currentText()
        r230 = self.r230_spin.value() if self.r230_spin.value() > 0 else None
        qd = self.date_edit.date()
        measured_at = datetime(qd.year(), qd.month(), qd.day())

        data = {
            "step": step,
            "concentration": self.conc_spin.value(),
            "purity_260_280": self.r280_spin.value(),
            "purity_260_230": r230,
            "measured_at": measured_at,
        }

        try:
            with db_manager.session_scope() as session:
                if self._edit_metric_id:
                    update_qc_metric(session, self._edit_metric_id, data)
                else:
                    data["sample_id"] = self.sample_id
                    data["instrument"] = "NanoDrop"
                    add_qc_metric(session, data)
            self.accept()
        except Exception as e:
            logger.error(f"NanoDrop save failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")


class QubitDialog(QDialog):
    """Qubit 측정값 입력/수정 다이얼로그

    Args:
        sample_id: 샘플 ID
        parent: parent widget
        edit_metric_id: 수정할 QCMetric PK. None이면 신규 입력 모드.
    """

    def __init__(self, sample_id, parent=None, edit_metric_id=None):
        super().__init__(parent)
        self.sample_id = sample_id
        self._edit_metric_id = edit_metric_id
        title = "Edit Qubit" if edit_metric_id else "Qubit"
        self.setWindowTitle(f"{title} - {sample_id}")
        self.setMinimumWidth(380)
        self._build_ui()
        if edit_metric_id:
            self._load_metric(edit_metric_id)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.conc_spin = QDoubleSpinBox()
        self.conc_spin.setRange(0, 99999)
        self.conc_spin.setDecimals(2)
        self.conc_spin.setSuffix(" ng/ul")
        self.conc_spin.valueChanged.connect(self._update_total)
        form.addRow("Concentration:", self.conc_spin)

        self.vol_spin = QDoubleSpinBox()
        self.vol_spin.setRange(0, 99999)
        self.vol_spin.setDecimals(1)
        self.vol_spin.setSuffix(" ul")
        self.vol_spin.valueChanged.connect(self._update_total)
        form.addRow("Volume:", self.vol_spin)

        self.total_label = QLabel("0.00 ng")
        self.total_label.setStyleSheet("font-weight: bold;")
        form.addRow("Total Amount:", self.total_label)

        self.assay_edit = QLineEdit()
        self.assay_edit.setPlaceholderText("e.g. dsDNA HS, RNA HS")
        form.addRow("Assay Type:", self.assay_edit)

        self.step_combo = QComboBox()
        for s in QC_STEPS:
            self.step_combo.addItem(s)
        self.step_combo.currentIndexChanged.connect(self._update_recovery)
        form.addRow("Step:", self.step_combo)

        self.recovery_label = QLabel("-")
        form.addRow("Recovery:", self.recovery_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow("Measured Date:", self.date_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_metric(self, metric_id):
        """편집 모드: 기존 측정값 로드."""
        try:
            with db_manager.session_scope() as session:
                m = get_qc_metric_by_id(session, metric_id)
                if not m:
                    return
                if m.concentration is not None:
                    self.conc_spin.setValue(m.concentration)
                if m.volume is not None:
                    self.vol_spin.setValue(m.volume)
                idx = self.step_combo.findText(m.step)
                if idx >= 0:
                    self.step_combo.setCurrentIndex(idx)
                if m.measured_at:
                    self.date_edit.setDate(QDate(
                        m.measured_at.year, m.measured_at.month, m.measured_at.day
                    ))
        except Exception as e:
            logger.error(f"Failed to load metric: {e}")

    def _get_total(self):
        return self.conc_spin.value() * self.vol_spin.value()

    def _update_total(self):
        total = self._get_total()
        self.total_label.setText(f"{total:.2f} ng")
        self._update_recovery()

    def _update_recovery(self):
        total = self._get_total()
        step = self.step_combo.currentText()
        step_idx = QC_STEPS.index(step) if step in QC_STEPS else -1

        if step_idx <= 0 or total <= 0:
            self.recovery_label.setText("-")
            return

        prev_step = QC_STEPS[step_idx - 1]
        try:
            with db_manager.session_scope() as session:
                prev_metrics = [
                    m for m in get_qc_metrics_by_sample(session, self.sample_id)
                    if m.step == prev_step and m.total_amount is not None
                ]
                if prev_metrics:
                    prev_total = prev_metrics[-1].total_amount
                    if prev_total and prev_total > 0:
                        recovery = (total / prev_total) * 100
                        self.recovery_label.setText(
                            f"{recovery:.1f}%  ({prev_step} -> {step})"
                        )
                        return
        except Exception:
            pass

        self.recovery_label.setText(f"No data for {prev_step}")

    def _on_accept(self):
        total = self._get_total()
        step = self.step_combo.currentText()
        assay = self.assay_edit.text().strip() or None
        qd = self.date_edit.date()
        measured_at = datetime(qd.year(), qd.month(), qd.day())

        data = {
            "step": step,
            "concentration": self.conc_spin.value(),
            "volume": self.vol_spin.value(),
            "total_amount": total,
            "measured_at": measured_at,
        }

        try:
            with db_manager.session_scope() as session:
                if self._edit_metric_id:
                    update_qc_metric(session, self._edit_metric_id, data)
                else:
                    data["sample_id"] = self.sample_id
                    data["instrument"] = "Qubit"
                    add_qc_metric(session, data)
                    if assay:
                        add_raw_trace(session, {
                            "sample_id": self.sample_id,
                            "step": step,
                            "instrument_name": "Qubit",
                            "assay_type": assay,
                        })
            self.accept()
        except Exception as e:
            logger.error(f"Qubit save failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")


class FemtoPulseDialog(QDialog):
    """Femto Pulse 폴더 업로드 다이얼로그 — 5종 파일 일괄 처리"""

    _FILE_TYPES = [
        'quality_table', 'peak_table', 'electropherogram',
        'size_calibration', 'smear_analysis',
    ]
    _TYPE_LABELS = {
        'quality_table': 'Quality Table',
        'peak_table': 'Peak Table',
        'electropherogram': 'Electropherogram',
        'size_calibration': 'Size Calibration',
        'smear_analysis': 'Smear Analysis',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Femto Pulse Folder Upload")
        self.setMinimumSize(800, 600)
        self._folder_path = None
        self._file_map = {}          # {type: path}
        self._quality_rows = []      # parsed quality table rows
        self._folder_data = None     # full parse result
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Folder selection
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("Select Femto Pulse run folder...")
        folder_row.addWidget(self.folder_edit)

        browse_btn = QPushButton("Browse Folder")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)

        # Step + Date row
        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Step:"))
        self.step_combo = QComboBox()
        for s in QC_STEPS:
            self.step_combo.addItem(s)
        step_row.addWidget(self.step_combo)
        step_row.addSpacing(20)
        step_row.addWidget(QLabel("Measured Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        step_row.addWidget(self.date_edit)
        step_row.addStretch()
        layout.addLayout(step_row)

        # File checklist (5 rows)
        layout.addWidget(QLabel("Detected Files:"))
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(2)
        self.file_table.setHorizontalHeaderLabels(["File Type", "File Name"])
        self.file_table.setRowCount(5)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.file_table.setMaximumHeight(160)
        for row, ft in enumerate(self._FILE_TYPES):
            self.file_table.setItem(row, 0, QTableWidgetItem(self._TYPE_LABELS[ft]))
            self.file_table.setItem(row, 1, QTableWidgetItem("not found"))
        layout.addWidget(self.file_table)

        # Sample preview table
        layout.addWidget(QLabel("Sample Preview (from Quality Table):"))
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels([
            "Well", "File Sample", "DB Sample ID", "DQN", "Conc (ng/ul)",
        ])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.preview_table)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        layout.addWidget(buttons)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Femto Pulse Run Folder"
        )
        if not folder:
            return

        self._folder_path = folder
        self.folder_edit.setText(folder)

        # Scan files
        self._file_map = scan_femtopulse_folder(folder)
        for row, ft in enumerate(self._FILE_TYPES):
            path = self._file_map.get(ft)
            if path:
                from pathlib import Path as _P
                self.file_table.setItem(row, 1, QTableWidgetItem(_P(path).name))
            else:
                item = QTableWidgetItem("not found")
                item.setForeground(Qt.gray)
                self.file_table.setItem(row, 1, item)

        # Parse quality table for preview
        qt_path = self._file_map.get('quality_table')
        if qt_path:
            try:
                self._quality_rows = parse_quality_table(qt_path)
            except Exception as e:
                QMessageBox.warning(self, "Parse Warning",
                                    f"Failed to parse Quality Table:\n{e}")
                self._quality_rows = []
        else:
            self._quality_rows = []

        self._populate_preview()
        # Enable OK when quality table is loaded; actual import requires at least one DB Sample ID
        self.ok_button.setEnabled(len(self._quality_rows) > 0)

    def _populate_preview(self):
        self.preview_table.setRowCount(len(self._quality_rows))
        for row, r in enumerate(self._quality_rows):
            file_sid = r.get('sample_id', '')

            well_item = QTableWidgetItem(r.get('well', ''))
            well_item.setFlags(well_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 0, well_item)

            fsid_item = QTableWidgetItem(file_sid)
            fsid_item.setFlags(fsid_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 1, fsid_item)

            # DB Sample ID: blank by default — user fills in only samples to import
            db_id_item = QTableWidgetItem('')
            db_id_item.setToolTip("Enter DB Sample ID to import this row")
            self.preview_table.setItem(row, 2, db_id_item)

            def _fmt(v):
                return f"{v:.2f}" if v is not None else "-"

            dqn_item = QTableWidgetItem(_fmt(r.get('dqn')))
            dqn_item.setFlags(dqn_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 3, dqn_item)

            conc_item = QTableWidgetItem(_fmt(r.get('total_concentration')))
            conc_item.setFlags(conc_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 4, conc_item)

    def _on_accept(self):
        step = self.step_combo.currentText()
        qd = self.date_edit.date()
        measured_at = datetime(qd.year(), qd.month(), qd.day())
        saved = 0
        skipped = []
        smear_saved = 0

        try:
            with db_manager.session_scope() as session:
                # 1. Create FemtoPulseRun record
                run = add_femtopulse_run(session, {
                    'run_folder': self._folder_path,
                    'step': step,
                    'quality_table_path': self._file_map.get('quality_table'),
                    'peak_table_path': self._file_map.get('peak_table'),
                    'electropherogram_path': self._file_map.get('electropherogram'),
                    'size_calibration_path': self._file_map.get('size_calibration'),
                    'smear_analysis_path': self._file_map.get('smear_analysis'),
                })

                # Build file_sample_id -> db_sample_id mapping (only filled rows)
                sid_map = {}  # file_sample_id -> db_sample_id
                for row, r in enumerate(self._quality_rows):
                    db_sid_item = self.preview_table.item(row, 2)
                    db_sid = db_sid_item.text().strip() if db_sid_item else ""
                    file_sid = r.get('sample_id', '')
                    if db_sid:
                        sid_map[file_sid] = db_sid

                if not sid_map:
                    QMessageBox.warning(
                        self, "No Samples",
                        "Enter at least one DB Sample ID to import.",
                    )
                    return

                # Pre-parse smear analysis for avg_size lookup
                smear_by_file_sid = {}  # file_sid -> {range: row_dict}
                smear_path = self._file_map.get('smear_analysis')
                smear_rows_all = []
                if smear_path:
                    try:
                        smear_rows_all = parse_smear_analysis(smear_path)
                        for sr in smear_rows_all:
                            fsid = sr.get('sample_id', '')
                            rng = sr.get('range', '')
                            smear_by_file_sid.setdefault(fsid, {})[rng] = sr
                    except Exception as e:
                        logger.warning(f"Smear analysis pre-parse failed: {e}")

                # 2. Save QCMetric + RawTrace per sample
                electro_path = self._file_map.get('electropherogram')
                for row, r in enumerate(self._quality_rows):
                    file_sid = r.get('sample_id', '')
                    db_sid = sid_map.get(file_sid, '')
                    if not db_sid:
                        continue

                    sample = get_sample_by_id(session, db_sid)
                    if not sample:
                        skipped.append(db_sid)
                        continue

                    # Lookup avg_size from smear "10000 bp to 165000 bp" range
                    smear_ranges = smear_by_file_sid.get(file_sid, {})
                    avg_size = None
                    for rng_key, sr_data in smear_ranges.items():
                        if '10000' in rng_key and '165' in rng_key:
                            avg_size = sr_data.get('avg_size')
                            break

                    add_qc_metric(session, {
                        'sample_id': db_sid,
                        'step': step,
                        'concentration': r.get('total_concentration'),
                        'gqn_rin': r.get('dqn'),
                        'avg_size': avg_size,
                        'instrument': 'Femto Pulse',
                        'data_file': self._file_map.get('quality_table'),
                        'measured_at': measured_at,
                    })

                    if electro_path:
                        add_raw_trace(session, {
                            'sample_id': db_sid,
                            'step': step,
                            'raw_file_path': electro_path,
                            'image_path': file_sid,  # 원본 파일 Sample ID (컬럼 매칭용)
                            'instrument_name': 'Femto Pulse',
                            'assay_type': 'Electropherogram',
                        })
                    saved += 1

                # 3. Save Smear Analysis records (using pre-parsed data)
                if smear_rows_all:
                    try:
                        for sr in smear_rows_all:
                            file_sid = sr.get('sample_id', '')
                            db_sid = sid_map.get(file_sid, '')
                            if not db_sid:
                                continue
                            sample = get_sample_by_id(session, db_sid)
                            if not sample:
                                continue
                            add_smear_analysis(session, {
                                'sample_id': db_sid,
                                'step': step,
                                'run_id': run.id,
                                'range_text': sr.get('range'),
                                'pg_ul': sr.get('pg_ul'),
                                'pct_total': sr.get('pct_total'),
                                'pmol_l': sr.get('pmol_l'),
                                'avg_size': sr.get('avg_size'),
                                'cv': sr.get('cv'),
                                'threshold': sr.get('threshold'),
                                'dqn': sr.get('dqn'),
                            })
                            smear_saved += 1
                    except Exception as e:
                        logger.warning(f"Smear analysis save failed: {e}")

            msg = f"Saved {saved} QC record(s)."
            if smear_saved:
                msg += f"\nSmear Analysis: {smear_saved} record(s)."
            if skipped:
                msg += f"\nSkipped (not in DB): {', '.join(skipped)}"
            QMessageBox.information(self, "Complete", msg)
            self.accept()

        except Exception as e:
            logger.error(f"FemtoPulse save failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")
