"""
Reports 탭 - 샘플별 QC 리포트 생성 및 내보내기
PDF : matplotlib PdfPages (추가 의존성 없음)
Excel: openpyxl
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import openpyxl
    from openpyxl.styles import Font as XlFont, PatternFill, Alignment, Border, Side
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

from config.settings import QC_STEPS, STATUS_COLORS, REPORTS_DIR
from database import (
    db_manager,
    get_all_samples,
    get_qc_metrics_by_sample,
    get_smear_analyses_by_sample,
)

logger = logging.getLogger(__name__)

_STATUS_HEX = STATUS_COLORS          # {"Pass": "#4CAF50", ...}
_STATUS_MPL = {                       # matplotlib-safe colours
    "Pass":    "#4CAF50",
    "Warning": "#FF9800",
    "Fail":    "#F44336",
    "No Data": "#9E9E9E",
}

# ── 선택 목록 컬럼 ──────────────────────────────────────────────────
_SEL_COLS = ["", "Sample ID", "Name", "Type", "Latest Status"]


def _fmt(val, decimals: int = 2) -> str:
    if val is None:
        return "-"
    return f"{val:.{decimals}f}"


# ════════════════════════════════════════════════════════════════════
# Reports 탭 메인 위젯
# ════════════════════════════════════════════════════════════════════

class ReportsTab(QWidget):
    """Reports 탭"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._samples_cache: list = []          # DB Sample objects (session 밖 snapshot)
        self._preview_sample_id: Optional[str] = None
        self._build_ui()
        self.refresh()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 헤더 바
        hdr = QHBoxLayout()
        title = QLabel("Reports")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        hdr.addWidget(title)
        hdr.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        hdr.addWidget(btn_refresh)

        self.btn_pdf = QPushButton("Export PDF (selected)")
        self.btn_pdf.clicked.connect(self._export_pdf)
        self.btn_pdf.setEnabled(HAS_MPL)
        hdr.addWidget(self.btn_pdf)

        self.btn_excel = QPushButton("Export Excel (selected)")
        self.btn_excel.clicked.connect(self._export_excel)
        self.btn_excel.setEnabled(HAS_OPENPYXL)
        hdr.addWidget(self.btn_excel)

        root.addLayout(hdr)

        # 좌우 스플리터
        splitter = QSplitter(Qt.Horizontal)
        self.splitter = splitter

        # ── 왼쪽: 샘플 선택 목록 ─────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # 검색 + 타입 필터
        filter_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search Sample ID…")
        self.search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.search_edit)

        self.type_filter = QComboBox()
        self.type_filter.addItem("All Types")
        self.type_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self.type_filter)
        left_layout.addLayout(filter_row)

        # 전체선택 / 해제
        sel_row = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self._select_all)
        sel_row.addWidget(btn_all)
        btn_none = QPushButton("Deselect All")
        btn_none.clicked.connect(self._deselect_all)
        sel_row.addWidget(btn_none)
        left_layout.addLayout(sel_row)

        # 샘플 선택 테이블
        self.sel_table = QTableWidget()
        self.sel_table.setColumnCount(len(_SEL_COLS))
        self.sel_table.setHorizontalHeaderLabels(_SEL_COLS)
        self.sel_table.setColumnWidth(0, 28)        # checkbox col
        self.sel_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.sel_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.sel_table.horizontalHeader().setStretchLastSection(True)
        self.sel_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sel_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sel_table.setAlternatingRowColors(True)
        self.sel_table.currentCellChanged.connect(self._on_row_selected)
        self.sel_table.itemChanged.connect(self._on_checkbox_changed)
        left_layout.addWidget(self.sel_table)

        splitter.addWidget(left)

        # ── 오른쪽: 미리보기 ─────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        preview_lbl = QLabel("Preview")
        f2 = QFont(); f2.setBold(True)
        preview_lbl.setFont(f2)
        right_layout.addWidget(preview_lbl)

        # 정보 패널 (HTML)
        self.info_browser = QTextBrowser()
        self.info_browser.setMaximumHeight(160)
        self.info_browser.setOpenExternalLinks(False)
        right_layout.addWidget(self.info_browser)

        # matplotlib 차트 (미리보기)
        if HAS_MPL:
            self._prev_fig, self._prev_axes = plt.subplots(
                1, 2, figsize=(8, 3.2), dpi=88
            )
            self._prev_fig.patch.set_facecolor("#FAFAFA")
            self._prev_canvas = FigureCanvas(self._prev_fig)
            self._prev_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            right_layout.addWidget(self._prev_canvas, 1)
        else:
            right_layout.addWidget(QLabel("matplotlib unavailable – chart disabled."), 1)

        # QC 상세 테이블 (미리보기)
        self.qc_preview = QTableWidget()
        qc_cols = ["Step", "Instrument", "Conc (ng/ul)", "Vol (ul)",
                   "Total (ng)", "GQN/RIN", "Avg Size (bp)", "Molarity (nM)", "Status", "Date"]
        self.qc_preview.setColumnCount(len(qc_cols))
        self.qc_preview.setHorizontalHeaderLabels(qc_cols)
        self.qc_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qc_preview.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.qc_preview.horizontalHeader().setStretchLastSection(True)
        self.qc_preview.setMaximumHeight(180)
        right_layout.addWidget(self.qc_preview)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, 1)

    # ── 데이터 로드 ──────────────────────────────────────────────────

    def refresh(self):
        """DB에서 샘플 목록 새로고침."""
        try:
            with db_manager.session_scope() as session:
                samples = get_all_samples(session)

                # session 밖에서 쓸 수 있도록 dict 형태로 스냅샷
                self._samples_cache = [
                    {
                        "sample_id": s.sample_id,
                        "sample_name": s.sample_name or "",
                        "sample_type": s.sample_type or "",
                        "species": getattr(s, "species", None) or "",
                        "material": getattr(s, "material", None) or "",
                        "description": s.description or "",
                    }
                    for s in samples
                ]

                # 최신 QC status 부착
                for snap in self._samples_cache:
                    from database import get_latest_qc_metric
                    latest = get_latest_qc_metric(session, snap["sample_id"])
                    snap["latest_status"] = latest.status if latest and latest.status else "No Data"

        except Exception as e:
            logger.error(f"Reports refresh failed: {e}")
            self._samples_cache = []

        # 타입 필터 콤보 갱신
        types = sorted({s["sample_type"] for s in self._samples_cache if s["sample_type"]})
        self.type_filter.blockSignals(True)
        current_type = self.type_filter.currentText()
        self.type_filter.clear()
        self.type_filter.addItem("All Types")
        for t in types:
            self.type_filter.addItem(t)
        idx = self.type_filter.findText(current_type)
        if idx >= 0:
            self.type_filter.setCurrentIndex(idx)
        self.type_filter.blockSignals(False)

        self._apply_filter()

    def _apply_filter(self):
        """검색어 + 타입 필터 적용."""
        keyword = self.search_edit.text().strip().lower()
        type_sel = self.type_filter.currentText()

        filtered = [
            s for s in self._samples_cache
            if (not keyword or keyword in s["sample_id"].lower()
                            or keyword in s["sample_name"].lower())
            and (type_sel == "All Types" or s["sample_type"] == type_sel)
        ]

        # 기존 checked 상태 보존
        checked = self._get_checked_ids()

        self.sel_table.blockSignals(True)
        self.sel_table.setRowCount(len(filtered))
        for row, s in enumerate(filtered):
            # checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if s["sample_id"] in checked else Qt.Unchecked)
            self.sel_table.setItem(row, 0, chk)

            self.sel_table.setItem(row, 1, QTableWidgetItem(s["sample_id"]))
            self.sel_table.setItem(row, 2, QTableWidgetItem(s["sample_name"]))
            self.sel_table.setItem(row, 3, QTableWidgetItem(s["sample_type"]))

            status = s["latest_status"]
            st_item = QTableWidgetItem(status)
            color = _STATUS_HEX.get(status)
            if color:
                st_item.setForeground(QColor(color))
            self.sel_table.setItem(row, 4, st_item)

        self.sel_table.blockSignals(False)

    def _get_checked_ids(self) -> set:
        ids = set()
        for row in range(self.sel_table.rowCount()):
            chk = self.sel_table.item(row, 0)
            sid = self.sel_table.item(row, 1)
            if chk and sid and chk.checkState() == Qt.Checked:
                ids.add(sid.text())
        return ids

    def _select_all(self):
        self.sel_table.blockSignals(True)
        for row in range(self.sel_table.rowCount()):
            chk = self.sel_table.item(row, 0)
            if chk:
                chk.setCheckState(Qt.Checked)
        self.sel_table.blockSignals(False)

    def _deselect_all(self):
        self.sel_table.blockSignals(True)
        for row in range(self.sel_table.rowCount()):
            chk = self.sel_table.item(row, 0)
            if chk:
                chk.setCheckState(Qt.Unchecked)
        self.sel_table.blockSignals(False)

    def _on_checkbox_changed(self, item):
        pass  # 나중에 필요하면 확장

    def _on_row_selected(self, row, _col, _prev_row, _prev_col):
        if row < 0:
            return
        sid_item = self.sel_table.item(row, 1)
        if sid_item:
            self._load_preview(sid_item.text())

    # ── 미리보기 ─────────────────────────────────────────────────────

    def _load_preview(self, sample_id: str):
        self._preview_sample_id = sample_id

        snap = next((s for s in self._samples_cache if s["sample_id"] == sample_id), None)
        if not snap:
            return

        try:
            with db_manager.session_scope() as session:
                metrics = get_qc_metrics_by_sample(session, sample_id)
                metrics_dicts = [
                    {
                        "step": m.step,
                        "instrument": m.instrument,
                        "concentration": m.concentration,
                        "volume": m.volume,
                        "total_amount": m.total_amount,
                        "gqn_rin": m.gqn_rin,
                        "avg_size": m.avg_size,
                        "molarity": m.molarity,
                        "status": m.status,
                        "measured_at": m.measured_at,
                    }
                    for m in metrics
                ]
        except Exception as e:
            logger.error(f"Preview load failed: {e}")
            metrics_dicts = []

        self._render_info_html(snap, metrics_dicts)
        self._render_qc_table(metrics_dicts)
        if HAS_MPL:
            self._render_preview_chart(sample_id, metrics_dicts)

    def _render_info_html(self, snap: dict, metrics: list):
        status = snap["latest_status"]
        color = _STATUS_HEX.get(status, "#9E9E9E")
        html = f"""
        <table style="font-size:11px; border-collapse:collapse; width:100%">
          <tr><td><b>Sample ID</b></td><td>{snap['sample_id']}</td>
              <td><b>Name</b></td><td>{snap['sample_name'] or '-'}</td></tr>
          <tr><td><b>Type</b></td><td>{snap['sample_type']}</td>
              <td><b>Latest Status</b></td>
              <td><span style="color:{color}; font-weight:bold">{status}</span></td></tr>
          <tr><td><b>Species</b></td><td>{snap['species'] or '-'}</td>
              <td><b>Material</b></td><td>{snap['material'] or '-'}</td></tr>
          <tr><td><b>Description</b></td>
              <td colspan="3">{snap['description'] or '-'}</td></tr>
          <tr><td><b>QC Records</b></td><td>{len(metrics)}</td>
              <td><b>Steps covered</b></td>
              <td>{', '.join(sorted({m['step'] for m in metrics if m['step']})) or '-'}</td></tr>
        </table>
        """
        self.info_browser.setHtml(html)

    def _render_qc_table(self, metrics: list):
        self.qc_preview.setRowCount(len(metrics))
        for row, m in enumerate(metrics):
            self.qc_preview.setItem(row, 0, QTableWidgetItem(m["step"] or "-"))
            self.qc_preview.setItem(row, 1, QTableWidgetItem(m["instrument"] or "-"))
            self.qc_preview.setItem(row, 2, QTableWidgetItem(_fmt(m["concentration"])))
            self.qc_preview.setItem(row, 3, QTableWidgetItem(_fmt(m["volume"])))
            self.qc_preview.setItem(row, 4, QTableWidgetItem(_fmt(m["total_amount"])))
            self.qc_preview.setItem(row, 5, QTableWidgetItem(_fmt(m["gqn_rin"])))
            self.qc_preview.setItem(row, 6, QTableWidgetItem(_fmt(m["avg_size"], 0)))
            self.qc_preview.setItem(row, 7, QTableWidgetItem(_fmt(m["molarity"])))

            status = m["status"] or "-"
            st_item = QTableWidgetItem(status)
            color = _STATUS_HEX.get(status)
            if color:
                st_item.setForeground(QColor(color))
            self.qc_preview.setItem(row, 8, st_item)

            date_str = (
                m["measured_at"].strftime("%Y-%m-%d")
                if m["measured_at"] else "-"
            )
            self.qc_preview.setItem(row, 9, QTableWidgetItem(date_str))

    def _render_preview_chart(self, sample_id: str, metrics: list):
        ax1, ax2 = self._prev_axes
        ax1.clear(); ax2.clear()

        if not metrics:
            for ax in (ax1, ax2):
                ax.text(0.5, 0.5, "No QC data", ha="center", va="center",
                        transform=ax.transAxes, color="#9E9E9E")
                ax.axis("off")
            self._prev_fig.tight_layout(pad=0.5)
            self._prev_canvas.draw()
            return

        steps = [m["step"] or "?" for m in metrics]
        concs = [m["concentration"] or 0 for m in metrics]
        gqns  = [m["gqn_rin"] or 0 for m in metrics]
        statuses = [m["status"] or "No Data" for m in metrics]
        bar_colors = [_STATUS_MPL.get(s, "#9E9E9E") for s in statuses]
        x = np.arange(len(steps))

        # 왼쪽: 농도
        bars1 = ax1.bar(x, concs, color=bar_colors, edgecolor="white", linewidth=0.8)
        ax1.set_title("Concentration (ng/µl)", fontsize=9, fontweight="bold")
        ax1.set_xticks(x)
        ax1.set_xticklabels(steps, rotation=25, ha="right", fontsize=7)
        ax1.tick_params(axis="y", labelsize=7)
        ax1.spines[["top", "right"]].set_visible(False)
        ax1.set_facecolor("#FAFAFA")
        for bar, val in zip(bars1, concs):
            if val > 0:
                ax1.text(bar.get_x() + bar.get_width() / 2,
                         bar.get_height(), f"{val:.1f}",
                         ha="center", va="bottom", fontsize=7)

        # 오른쪽: GQN/RIN
        bars2 = ax2.bar(x, gqns, color=bar_colors, edgecolor="white", linewidth=0.8)
        ax2.set_title("GQN / RIN", fontsize=9, fontweight="bold")
        ax2.set_xticks(x)
        ax2.set_xticklabels(steps, rotation=25, ha="right", fontsize=7)
        ax2.tick_params(axis="y", labelsize=7)
        ax2.spines[["top", "right"]].set_visible(False)
        ax2.set_facecolor("#FAFAFA")
        for bar, val in zip(bars2, gqns):
            if val > 0:
                ax2.text(bar.get_x() + bar.get_width() / 2,
                         bar.get_height(), f"{val:.1f}",
                         ha="center", va="bottom", fontsize=7)

        self._prev_fig.suptitle(f"QC Preview — {sample_id}", fontsize=9, y=1.01)
        self._prev_fig.tight_layout(pad=0.6)
        self._prev_canvas.draw()

    # ── PDF 내보내기 ─────────────────────────────────────────────────

    def _export_pdf(self):
        selected_ids = sorted(self._get_checked_ids())
        if not selected_ids:
            QMessageBox.information(self, "No Selection",
                                    "Check at least one sample in the list.")
            return

        default_name = f"QC_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Report",
            str(REPORTS_DIR / default_name),
            "PDF Files (*.pdf)",
        )
        if not save_path:
            return

        snap_map = {s["sample_id"]: s for s in self._samples_cache}
        failed = []

        try:
            with PdfPages(save_path) as pdf:
                for sid in selected_ids:
                    snap = snap_map.get(sid, {"sample_id": sid, "sample_name": "",
                                              "sample_type": "", "species": "",
                                              "material": "", "description": "",
                                              "latest_status": ""})
                    try:
                        with db_manager.session_scope() as session:
                            metrics = get_qc_metrics_by_sample(session, sid)
                            metrics_dicts = [
                                {
                                    "step": m.step,
                                    "instrument": m.instrument,
                                    "concentration": m.concentration,
                                    "volume": m.volume,
                                    "total_amount": m.total_amount,
                                    "gqn_rin": m.gqn_rin,
                                    "avg_size": m.avg_size,
                                    "molarity": m.molarity,
                                    "status": m.status,
                                    "measured_at": m.measured_at,
                                }
                                for m in metrics
                            ]
                        fig = _build_report_figure(snap, metrics_dicts)
                        pdf.savefig(fig, bbox_inches="tight")
                        plt.close(fig)
                    except Exception as e:
                        logger.error(f"PDF page failed for {sid}: {e}")
                        failed.append(sid)

                # 마지막 페이지: 생성 정보
                info_fig = _build_summary_page(selected_ids, snap_map)
                pdf.savefig(info_fig, bbox_inches="tight")
                plt.close(info_fig)

            msg = f"PDF saved:\n{save_path}\n\n{len(selected_ids) - len(failed)} sample(s) exported."
            if failed:
                msg += f"\nFailed: {', '.join(failed)}"
            QMessageBox.information(self, "Export Complete", msg)

        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to save PDF:\n{e}")

    # ── Excel 내보내기 ────────────────────────────────────────────────

    def _export_excel(self):
        selected_ids = sorted(self._get_checked_ids())
        if not selected_ids:
            QMessageBox.information(self, "No Selection",
                                    "Check at least one sample in the list.")
            return

        default_name = f"QC_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel File",
            str(REPORTS_DIR / default_name),
            "Excel Files (*.xlsx)",
        )
        if not save_path:
            return

        snap_map = {s["sample_id"]: s for s in self._samples_cache}

        try:
            wb = openpyxl.Workbook()
            _write_excel(wb, selected_ids, snap_map)
            wb.save(save_path)
            QMessageBox.information(self, "Export Complete",
                                    f"Excel saved:\n{save_path}")
        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to save Excel:\n{e}")

    # ── GUI 상태 저장/복원 ────────────────────────────────────────────

    def save_gui_state(self, settings):
        from config.gui_state import save_table_widths, save_splitter, save_combo
        save_table_widths(settings, "ReportsTab/selTableWidths",     self.sel_table)
        save_table_widths(settings, "ReportsTab/qcPreviewWidths",    self.qc_preview)
        save_splitter(settings,     "ReportsTab/splitterState",      self.splitter)
        save_combo(settings,        "ReportsTab/typeFilter",         self.type_filter)
        settings.setValue("ReportsTab/searchText", self.search_edit.text())

    def restore_gui_state(self, settings):
        from config.gui_state import restore_table_widths, restore_splitter, restore_combo
        restore_table_widths(settings, "ReportsTab/selTableWidths",  self.sel_table)
        restore_table_widths(settings, "ReportsTab/qcPreviewWidths", self.qc_preview)
        restore_splitter(settings,     "ReportsTab/splitterState",   self.splitter)
        self.type_filter.blockSignals(True)
        restore_combo(settings,        "ReportsTab/typeFilter",      self.type_filter)
        self.type_filter.blockSignals(False)
        text = settings.value("ReportsTab/searchText", "")
        if text:
            self.search_edit.setText(str(text))


# ════════════════════════════════════════════════════════════════════
# PDF 빌더 함수 (모듈 레벨)
# ════════════════════════════════════════════════════════════════════

def _build_report_figure(snap: dict, metrics: list) -> "plt.Figure":
    """샘플 한 개의 A4 리포트 페이지 Figure 생성."""
    fig = plt.figure(figsize=(8.27, 11.69))          # A4
    fig.patch.set_facecolor("white")

    gs = gridspec.GridSpec(
        4, 1, figure=fig,
        height_ratios=[1.2, 3, 2.8, 0.2],
        hspace=0.55,
        left=0.08, right=0.95, top=0.94, bottom=0.04,
    )

    # ── 1) 헤더 ─────────────────────────────────────────────────────
    ax_hdr = fig.add_subplot(gs[0])
    ax_hdr.axis("off")

    sample_id = snap.get("sample_id", "")
    status = snap.get("latest_status", "")
    status_color = _STATUS_MPL.get(status, "#9E9E9E")

    ax_hdr.text(0, 1.0, "NGS Sample QC Report",
                transform=ax_hdr.transAxes, fontsize=15, fontweight="bold",
                va="top", color="#1A237E")
    ax_hdr.text(0, 0.62, f"Sample ID: {sample_id}",
                transform=ax_hdr.transAxes, fontsize=11, va="top")

    info_lines = [
        f"Name: {snap.get('sample_name') or '-'}",
        f"Type: {snap.get('sample_type') or '-'}",
        f"Species: {snap.get('species') or '-'}",
        f"Material: {snap.get('material') or '-'}",
        f"Description: {snap.get('description') or '-'}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    ax_hdr.text(0, 0.30, "   ".join(info_lines[:3]),
                transform=ax_hdr.transAxes, fontsize=8, va="top", color="#333333")
    ax_hdr.text(0, 0.0, "   ".join(info_lines[3:]),
                transform=ax_hdr.transAxes, fontsize=8, va="top", color="#333333")

    # 상태 배지
    ax_hdr.text(1.0, 1.0, status,
                transform=ax_hdr.transAxes, fontsize=13, fontweight="bold",
                ha="right", va="top", color="white",
                bbox=dict(facecolor=status_color, edgecolor="none",
                          boxstyle="round,pad=0.4"))

    # ── 2) 차트 ─────────────────────────────────────────────────────
    ax_charts = fig.add_subplot(gs[1])
    ax_charts.axis("off")

    inner_gs = gridspec.GridSpecFromSubplotSpec(
        1, 3, subplot_spec=gs[1], wspace=0.45
    )
    ax_conc = fig.add_subplot(inner_gs[0])
    ax_gqn  = fig.add_subplot(inner_gs[1])
    ax_size = fig.add_subplot(inner_gs[2])

    if metrics:
        steps      = [m["step"] or "?" for m in metrics]
        concs      = [m["concentration"] or 0 for m in metrics]
        gqns       = [m["gqn_rin"] or 0 for m in metrics]
        sizes      = [m["avg_size"] or 0 for m in metrics]
        statuses   = [m["status"] or "No Data" for m in metrics]
        bar_colors = [_STATUS_MPL.get(s, "#9E9E9E") for s in statuses]
        x = np.arange(len(steps))

        for ax, vals, ylabel in [
            (ax_conc, concs, "ng/µl"),
            (ax_gqn,  gqns,  "GQN/RIN"),
            (ax_size, sizes, "bp"),
        ]:
            bars = ax.bar(x, vals, color=bar_colors, edgecolor="white", linewidth=0.6)
            ax.set_xticks(x)
            ax.set_xticklabels(steps, rotation=30, ha="right", fontsize=6.5)
            ax.set_ylabel(ylabel, fontsize=7)
            ax.tick_params(axis="y", labelsize=7)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_facecolor("#FAFAFA")
            for bar, val in zip(bars, vals):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_height(), f"{val:.1f}",
                            ha="center", va="bottom", fontsize=6)

        ax_conc.set_title("Concentration", fontsize=8, fontweight="bold")
        ax_gqn.set_title("GQN / RIN", fontsize=8, fontweight="bold")
        ax_size.set_title("Avg Size (bp)", fontsize=8, fontweight="bold")

        # 범례 (Pass/Warning/Fail)
        from matplotlib.patches import Patch
        legend_handles = [
            Patch(facecolor=_STATUS_MPL["Pass"],    label="Pass"),
            Patch(facecolor=_STATUS_MPL["Warning"], label="Warning"),
            Patch(facecolor=_STATUS_MPL["Fail"],    label="Fail"),
            Patch(facecolor=_STATUS_MPL["No Data"], label="No Data"),
        ]
        ax_conc.legend(handles=legend_handles, loc="upper right",
                       fontsize=6, frameon=True, framealpha=0.8)
    else:
        for ax in (ax_conc, ax_gqn, ax_size):
            ax.text(0.5, 0.5, "No QC data", ha="center", va="center",
                    transform=ax.transAxes, color="#9E9E9E", fontsize=9)
            ax.axis("off")

    # ── 3) QC 데이터 테이블 ─────────────────────────────────────────
    ax_tbl = fig.add_subplot(gs[2])
    ax_tbl.axis("off")

    tbl_cols = ["Step", "Instrument", "Conc\n(ng/µl)", "Vol\n(µl)",
                "Total\n(ng)", "GQN/\nRIN", "Avg Size\n(bp)",
                "Molarity\n(nM)", "Status", "Date"]

    if metrics:
        tbl_data = []
        for m in metrics:
            date_str = (m["measured_at"].strftime("%Y-%m-%d")
                        if m["measured_at"] else "-")
            tbl_data.append([
                m["step"] or "-",
                m["instrument"] or "-",
                _fmt(m["concentration"]),
                _fmt(m["volume"]),
                _fmt(m["total_amount"]),
                _fmt(m["gqn_rin"]),
                _fmt(m["avg_size"], 0),
                _fmt(m["molarity"]),
                m["status"] or "-",
                date_str,
            ])
    else:
        tbl_data = [["No data"] + ["-"] * (len(tbl_cols) - 1)]

    tbl = ax_tbl.table(
        cellText=tbl_data,
        colLabels=tbl_cols,
        loc="upper center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    tbl.auto_set_column_width(list(range(len(tbl_cols))))

    # 헤더 스타일
    for col in range(len(tbl_cols)):
        cell = tbl[0, col]
        cell.set_facecolor("#1A237E")
        cell.set_text_props(color="white", fontweight="bold")

    # 상태 셀 색상
    for row_idx, m in enumerate(metrics if metrics else []):
        status = m.get("status", "")
        color = _STATUS_MPL.get(status)
        if color:
            status_col = tbl_cols.index("Status")
            tbl[row_idx + 1, status_col].set_facecolor(color)
            tbl[row_idx + 1, status_col].set_text_props(
                color="white", fontweight="bold"
            )

    # 교대 행 배경
    for row_idx in range(len(metrics if metrics else [])):
        if row_idx % 2 == 1:
            for col in range(len(tbl_cols)):
                if (row_idx + 1, col) in tbl._cells:
                    cell = tbl[row_idx + 1, col]
                    if cell.get_facecolor()[:3] == (1, 1, 1):  # white만
                        cell.set_facecolor("#F3F4F6")

    ax_tbl.set_title("QC Metrics", fontsize=9, fontweight="bold",
                     loc="left", pad=4, color="#1A237E")

    # ── 4) 푸터 ─────────────────────────────────────────────────────
    ax_ftr = fig.add_subplot(gs[3])
    ax_ftr.axis("off")
    ax_ftr.text(0.5, 0.5,
                f"NGS Sample QC LIMS  |  {datetime.now().strftime('%Y-%m-%d')}",
                transform=ax_ftr.transAxes,
                ha="center", va="center", fontsize=7, color="#888888")

    return fig


def _build_summary_page(sample_ids: List[str], snap_map: dict) -> "plt.Figure":
    """PDF 마지막 페이지: 배치 요약 표."""
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    fig.patch.set_facecolor("white")
    ax.axis("off")
    ax.set_title("QC Batch Summary",
                 fontsize=14, fontweight="bold", color="#1A237E",
                 loc="left", pad=12, x=0.05, y=0.97)

    tbl_cols = ["Sample ID", "Name", "Type", "Species", "Material", "Status"]
    tbl_data = []
    for sid in sample_ids:
        s = snap_map.get(sid, {})
        tbl_data.append([
            sid,
            s.get("sample_name", "-"),
            s.get("sample_type", "-"),
            s.get("species", "-"),
            s.get("material", "-"),
            s.get("latest_status", "-"),
        ])

    tbl = ax.table(
        cellText=tbl_data,
        colLabels=tbl_cols,
        loc="upper center",
        cellLoc="center",
        bbox=[0.02, 0.1, 0.96, 0.82],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.auto_set_column_width(list(range(len(tbl_cols))))

    for col in range(len(tbl_cols)):
        cell = tbl[0, col]
        cell.set_facecolor("#1A237E")
        cell.set_text_props(color="white", fontweight="bold")

    for row_idx, row_data in enumerate(tbl_data):
        status = row_data[-1]
        color = _STATUS_MPL.get(status)
        status_col = len(tbl_cols) - 1
        if color:
            tbl[row_idx + 1, status_col].set_facecolor(color)
            tbl[row_idx + 1, status_col].set_text_props(
                color="white", fontweight="bold"
            )
        if row_idx % 2 == 1:
            for col in range(len(tbl_cols) - 1):
                tbl[row_idx + 1, col].set_facecolor("#F3F4F6")

    ax.text(0.5, 0.03,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
            f"Total: {len(sample_ids)} sample(s)",
            transform=ax.transAxes, ha="center", fontsize=8, color="#888888")

    return fig


# ════════════════════════════════════════════════════════════════════
# Excel 빌더 함수
# ════════════════════════════════════════════════════════════════════

def _write_excel(wb: "openpyxl.Workbook", sample_ids: List[str], snap_map: dict):
    """선택 샘플의 QC 데이터를 Excel에 기록."""
    # ── Sheet 1: Sample Info ──────────────────────────────────────
    ws_info = wb.active
    ws_info.title = "Sample Info"

    hdr_fill = PatternFill("solid", fgColor="1A237E")
    hdr_font = XlFont(bold=True, color="FFFFFF")
    alt_fill = PatternFill("solid", fgColor="F3F4F6")
    center   = Alignment(horizontal="center", vertical="center")
    thin     = Side(style="thin", color="CCCCCC")
    border   = Border(left=thin, right=thin, top=thin, bottom=thin)

    def _hdr(ws, row, cols):
        for col_idx, text in enumerate(cols, 1):
            c = ws.cell(row=row, column=col_idx, value=text)
            c.font = hdr_font; c.fill = hdr_fill
            c.alignment = center; c.border = border

    def _cell(ws, row, col, value, fill=None):
        c = ws.cell(row=row, column=col, value=value)
        c.alignment = Alignment(vertical="center")
        c.border = border
        if fill:
            c.fill = fill
        return c

    info_cols = ["Sample ID", "Name", "Type", "Species", "Material",
                 "Description", "Latest Status"]
    _hdr(ws_info, 1, info_cols)

    for row_idx, sid in enumerate(sample_ids, 2):
        s = snap_map.get(sid, {})
        status = s.get("latest_status", "")
        status_color_map = {
            "Pass": "4CAF50", "Warning": "FF9800",
            "Fail": "F44336", "No Data": "9E9E9E"
        }
        status_fill = PatternFill("solid",
                                   fgColor=status_color_map.get(status, "9E9E9E"))
        alt = alt_fill if row_idx % 2 == 0 else None
        _cell(ws_info, row_idx, 1, sid, alt)
        _cell(ws_info, row_idx, 2, s.get("sample_name", ""), alt)
        _cell(ws_info, row_idx, 3, s.get("sample_type", ""), alt)
        _cell(ws_info, row_idx, 4, s.get("species", ""), alt)
        _cell(ws_info, row_idx, 5, s.get("material", ""), alt)
        _cell(ws_info, row_idx, 6, s.get("description", ""), alt)
        c = _cell(ws_info, row_idx, 7, status, status_fill)
        c.font = XlFont(bold=True, color="FFFFFF")
        c.alignment = center

    for col in ws_info.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=8)
        ws_info.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    # ── Sheet 2: QC Metrics ───────────────────────────────────────
    ws_qc = wb.create_sheet("QC Metrics")
    qc_cols = ["Sample ID", "Step", "Instrument",
               "Conc (ng/ul)", "Vol (ul)", "Total (ng)",
               "260/280", "GQN/RIN", "Avg Size (bp)",
               "Molarity (nM)", "Status", "Measured Date"]
    _hdr(ws_qc, 1, qc_cols)

    qc_row = 2
    status_color_map = {
        "Pass": "4CAF50", "Warning": "FF9800",
        "Fail": "F44336", "No Data": "9E9E9E"
    }
    for sid in sample_ids:
        try:
            with db_manager.session_scope() as session:
                metrics = get_qc_metrics_by_sample(session, sid)
                for m_idx, m in enumerate(metrics):
                    alt = alt_fill if qc_row % 2 == 0 else None
                    _cell(ws_qc, qc_row, 1, sid, alt)
                    _cell(ws_qc, qc_row, 2, m.step, alt)
                    _cell(ws_qc, qc_row, 3, m.instrument, alt)
                    _cell(ws_qc, qc_row, 4, m.concentration, alt)
                    _cell(ws_qc, qc_row, 5, m.volume, alt)
                    _cell(ws_qc, qc_row, 6, m.total_amount, alt)
                    _cell(ws_qc, qc_row, 7, m.purity_260_280, alt)
                    _cell(ws_qc, qc_row, 8, m.gqn_rin, alt)
                    _cell(ws_qc, qc_row, 9, m.avg_size, alt)
                    _cell(ws_qc, qc_row, 10, m.molarity, alt)
                    status = m.status or ""
                    s_fill = PatternFill("solid",
                                         fgColor=status_color_map.get(status, "9E9E9E"))
                    c = _cell(ws_qc, qc_row, 11, status, s_fill)
                    c.font = XlFont(bold=True, color="FFFFFF")
                    c.alignment = center
                    date_str = (m.measured_at.strftime("%Y-%m-%d")
                                if m.measured_at else "")
                    _cell(ws_qc, qc_row, 12, date_str, alt)
                    qc_row += 1
        except Exception as e:
            logger.error(f"Excel QC row failed for {sid}: {e}")

    for col in ws_qc.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=8)
        ws_qc.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

    ws_qc.freeze_panes = "A2"
    ws_info.freeze_panes = "A2"
