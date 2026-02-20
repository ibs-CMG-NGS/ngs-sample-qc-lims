"""
Samples 탭 메인 위젯 - 샘플 목록 테이블 + QC 상세 테이블
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QLabel, QMessageBox, QAbstractItemView,
    QMenu, QAction, QDialog, QDialogButtonBox,
)
from PyQt5.QtCore import Qt
import logging

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
    HAS_MPL_QT = True
except ImportError:
    HAS_MPL_QT = False

from config.settings import QC_STEPS, STATUS_COLORS
from database import (
    db_manager, get_all_samples, get_latest_qc_metric,
    get_qc_metrics_by_sample, delete_qc_metric, delete_sample,
    get_smear_analyses_by_sample,
)
from ui.dialogs import SampleDialog, NanoDropDialog, QubitDialog, FemtoPulseDialog
from analysis.visualizer import load_electropherogram_traces, qc_visualizer

logger = logging.getLogger(__name__)

# Sample list columns
SAMPLE_COLS = ["Sample ID", "Name", "Species", "Material", "Type", "Created"]

# QC detail columns
QC_COLS = [
    "Step", "Instrument", "Conc", "Vol", "Total",
    "Recovery", "260/280", "GQN", "AvgSize",
    "1k-10k%", "10k-165k%",
    "Molarity", "Status", "Date",
]


def _fmt(val):
    """Format a numeric value for display."""
    if val is None:
        return "-"
    return f"{val:.2f}"


class SampleTab(QWidget):
    """Samples 탭 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_sample_id = None
        self._qc_metric_ids = []  # QC 테이블 행별 (metric_id, instrument)
        self._build_ui()
        self.refresh_samples()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Button bar
        btn_bar = QHBoxLayout()

        btn_new = QPushButton("New Sample")
        btn_new.clicked.connect(self.open_new_sample_dialog)
        btn_bar.addWidget(btn_new)

        btn_edit = QPushButton("Edit Sample")
        btn_edit.clicked.connect(self._open_edit_sample)
        btn_bar.addWidget(btn_edit)

        btn_nanodrop = QPushButton("NanoDrop")
        btn_nanodrop.clicked.connect(self._open_nanodrop)
        btn_bar.addWidget(btn_nanodrop)

        btn_qubit = QPushButton("Qubit")
        btn_qubit.clicked.connect(self._open_qubit)
        btn_bar.addWidget(btn_qubit)

        btn_femto = QPushButton("Femto Pulse")
        btn_femto.clicked.connect(self._open_femtopulse)
        btn_bar.addWidget(btn_femto)

        btn_electro = QPushButton("Electropherogram")
        btn_electro.clicked.connect(self._open_electropherogram)
        btn_bar.addWidget(btn_electro)

        btn_bar.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh_samples)
        btn_bar.addWidget(btn_refresh)

        layout.addLayout(btn_bar)

        # Splitter: top = sample list, bottom = QC details
        splitter = QSplitter(Qt.Vertical)

        # --- Top: sample list ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(QLabel("Sample List"))

        self.sample_table = QTableWidget()
        self.sample_table.setColumnCount(len(SAMPLE_COLS))
        self.sample_table.setHorizontalHeaderLabels(SAMPLE_COLS)
        self.sample_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sample_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sample_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sample_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.sample_table.horizontalHeader().setStretchLastSection(True)
        self.sample_table.setSortingEnabled(True)
        self.sample_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sample_table.customContextMenuRequested.connect(self._on_sample_context_menu)
        self.sample_table.currentCellChanged.connect(self._on_sample_selected)
        self.sample_table.doubleClicked.connect(self._open_edit_sample)
        top_layout.addWidget(self.sample_table)

        splitter.addWidget(top_widget)

        # --- Bottom: QC detail ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_label = QLabel("QC Details")
        bottom_layout.addWidget(self.detail_label)

        self.qc_table = QTableWidget()
        self.qc_table.setColumnCount(len(QC_COLS))
        self.qc_table.setHorizontalHeaderLabels(QC_COLS)
        self.qc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qc_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.qc_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.qc_table.horizontalHeader().setStretchLastSection(True)
        self.qc_table.doubleClicked.connect(self._on_qc_double_click)
        self.qc_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.qc_table.customContextMenuRequested.connect(self._on_qc_context_menu)
        bottom_layout.addWidget(self.qc_table)

        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    # ── Data loading ─────────────────────────────────────────────────

    def refresh_samples(self):
        """DB에서 샘플 목록을 로드하여 테이블 갱신."""
        self.sample_table.setSortingEnabled(False)
        self.sample_table.setRowCount(0)
        self.qc_table.setRowCount(0)
        self._selected_sample_id = None
        self.detail_label.setText("QC Details")

        try:
            with db_manager.session_scope() as session:
                samples = get_all_samples(session)
                self.sample_table.setRowCount(len(samples))

                for row, s in enumerate(samples):
                    self.sample_table.setItem(
                        row, 0, QTableWidgetItem(s.sample_id)
                    )
                    self.sample_table.setItem(
                        row, 1, QTableWidgetItem(s.sample_name or "")
                    )
                    self.sample_table.setItem(
                        row, 2, QTableWidgetItem(
                            getattr(s, 'species', None) or ""
                        )
                    )
                    self.sample_table.setItem(
                        row, 3, QTableWidgetItem(
                            getattr(s, 'material', None) or ""
                        )
                    )
                    self.sample_table.setItem(
                        row, 4, QTableWidgetItem(s.sample_type or "")
                    )

                    created = (
                        s.created_at.strftime("%Y-%m-%d")
                        if s.created_at
                        else "-"
                    )
                    self.sample_table.setItem(
                        row, 5, QTableWidgetItem(created)
                    )

        except Exception as e:
            logger.error(f"Failed to load samples: {e}")
        finally:
            self.sample_table.setSortingEnabled(True)

    def _on_sample_context_menu(self, pos):
        """Sample list 우클릭 컨텍스트 메뉴."""
        row = self.sample_table.rowAt(pos.y())
        if row < 0:
            return
        item = self.sample_table.item(row, 0)
        if not item:
            return
        sample_id = item.text()

        menu = QMenu(self)

        edit_action = QAction("Edit Sample", self)
        edit_action.triggered.connect(lambda: self._edit_sample_by_id(sample_id))
        menu.addAction(edit_action)

        menu.addSeparator()

        nd_action = QAction("NanoDrop", self)
        nd_action.triggered.connect(lambda: self._open_nanodrop_for(sample_id))
        menu.addAction(nd_action)

        qb_action = QAction("Qubit", self)
        qb_action.triggered.connect(lambda: self._open_qubit_for(sample_id))
        menu.addAction(qb_action)

        fp_action = QAction("Femto Pulse", self)
        fp_action.triggered.connect(self._open_femtopulse)
        menu.addAction(fp_action)

        ep_action = QAction("View Electropherogram", self)
        ep_action.triggered.connect(lambda: self._show_electropherogram_for(sample_id))
        menu.addAction(ep_action)

        menu.addSeparator()

        del_action = QAction("Delete Sample", self)
        del_action.triggered.connect(lambda: self._delete_sample(sample_id))
        menu.addAction(del_action)

        menu.exec_(self.sample_table.viewport().mapToGlobal(pos))

    def _edit_sample_by_id(self, sample_id):
        dlg = SampleDialog(self, edit_sample_id=sample_id)
        if dlg.exec_() == SampleDialog.Accepted:
            self.refresh_samples()

    def _open_nanodrop_for(self, sample_id):
        dlg = NanoDropDialog(sample_id, self)
        if dlg.exec_() == NanoDropDialog.Accepted:
            self._selected_sample_id = sample_id
            self._load_qc_details(sample_id)

    def _open_qubit_for(self, sample_id):
        dlg = QubitDialog(sample_id, self)
        if dlg.exec_() == QubitDialog.Accepted:
            self._selected_sample_id = sample_id
            self._load_qc_details(sample_id)

    def _delete_sample(self, sample_id):
        reply = QMessageBox.question(
            self, "Delete Sample",
            f"Delete sample '{sample_id}' and all its QC data?\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            with db_manager.session_scope() as session:
                delete_sample(session, sample_id)
            self.refresh_samples()
        except Exception as e:
            logger.error(f"Failed to delete sample: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete:\n{e}")

    def _on_sample_selected(self, row, _col, _prev_row, _prev_col):
        """샘플 행 클릭 시 하단 QC 상세 갱신."""
        if row < 0:
            return
        item = self.sample_table.item(row, 0)
        if not item:
            return
        sample_id = item.text()
        self._selected_sample_id = sample_id
        self._load_qc_details(sample_id)

    def _load_qc_details(self, sample_id):
        """선택된 샘플의 QC metrics를 로드하여 하단 테이블에 표시."""
        self.detail_label.setText(f"QC Details - {sample_id}")
        self.qc_table.setRowCount(0)
        self._qc_metric_ids = []

        try:
            with db_manager.session_scope() as session:
                metrics = get_qc_metrics_by_sample(session, sample_id)
                if not metrics:
                    return

                # Pre-load smear analyses grouped by step
                smear_all = get_smear_analyses_by_sample(session, sample_id)
                smear_by_step = {}  # step -> {range_text: SmearAnalysis}
                for sa in smear_all:
                    smear_by_step.setdefault(sa.step, {})[sa.range_text or ''] = sa

                self.qc_table.setRowCount(len(metrics))
                recoveries = self._calc_recovery(metrics)

                for row, m in enumerate(metrics):
                    self._qc_metric_ids.append((m.id, m.instrument))
                    self.qc_table.setItem(
                        row, 0, QTableWidgetItem(m.step or "-")
                    )
                    self.qc_table.setItem(
                        row, 1, QTableWidgetItem(m.instrument or "-")
                    )
                    self.qc_table.setItem(
                        row, 2, QTableWidgetItem(_fmt(m.concentration))
                    )
                    self.qc_table.setItem(
                        row, 3, QTableWidgetItem(_fmt(m.volume))
                    )
                    self.qc_table.setItem(
                        row, 4, QTableWidgetItem(_fmt(m.total_amount))
                    )
                    self.qc_table.setItem(
                        row, 5, QTableWidgetItem(recoveries[row])
                    )
                    self.qc_table.setItem(
                        row, 6, QTableWidgetItem(_fmt(m.purity_260_280))
                    )
                    self.qc_table.setItem(
                        row, 7, QTableWidgetItem(_fmt(m.gqn_rin))
                    )
                    self.qc_table.setItem(
                        row, 8, QTableWidgetItem(_fmt(m.avg_size))
                    )

                    # Smear %Total columns (Femto Pulse only)
                    pct_1k_10k = "-"
                    pct_10k_165k = "-"
                    step_smears = smear_by_step.get(m.step, {})
                    if m.instrument == 'Femto Pulse' and step_smears:
                        for rng, sa in step_smears.items():
                            if '1000' in rng and '10000' in rng and '165' not in rng:
                                pct_1k_10k = _fmt(sa.pct_total)
                            elif '10000' in rng and '165' in rng:
                                pct_10k_165k = _fmt(sa.pct_total)
                    self.qc_table.setItem(row, 9, QTableWidgetItem(pct_1k_10k))
                    self.qc_table.setItem(row, 10, QTableWidgetItem(pct_10k_165k))

                    self.qc_table.setItem(
                        row, 11, QTableWidgetItem(_fmt(m.molarity))
                    )

                    status_text = m.status or "-"
                    status_item = QTableWidgetItem(status_text)
                    color = STATUS_COLORS.get(status_text)
                    if color:
                        from PyQt5.QtGui import QColor
                        status_item.setForeground(QColor(color))
                    self.qc_table.setItem(row, 12, status_item)

                    date_str = (
                        m.measured_at.strftime("%Y-%m-%d")
                        if m.measured_at
                        else "-"
                    )
                    self.qc_table.setItem(
                        row, 13, QTableWidgetItem(date_str)
                    )

        except Exception as e:
            logger.error(f"Failed to load QC details: {e}")

    @staticmethod
    def _calc_recovery(metrics):
        """step별 recovery rate 계산 (CLI menu_status 로직 재사용)."""
        prev_total_map = {}
        results = []
        for m in metrics:
            recovery_str = "-"
            if m.total_amount is not None:
                step_idx = (
                    QC_STEPS.index(m.step) if m.step in QC_STEPS else -1
                )
                if step_idx > 0:
                    prev_step = QC_STEPS[step_idx - 1]
                    prev_total = prev_total_map.get(prev_step)
                    if prev_total is not None and prev_total > 0:
                        recovery_str = (
                            f"{(m.total_amount / prev_total) * 100:.1f}%"
                        )
                prev_total_map[m.step] = m.total_amount
            results.append(recovery_str)
        return results

    # ── Dialog openers ───────────────────────────────────────────────

    def open_new_sample_dialog(self):
        """새 샘플 등록 다이얼로그."""
        dlg = SampleDialog(self)
        if dlg.exec_() == SampleDialog.Accepted:
            self.refresh_samples()

    def _open_edit_sample(self):
        """선택된 샘플 편집 다이얼로그."""
        sample_id = self._get_selected_sample_id()
        if not sample_id:
            return
        dlg = SampleDialog(self, edit_sample_id=sample_id)
        if dlg.exec_() == SampleDialog.Accepted:
            self.refresh_samples()

    def _get_selected_sample_id(self):
        """현재 선택된 sample_id 반환. 없으면 경고 후 None."""
        if not self._selected_sample_id:
            QMessageBox.information(
                self, "No Selection", "Please select a sample first."
            )
            return None
        return self._selected_sample_id

    def _open_nanodrop(self):
        sample_id = self._get_selected_sample_id()
        if not sample_id:
            return
        dlg = NanoDropDialog(sample_id, self)
        if dlg.exec_() == NanoDropDialog.Accepted:
            self._load_qc_details(sample_id)

    def _open_qubit(self):
        sample_id = self._get_selected_sample_id()
        if not sample_id:
            return
        dlg = QubitDialog(sample_id, self)
        if dlg.exec_() == QubitDialog.Accepted:
            self._load_qc_details(sample_id)

    def _on_qc_context_menu(self, pos):
        """QC 상세 테이블 우클릭 컨텍스트 메뉴."""
        row = self.qc_table.rowAt(pos.y())
        if row < 0 or row >= len(self._qc_metric_ids):
            return

        metric_id, instrument = self._qc_metric_ids[row]
        step_item = self.qc_table.item(row, 0)
        step_text = step_item.text() if step_item else ""

        menu = QMenu(self)

        if instrument in ("NanoDrop", "Qubit"):
            edit_action = QAction("Edit", self)
            edit_action.triggered.connect(
                lambda: self._edit_qc_row(row)
            )
            menu.addAction(edit_action)

        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(
            lambda: self._delete_qc_row(metric_id, instrument, step_text)
        )
        menu.addAction(delete_action)

        menu.exec_(self.qc_table.viewport().mapToGlobal(pos))

    def _edit_qc_row(self, row):
        """컨텍스트 메뉴에서 Edit 선택 시."""
        from PyQt5.QtCore import QModelIndex
        index = self.qc_table.model().index(row, 0)
        self._on_qc_double_click(index)

    def _delete_qc_row(self, metric_id, instrument, step_text):
        """QC 측정값 삭제."""
        reply = QMessageBox.question(
            self, "Delete QC Metric",
            f"Delete {instrument} measurement at '{step_text}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            with db_manager.session_scope() as session:
                delete_qc_metric(session, metric_id)
            if self._selected_sample_id:
                self._load_qc_details(self._selected_sample_id)
        except Exception as e:
            logger.error(f"Failed to delete QC metric: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete:\n{e}")

    def _on_qc_double_click(self, index):
        """QC 상세 테이블 더블클릭 → NanoDrop/Qubit 편집 다이얼로그."""
        row = index.row()
        if row < 0 or row >= len(self._qc_metric_ids):
            return
        metric_id, instrument = self._qc_metric_ids[row]
        sample_id = self._selected_sample_id
        if not sample_id:
            return

        if instrument == "NanoDrop":
            dlg = NanoDropDialog(sample_id, self, edit_metric_id=metric_id)
        elif instrument == "Qubit":
            dlg = QubitDialog(sample_id, self, edit_metric_id=metric_id)
        else:
            QMessageBox.information(
                self, "Info",
                f"{instrument} measurements cannot be edited here.",
            )
            return

        if dlg.exec_() == dlg.Accepted:
            self._load_qc_details(sample_id)

    def _open_femtopulse(self):
        dlg = FemtoPulseDialog(self)
        if dlg.exec_() == FemtoPulseDialog.Accepted:
            self.refresh_samples()
            if self._selected_sample_id:
                self._load_qc_details(self._selected_sample_id)

    def _open_electropherogram(self):
        sample_id = self._get_selected_sample_id()
        if not sample_id:
            return
        self._show_electropherogram_for(sample_id)

    def _show_electropherogram_for(self, sample_id):
        """Load traces and display electropherogram overlay in a dialog."""
        if not HAS_MPL_QT:
            QMessageBox.warning(
                self, "Missing Dependency",
                "matplotlib Qt5 backend is required for electropherogram display.",
            )
            return

        traces, ladder_points = load_electropherogram_traces(sample_id)
        if not traces:
            QMessageBox.information(
                self, "No Data",
                f"No electropherogram traces found for '{sample_id}'.\n"
                "Upload Femto Pulse data with an Electropherogram file first.",
            )
            return

        fig = qc_visualizer.plot_electropherogram_overlay(
            sample_id, traces, ladder_points=ladder_points
        )
        if fig is None:
            return

        # Create a dialog with embedded matplotlib canvas
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Electropherogram - {sample_id}")
        dlg.setMinimumSize(900, 600)

        layout = QVBoxLayout(dlg)

        canvas = FigureCanvas(fig)
        toolbar = NavigationToolbar(canvas, dlg)
        layout.addWidget(toolbar)
        layout.addWidget(canvas)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec_()
