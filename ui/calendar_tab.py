"""
Calendar 탭 — QC 측정 일정 캘린더 뷰

날짜별 QC 측정 이력을 달력 형식으로 표시.
측정 상태(Pass/Warning/Fail)에 따라 날짜 셀 색상 구분.
날짜 선택 시 오른쪽 패널에 해당 날짜 측정 목록 표시.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional, Set

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont, QTextCharFormat
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database import db_manager, get_all_samples
from database.models import QCMetric, Sample

logger = logging.getLogger(__name__)

# ── 상태 색상 ─────────────────────────────────────────────────────────
# 날짜 셀 배경 (QCalendarWidget)
_STATUS_BG: Dict[Optional[str], str] = {
    "Fail":    "#FFCDD2",  # 연빨강
    "Warning": "#FFE0B2",  # 연주황
    "Pass":    "#C8E6C9",  # 연초록
    None:      "#E3F2FD",  # 연파랑 (status 없음)
}
# 테이블 텍스트 색상
_STATUS_FG: Dict[str, str] = {
    "Pass":    "#2E7D32",
    "Warning": "#E65100",
    "Fail":    "#B71C1C",
}
# 날짜별 worst status 우선순위
_PRIORITY = {"Fail": 0, "Warning": 1, "Pass": 2, None: 3}


def _worst_status(metrics: List[dict]) -> Optional[str]:
    """리스트에서 가장 심각한 status 반환."""
    best = None
    for m in metrics:
        s = m.get("status")
        if _PRIORITY.get(s, 3) < _PRIORITY.get(best, 3):
            best = s
    return best


def _fmt(val, decimals=2) -> str:
    return f"{val:.{decimals}f}" if val is not None else "-"


# ── 커스텀 캘린더 ────────────────────────────────────────────────────

class _QCCalendar(QCalendarWidget):
    """날짜별 QC 측정 상태를 배경색으로 표시하는 QCalendarWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setMinimumWidth(360)
        self._colored: Set[QDate] = set()

    def apply_date_data(self, date_map: Dict[date, List[dict]]):
        """date_map: {python date → [metric dict, ...]}"""
        # 기존 포맷 초기화
        blank = QTextCharFormat()
        for qd in self._colored:
            self.setDateTextFormat(qd, blank)
        self._colored.clear()

        bold_font = QFont()
        bold_font.setBold(True)

        for py_date, metrics in date_map.items():
            worst = _worst_status(metrics)
            bg_hex = _STATUS_BG.get(worst, _STATUS_BG[None])

            fmt = QTextCharFormat()
            fmt.setBackground(QColor(bg_hex))
            fmt.setFont(bold_font)

            qd = QDate(py_date.year, py_date.month, py_date.day)
            self.setDateTextFormat(qd, fmt)
            self._colored.add(qd)


# ════════════════════════════════════════════════════════════════════
# Calendar 탭
# ════════════════════════════════════════════════════════════════════

class CalendarTab(QWidget):
    """QC 측정 일정 캘린더 탭."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # date(python) → [metric dict, ...]
        self._date_map: Dict[date, List[dict]] = {}
        self._build_ui()
        self.refresh()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 상단 헤더 ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("QC Measurement Calendar")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        hdr.addWidget(title)
        hdr.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        hdr.addWidget(btn_refresh)
        root.addLayout(hdr)

        # ── 범례 ─────────────────────────────────────────────────────
        legend_row = QHBoxLayout()
        legend_row.addWidget(QLabel("Legend:"))
        for label_text, bg, fg in [
            ("Pass",    _STATUS_BG["Pass"],    "#2E7D32"),
            ("Warning", _STATUS_BG["Warning"], "#E65100"),
            ("Fail",    _STATUS_BG["Fail"],    "#B71C1C"),
            ("No Status", _STATUS_BG[None],   "#1565C0"),
        ]:
            lbl = QLabel(f"  {label_text}  ")
            lbl.setStyleSheet(
                f"background-color:{bg}; color:{fg}; "
                "border-radius:3px; font-weight:bold; padding:1px 4px;"
            )
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        root.addLayout(legend_row)

        # ── 메인 스플리터 ────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # 왼쪽: 달력
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._calendar = _QCCalendar()
        self._calendar.selectionChanged.connect(self._on_date_selected)
        left_layout.addWidget(self._calendar)

        self._summary_label = QLabel("날짜를 선택하세요.")
        self._summary_label.setStyleSheet("color:#555; padding:4px;")
        left_layout.addWidget(self._summary_label)
        left_layout.addStretch()

        splitter.addWidget(left)

        # 오른쪽: 측정 목록 테이블
        right = QFrame()
        right.setFrameShape(QFrame.StyledPanel)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 6, 6, 6)

        self._detail_label = QLabel("QC Measurements")
        f2 = QFont(); f2.setBold(True); f2.setPointSize(9)
        self._detail_label.setFont(f2)
        right_layout.addWidget(self._detail_label)

        self._table = QTableWidget()
        cols = [
            "Sample ID", "Sample Name", "Project",
            "Step", "Instrument",
            "Conc (ng/µl)", "GQN/RIN", "Avg Size (bp)",
            "Status",
        ]
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        right_layout.addWidget(self._table)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

    # ── 데이터 로드 ──────────────────────────────────────────────────

    def refresh(self):
        """DB에서 전체 QC 측정 데이터 로드 → 캘린더 갱신."""
        self._date_map.clear()

        try:
            with db_manager.session_scope() as session:
                # Sample 정보 사전 로드
                samples = {
                    s.sample_id: {
                        "sample_name": s.sample_name or "",
                        "project": getattr(s, "project", None) or "",
                    }
                    for s in session.query(Sample).all()
                }

                metrics = (
                    session.query(QCMetric)
                    .filter(QCMetric.measured_at.isnot(None))
                    .order_by(QCMetric.measured_at)
                    .all()
                )
                for m in metrics:
                    py_date = m.measured_at.date()
                    s_info = samples.get(m.sample_id, {})
                    entry = {
                        "sample_id":   m.sample_id,
                        "sample_name": s_info.get("sample_name", ""),
                        "project":     s_info.get("project", ""),
                        "step":        m.step or "",
                        "instrument":  m.instrument or "",
                        "concentration": m.concentration,
                        "gqn_rin":     m.gqn_rin,
                        "avg_size":    m.avg_size,
                        "status":      m.status,
                    }
                    self._date_map.setdefault(py_date, []).append(entry)

        except Exception as e:
            logger.error(f"CalendarTab refresh failed: {e}")

        self._calendar.apply_date_data(self._date_map)
        total_dates = len(self._date_map)
        total_metrics = sum(len(v) for v in self._date_map.values())
        self._summary_label.setText(
            f"총 {total_dates}일, {total_metrics}건 측정 — 날짜를 클릭하면 상세 내용이 표시됩니다."
        )

        # 현재 선택된 날짜 다시 표시
        self._on_date_selected()

    # ── 날짜 선택 ────────────────────────────────────────────────────

    def _on_date_selected(self):
        qd = self._calendar.selectedDate()
        py_date = date(qd.year(), qd.month(), qd.day())
        metrics = self._date_map.get(py_date, [])

        date_str = qd.toString("yyyy-MM-dd")
        self._detail_label.setText(
            f"QC Measurements — {date_str}  ({len(metrics)}건)"
        )
        self._populate_table(metrics)

    def _populate_table(self, metrics: List[dict]):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(metrics))

        for row, m in enumerate(metrics):
            self._table.setItem(row, 0, QTableWidgetItem(m["sample_id"]))
            self._table.setItem(row, 1, QTableWidgetItem(m["sample_name"]))
            self._table.setItem(row, 2, QTableWidgetItem(m["project"]))
            self._table.setItem(row, 3, QTableWidgetItem(m["step"]))
            self._table.setItem(row, 4, QTableWidgetItem(m["instrument"]))
            self._table.setItem(row, 5, QTableWidgetItem(_fmt(m["concentration"])))
            self._table.setItem(row, 6, QTableWidgetItem(_fmt(m["gqn_rin"])))
            self._table.setItem(row, 7, QTableWidgetItem(_fmt(m["avg_size"], 0)))

            status = m["status"] or "-"
            status_item = QTableWidgetItem(status)
            fg = _STATUS_FG.get(status)
            if fg:
                status_item.setForeground(QColor(fg))
            self._table.setItem(row, 8, status_item)

        self._table.setSortingEnabled(True)

    # ── GUI 상태 저장/복원 ────────────────────────────────────────────

    def save_gui_state(self, settings):
        qd = self._calendar.selectedDate()
        settings.setValue("CalendarTab/selectedDate", qd.toString(Qt.ISODate))

    def restore_gui_state(self, settings):
        date_str = settings.value("CalendarTab/selectedDate")
        if date_str:
            qd = QDate.fromString(date_str, Qt.ISODate)
            if qd.isValid():
                self._calendar.setSelectedDate(qd)
