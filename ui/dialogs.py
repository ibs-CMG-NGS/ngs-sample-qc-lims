"""
다이얼로그 모음 - SampleDialog, NanoDropDialog, QubitDialog, FemtoPulseDialog, NoteDialog
"""
import os
from datetime import date, datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QLabel, QPushButton, QDialogButtonBox,
    QFileDialog, QTableWidget, QTableWidgetItem, QMessageBox,
    QHeaderView, QDoubleSpinBox, QTextEdit, QAbstractItemView,
    QDateEdit, QListWidget, QListWidgetItem, QSplitter,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont
import logging

from config.settings import SAMPLE_TYPES, QC_STEPS, SPECIES_LIST, MATERIAL_LIST
from database import (
    db_manager, add_sample, get_sample_by_id, update_sample,
    add_qc_metric, get_qc_metrics_by_sample, add_raw_trace,
    get_qc_metric_by_id, update_qc_metric,
    add_femtopulse_run, add_smear_analysis,
    add_note, get_notes_by_sample, update_note, delete_note,
)
from analysis.qc_judge import qc_judge
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
        self.sample_name_edit.setPlaceholderText("Optional (memo / alias)")
        form.addRow("Sample Name:", self.sample_name_edit)

        self.species_combo = QComboBox()
        self.species_combo.setEditable(True)
        for sp in SPECIES_LIST:
            self.species_combo.addItem(sp)
        self.species_combo.addItem("Other")
        self.species_combo.setCurrentIndex(-1)
        self.species_combo.setPlaceholderText("Select or type...")  # Qt 5.15+
        form.addRow("Species:", self.species_combo)

        self.material_combo = QComboBox()
        self.material_combo.setEditable(True)
        for mt in MATERIAL_LIST:
            self.material_combo.addItem(mt)
        self.material_combo.setCurrentIndex(-1)
        self.material_combo.setPlaceholderText("Select or type...")
        form.addRow("Material:", self.material_combo)

        self.type_combo = QComboBox()
        for key, desc in SAMPLE_TYPES.items():
            self.type_combo.addItem(f"{key} ({desc})", key)
        form.addRow("Sample Type:", self.type_combo)

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
                if sample.species:
                    self.species_combo.setCurrentText(sample.species)
                if sample.material:
                    self.material_combo.setCurrentText(sample.material)
                idx = self.type_combo.findData(sample.sample_type)
                if idx >= 0:
                    self.type_combo.setCurrentIndex(idx)
                self.desc_edit.setPlainText(sample.description or "")
        except Exception as e:
            logger.error(f"Failed to load sample: {e}")

    def _on_accept(self):
        sample_id = self.sample_id_edit.text().strip()
        if not sample_id:
            QMessageBox.warning(self, "Validation", "Sample ID is required.")
            return

        species_text = self.species_combo.currentText().strip()
        material_text = self.material_combo.currentText().strip()

        data = {
            "sample_name": self.sample_name_edit.text().strip() or None,
            "species": species_text or None,
            "material": material_text or None,
            "sample_type": self.type_combo.currentData(),
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
                # QC 자동 판정
                sample = get_sample_by_id(session, self.sample_id)
                if sample:
                    data["status"] = qc_judge.judge_qc(sample.sample_type, {
                        "concentration": data["concentration"],
                        "step": step,
                    })
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
                # QC 자동 판정
                sample = get_sample_by_id(session, self.sample_id)
                if sample:
                    data["status"] = qc_judge.judge_qc(sample.sample_type, {
                        "concentration": data["concentration"],
                        "total_amount": total,
                        "step": step,
                    })
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

                    fp_qc_data = {
                        'concentration': r.get('total_concentration'),
                        'gqn_rin': r.get('dqn'),
                        'avg_size': avg_size,
                        'step': step,
                    }
                    fp_qc_data['status'] = qc_judge.judge_qc(
                        sample.sample_type, fp_qc_data
                    )
                    add_qc_metric(session, {
                        'sample_id': db_sid,
                        'step': step,
                        'concentration': fp_qc_data['concentration'],
                        'gqn_rin': fp_qc_data['gqn_rin'],
                        'avg_size': fp_qc_data['avg_size'],
                        'status': fp_qc_data['status'],
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


class NoteDialog(QDialog):
    """샘플 메모 관리 다이얼로그 — 목록 조회 / 추가 / 수정 / 삭제"""

    def __init__(self, sample_id: str, parent=None):
        super().__init__(parent)
        self.sample_id = sample_id
        self.setWindowTitle(f"Notes — {sample_id}")
        self.setMinimumSize(560, 400)
        self._note_ids: list[int] = []   # 목록 행 → DB id 매핑
        self._build_ui()
        self._load_notes()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── 목록 + 미리보기 스플리터 ──────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # 위: 노트 목록
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        splitter.addWidget(self.list_widget)

        # 아래: 선택된 노트 본문 미리보기 (읽기 전용)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("노트를 선택하면 내용이 표시됩니다.")
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # ── 버튼 바 ───────────────────────────────────────────────
        btn_row = QHBoxLayout()

        btn_add = QPushButton("Add Note")
        btn_add.clicked.connect(self._add_note)
        btn_row.addWidget(btn_add)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self._edit_note)
        self.btn_edit.setEnabled(False)
        btn_row.addWidget(self.btn_edit)

        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(self._delete_note)
        self.btn_del.setEnabled(False)
        btn_row.addWidget(self.btn_del)

        btn_row.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    # ── 데이터 ────────────────────────────────────────────────────

    def _load_notes(self):
        self.list_widget.clear()
        self._note_ids.clear()
        self.preview.clear()

        try:
            with db_manager.session_scope() as session:
                notes = get_notes_by_sample(session, self.sample_id)
                for note in notes:
                    # 목록 항목: 날짜 + 첫 줄 미리보기
                    date_str = note.created_at.strftime("%Y-%m-%d %H:%M") if note.created_at else ""
                    first_line = note.note_text.splitlines()[0][:60] if note.note_text else ""
                    if len(note.note_text or "") > 60 or "\n" in (note.note_text or ""):
                        first_line += " …"
                    self.list_widget.addItem(f"[{date_str}]  {first_line}")
                    self._note_ids.append((note.id, note.note_text))
        except Exception as e:
            logger.error(f"Note load failed: {e}")

        has = self.list_widget.count() > 0
        self.btn_edit.setEnabled(False)
        self.btn_del.setEnabled(False)

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._note_ids):
            self.preview.clear()
            self.btn_edit.setEnabled(False)
            self.btn_del.setEnabled(False)
            return
        _, text = self._note_ids[row]
        self.preview.setPlainText(text)
        self.btn_edit.setEnabled(True)
        self.btn_del.setEnabled(True)

    # ── 동작 ─────────────────────────────────────────────────────

    def _add_note(self):
        text, ok = self._input_dialog("Add Note", "")
        if not ok or not text.strip():
            return
        try:
            with db_manager.session_scope() as session:
                add_note(session, self.sample_id, text.strip())
            self._load_notes()
            # 방금 추가한 항목(최신순 0번)으로 선택 이동
            self.list_widget.setCurrentRow(0)
        except Exception as e:
            logger.error(f"Note add failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add note:\n{e}")

    def _edit_note(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._note_ids):
            return
        note_id, current_text = self._note_ids[row]
        text, ok = self._input_dialog("Edit Note", current_text)
        if not ok or not text.strip():
            return
        try:
            with db_manager.session_scope() as session:
                update_note(session, note_id, text.strip())
            self._load_notes()
            self.list_widget.setCurrentRow(row)
        except Exception as e:
            logger.error(f"Note edit failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to edit note:\n{e}")

    def _delete_note(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._note_ids):
            return
        note_id, _ = self._note_ids[row]
        reply = QMessageBox.question(
            self, "Delete Note", "이 메모를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            with db_manager.session_scope() as session:
                delete_note(session, note_id)
            self._load_notes()
        except Exception as e:
            logger.error(f"Note delete failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete note:\n{e}")

    @staticmethod
    def _input_dialog(title: str, initial: str) -> tuple[str, bool]:
        """여러 줄 텍스트 입력 다이얼로그."""
        dlg = QDialog()
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(440, 220)
        layout = QVBoxLayout(dlg)

        edit = QTextEdit()
        edit.setPlaceholderText("메모 내용을 입력하세요…")
        edit.setPlainText(initial)
        layout.addWidget(edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec_() == QDialog.Accepted:
            return edit.toPlainText(), True
        return "", False
