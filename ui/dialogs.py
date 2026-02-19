"""
다이얼로그 모음 - SampleDialog, NanoDropDialog, QubitDialog, FemtoPulseDialog
"""
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QLabel, QPushButton, QDialogButtonBox,
    QFileDialog, QTableWidget, QTableWidgetItem, QMessageBox,
    QHeaderView, QDoubleSpinBox, QTextEdit,
)
from PyQt5.QtCore import Qt
import logging

from config.settings import SAMPLE_TYPES, QC_STEPS
from database import (
    db_manager, add_sample, get_sample_by_id, update_sample,
    add_qc_metric, get_qc_metrics_by_sample, add_raw_trace,
    get_qc_metric_by_id, update_qc_metric,
)
from parsers import parse_femtopulse_file

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
        except Exception as e:
            logger.error(f"Failed to load metric: {e}")

    def _on_accept(self):
        step = self.step_combo.currentText()
        r230 = self.r230_spin.value() if self.r230_spin.value() > 0 else None

        data = {
            "step": step,
            "concentration": self.conc_spin.value(),
            "purity_260_280": self.r280_spin.value(),
            "purity_260_230": r230,
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

        data = {
            "step": step,
            "concentration": self.conc_spin.value(),
            "volume": self.vol_spin.value(),
            "total_amount": total,
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
    """Femto Pulse 파일 업로드 다이얼로그"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Femto Pulse Upload")
        self.setMinimumSize(700, 500)
        self.parsed_results = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # File selection row
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText("Select CSV or XML file...")
        file_row.addWidget(self.file_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Step selection
        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Step:"))
        self.step_combo = QComboBox()
        for s in QC_STEPS:
            self.step_combo.addItem(s)
        step_row.addWidget(self.step_combo)
        step_row.addStretch()
        layout.addLayout(step_row)

        # Preview table
        layout.addWidget(QLabel("Parsed Results:"))
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(6)
        self.preview_table.setHorizontalHeaderLabels([
            "File Sample ID", "DB Sample ID", "GQN", "Conc", "Avg Size", "Peak Size"
        ])
        self.preview_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        layout.addWidget(self.preview_table)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        layout.addWidget(buttons)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Femto Pulse File", "",
            "Data Files (*.csv *.xml);;All Files (*)",
        )
        if not path:
            return

        self.file_edit.setText(path)
        try:
            self.parsed_results = parse_femtopulse_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse file:\n{e}")
            self.parsed_results = []
            return

        if not self.parsed_results:
            QMessageBox.information(self, "No Data", "No results found in file.")
            return

        self._populate_preview()
        self.ok_button.setEnabled(True)

    def _populate_preview(self):
        self.preview_table.setRowCount(len(self.parsed_results))
        for row, r in enumerate(self.parsed_results):
            file_sid = r.get("sample_id", "")
            self.preview_table.setItem(row, 0, QTableWidgetItem(file_sid))

            # Editable DB sample ID — defaults to file sample ID
            db_id_item = QTableWidgetItem(file_sid)
            self.preview_table.setItem(row, 1, db_id_item)

            def _fmt(v):
                return f"{v:.2f}" if v is not None else "-"

            gqn_item = QTableWidgetItem(_fmt(r.get("gqn_rin")))
            gqn_item.setFlags(gqn_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 2, gqn_item)

            conc_item = QTableWidgetItem(_fmt(r.get("concentration")))
            conc_item.setFlags(conc_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 3, conc_item)

            avg_item = QTableWidgetItem(_fmt(r.get("avg_size")))
            avg_item.setFlags(avg_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 4, avg_item)

            peak_item = QTableWidgetItem(_fmt(r.get("peak_size")))
            peak_item.setFlags(peak_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 5, peak_item)

    def _on_accept(self):
        step = self.step_combo.currentText()
        file_path = self.file_edit.text()
        saved = 0
        skipped = []

        try:
            with db_manager.session_scope() as session:
                for row, r in enumerate(self.parsed_results):
                    db_sid_item = self.preview_table.item(row, 1)
                    db_sid = db_sid_item.text().strip() if db_sid_item else ""

                    if not db_sid:
                        continue

                    sample = get_sample_by_id(session, db_sid)
                    if not sample:
                        skipped.append(db_sid)
                        continue

                    add_qc_metric(session, {
                        "sample_id": db_sid,
                        "step": step,
                        "concentration": r.get("concentration"),
                        "gqn_rin": r.get("gqn_rin"),
                        "avg_size": r.get("avg_size"),
                        "peak_size": r.get("peak_size"),
                        "instrument": "Femto Pulse",
                        "data_file": file_path,
                    })
                    add_raw_trace(session, {
                        "sample_id": db_sid,
                        "step": step,
                        "raw_file_path": file_path,
                        "instrument_name": "Femto Pulse",
                    })
                    saved += 1

            msg = f"Saved {saved} record(s)."
            if skipped:
                msg += f"\nSkipped (not in DB): {', '.join(skipped)}"
            QMessageBox.information(self, "Complete", msg)
            self.accept()

        except Exception as e:
            logger.error(f"FemtoPulse save failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")
