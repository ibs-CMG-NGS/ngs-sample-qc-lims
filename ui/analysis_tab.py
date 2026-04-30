"""
Analysis 탭 - 4가지 QC 분석 차트
1. 배치 비교     : 선택 단계·지표의 샘플 간 비교 바 차트
2. Recovery 흐름 : 단계별 Total Amount / Recovery % 라인 차트
3. 분포 히스토그램: 선택 지표의 전체 샘플 분포 + 기준선
4. 단계별 통계   : Pass / Warning / Fail 스택 바 차트
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionHeader,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavToolbar

    # ── 전역 스타일 설정 ──────────────────────────────────────────────
    plt.rcParams.update({
        "figure.facecolor":      "#FFFFFF",
        "axes.facecolor":        "#F8F9FA",
        "axes.edgecolor":        "#CCCCCC",
        "axes.linewidth":        0.8,
        "axes.grid":             True,
        "axes.grid.axis":        "y",
        "grid.color":            "#E0E0E0",
        "grid.linewidth":        0.6,
        "axes.spines.top":       False,
        "axes.spines.right":     False,
        "axes.titlesize":        10,
        "axes.titleweight":      "bold",
        "axes.titlepad":         8,
        "axes.labelsize":        8,
        "axes.labelcolor":       "#444444",
        "xtick.labelsize":       8,
        "ytick.labelsize":       8,
        "xtick.color":           "#555555",
        "ytick.color":           "#555555",
        "legend.fontsize":       7.5,
        "legend.framealpha":     0.85,
        "legend.edgecolor":      "#CCCCCC",
        "legend.borderpad":      0.5,
        "font.family":           ["Malgun Gothic", "DejaVu Sans", "sans-serif"],
        "lines.linewidth":       2.0,
        "lines.markersize":      6,
        "patch.linewidth":       0.5,
    })
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from config.settings import QC_STEPS, RNA_QC_STEPS, QC_CRITERIA, STATUS_COLORS

_ALL_STEPS = QC_STEPS + RNA_QC_STEPS

# mRNA-seq 는 RNA workflow, 나머지는 모두 DNA workflow
_RNA_SAMPLE_TYPES = {"mRNA-seq"}
from database import db_manager, get_all_samples, get_qc_metrics_by_sample

logger = logging.getLogger(__name__)

# ── 색상 상수 ──────────────────────────────────────────────────────
_STATUS_COLOR = {
    "Pass":    STATUS_COLORS["Pass"],
    "Warning": STATUS_COLORS["Warning"],
    "Fail":    STATUS_COLORS["Fail"],
    "No Data": "#9E9E9E",
}

# 다중 샘플용 색상 팔레트 (colorblind-friendly, 20색 순환)
_SAMPLE_PALETTE = [
    "#2196F3", "#4CAF50", "#FF5722", "#9C27B0", "#009688",
    "#F44336", "#3F51B5", "#FF9800", "#00BCD4", "#8BC34A",
    "#E91E63", "#795548", "#607D8B", "#CDDC39", "#FFC107",
    "#673AB7", "#03A9F4", "#76FF03", "#FF4081", "#00E5FF",
]

# ── 지표 정의 ──────────────────────────────────────────────────────
METRICS = {
    "Concentration (ng/µl)": "concentration",
    "Total Amount (ng)":     "total_amount",
    "GQN / RIN":             "gqn_rin",
    "Avg Size (bp)":         "avg_size",
    "Purity 260/280":        "purity_260_280",
}

# QC 기준값 (히스토그램 기준선용)
_THRESHOLDS: Dict[str, List[tuple]] = {
    "gqn_rin": [
        (7.0, "Pass", _STATUS_COLOR["Pass"]),
        (5.0, "Warning", _STATUS_COLOR["Warning"]),
    ],
}


def _fmt(val, d=2) -> str:
    return f"{val:.{d}f}" if val is not None else "-"


class _SortableItem(QTableWidgetItem):
    """숫자 컬럼을 숫자 순서로 정렬하는 QTableWidgetItem."""
    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


# ── QC Summary 표 컬럼 정의 ──────────────────────────────────────────
# (group_name, col_display, step_name_or_None, field_name)
_STEP_COL_SPEC = [
    ("Sample Info",        "Sample ID",    None,                  "sample_id"),
    ("Sample Info",        "Name",         None,                  "sample_name"),
    ("Sample Info",        "Project",      None,                  "project"),
    ("gDNA Extraction",    "Conc.(ng/µl)", "gDNA Extraction",     "concentration"),
    ("gDNA Extraction",    "Total(ng)",    "gDNA Extraction",     "total_amount"),
    ("gDNA Extraction",    "260/280",      "gDNA Extraction",     "purity_260_280"),
    ("gDNA Extraction",    "GQN",          "gDNA Extraction",     "gqn_rin"),
    ("gDNA Extraction",    "Status",       "gDNA Extraction",     "status"),
    ("SRE",                "Conc.(ng/µl)", "SRE",                 "concentration"),
    ("SRE",                "Total(ng)",    "SRE",                 "total_amount"),
    ("SRE",                "Status",       "SRE",                 "status"),
    ("DNA Shearing",       "Conc.(ng/µl)", "DNA Shearing",        "concentration"),
    ("DNA Shearing",       "Total(ng)",    "DNA Shearing",        "total_amount"),
    ("DNA Shearing",       "AvgSize(bp)",  "DNA Shearing",        "avg_size"),
    ("DNA Shearing",       "Status",       "DNA Shearing",        "status"),
    ("Library Prep",       "Conc.(ng/µl)", "Library Prep",        "concentration"),
    ("Library Prep",       "Total(ng)",    "Library Prep",        "total_amount"),
    ("Library Prep",       "Index",        "Library Prep",        "index_no"),
    ("Library Prep",       "Status",       "Library Prep",        "status"),
    ("Polymerase Binding", "Conc.(ng/µl)", "Polymerase Binding",  "concentration"),
    ("Polymerase Binding", "Total(ng)",    "Polymerase Binding",  "total_amount"),
    ("Polymerase Binding", "Status",       "Polymerase Binding",  "status"),
    ("RNA Extraction",     "Conc.(ng/µl)", "RNA Extraction",      "concentration"),
    ("RNA Extraction",     "Total(ng)",    "RNA Extraction",      "total_amount"),
    ("RNA Extraction",     "260/280",      "RNA Extraction",      "purity_260_280"),
    ("RNA Extraction",     "RIN",          "RNA Extraction",      "gqn_rin"),
    ("RNA Extraction",     "Status",       "RNA Extraction",      "status"),
    ("mRNA Elution",       "Conc.(ng/µl)", "mRNA Elution",        "concentration"),
    ("mRNA Elution",       "Total(ng)",    "mRNA Elution",        "total_amount"),
    ("mRNA Elution",       "Status",       "mRNA Elution",        "status"),
    ("Library Prep (RNA)", "Conc.(ng/µl)", "Library Prep (RNA)",  "concentration"),
    ("Library Prep (RNA)", "Total(ng)",    "Library Prep (RNA)",  "total_amount"),
    ("Library Prep (RNA)", "Status",       "Library Prep (RNA)",  "status"),
]


def _build_groups(col_defs):
    """col_defs → [(group_label, start_col, col_count), ...]"""
    groups, cur_group, cur_start = [], None, 0
    for i, (group, *_) in enumerate(col_defs):
        if group != cur_group:
            if cur_group is not None:
                groups.append((cur_group, cur_start, i - cur_start))
            cur_group, cur_start = group, i
    if cur_group is not None:
        groups.append((cur_group, cur_start, len(col_defs) - cur_start))
    return groups


# ── 2단 병합 헤더 ────────────────────────────────────────────────────

class _MultiHeaderView(QHeaderView):
    """위쪽 절반: 그룹명(병합), 아래쪽 절반: 개별 컬럼명."""

    _GROUP_BG   = QColor("#CFD8DC")   # 그룹 헤더 배경
    _GROUP_FG   = QColor("#1A237E")   # 그룹 헤더 텍스트
    _GROUP_BORDER = QColor("#90A4AE")

    def __init__(self, col_labels, groups, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._col_labels = col_labels
        self._groups = groups   # [(label, start, span), ...]
        self.setSectionsClickable(True)

    def sizeHint(self):
        sh = super().sizeHint()
        return QSize(sh.width(), sh.height() * 2)

    def paintSection(self, painter, rect, logical_index):
        if not rect.isValid():
            return
        painter.save()
        half = rect.height() // 2

        # 전체 배경 먼저 (기본 헤더 스타일)
        opt = QStyleOptionHeader()
        self.initStyleOption(opt)
        opt.rect = rect
        opt.section = logical_index
        opt.text = ""
        self.style().drawControl(QStyle.CE_Header, opt, painter, self)

        # 아래 절반: 컬럼명
        bot = QRect(rect.left(), rect.top() + half, rect.width(), half)
        opt2 = QStyleOptionHeader()
        self.initStyleOption(opt2)
        opt2.rect = bot
        opt2.section = logical_index
        opt2.text = self._col_labels[logical_index]
        opt2.textAlignment = Qt.AlignCenter
        self.style().drawControl(QStyle.CE_Header, opt2, painter, self)

        painter.restore()

    def mousePressEvent(self, event):
        # 위 절반(그룹 헤더) 클릭 시 정렬 트리거 방지
        if event.y() < self.height() // 2:
            return  # 이벤트 소비(accept), 부모로 버블링하지 않음
        super().mousePressEvent(event)

    def paintEvent(self, event):
        # 먼저 개별 섹션(아래 절반) 페인트
        super().paintEvent(event)

        # 그 위에 그룹 헤더(위 절반) 오버레이
        p = QPainter(self.viewport())
        p.save()
        half = self.height() // 2

        for group_label, start, span in self._groups:
            if start >= self.count():
                continue
            x0 = self.sectionViewportPosition(start)
            total_w = sum(
                self.sectionSize(i)
                for i in range(start, min(start + span, self.count()))
            )
            rect = QRect(x0, 0, total_w, half)
            p.fillRect(rect, self._GROUP_BG)
            p.setPen(self._GROUP_BORDER)
            p.drawRect(rect.adjusted(0, 0, -1, -1))
            fnt = self.font()
            fnt.setBold(True)
            p.setFont(fnt)
            p.setPen(self._GROUP_FG)
            p.drawText(rect.adjusted(3, 0, -3, 0), Qt.AlignCenter, group_label)

        p.restore()


# ════════════════════════════════════════════════════════════════════
# 차트 패널 헬퍼
# ════════════════════════════════════════════════════════════════════

class _ChartPanel(QFrame):
    """제목 + 컨트롤 바 + matplotlib 캔버스를 묶는 패널."""

    def __init__(self, title: str, figsize=(5.5, 3.8), dpi=92, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E0E0E0;"
            " border-radius: 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # 타이틀 바 (회색 배경)
        title_bar = QWidget()
        title_bar.setStyleSheet(
            "background-color: #F5F5F5; border-radius: 4px; padding: 2px 4px;"
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(6, 2, 6, 2)
        title_layout.setSpacing(8)

        lbl = QLabel(title)
        f = QFont(); f.setBold(True); f.setPointSize(9)
        lbl.setFont(f)
        lbl.setStyleSheet("background: transparent; color: #333333;")
        title_layout.addWidget(lbl)

        # 컨트롤 슬롯 (우측 정렬)
        title_layout.addStretch()
        self.ctrl_layout = QHBoxLayout()
        self.ctrl_layout.setSpacing(6)
        title_layout.addLayout(self.ctrl_layout)
        layout.addWidget(title_bar)

        # matplotlib 캔버스
        if HAS_MPL:
            self.fig, self.ax = plt.subplots(figsize=figsize, dpi=dpi)
            self.canvas = FigureCanvas(self.fig)
            self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self.canvas, 1)
        else:
            layout.addWidget(QLabel("matplotlib unavailable"), 1)

    def _clear(self):
        self.ax.clear()
        self.ax.set_facecolor("#F8F9FA")

    def _draw(self):
        try:
            self.fig.tight_layout(pad=0.8)
        except Exception:
            pass
        self.canvas.draw()

    def _no_data(self, msg="데이터 없음"):
        self._clear()
        self.ax.text(0.5, 0.5, msg, ha="center", va="center",
                     transform=self.ax.transAxes, color="#BDBDBD", fontsize=12,
                     fontweight="bold")
        self.ax.axis("off")
        self._draw()


# ════════════════════════════════════════════════════════════════════
# Analysis 탭
# ════════════════════════════════════════════════════════════════════

class AnalysisTab(QWidget):
    """Analysis 탭 — 4개 차트 2×2 그리드"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 캐시된 데이터: [{sample_id, sample_type, metrics:[{...}]}]
        self._data: List[dict] = []
        self._build_ui()
        self.refresh()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── 상단 글로벌 컨트롤 바 ────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("Analysis")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        title.setFont(f)
        hdr.addWidget(title)

        hdr.addWidget(QLabel("Sample Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("All Types")
        self.type_combo.currentIndexChanged.connect(self._on_filter_changed)
        hdr.addWidget(self.type_combo)

        hdr.addWidget(QLabel("Project:"))
        self._proj_combo = QComboBox()
        self._proj_combo.addItem("All Projects")
        self._proj_combo.currentIndexChanged.connect(self._on_filter_changed)
        hdr.addWidget(self._proj_combo)

        hdr.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        hdr.addWidget(btn_refresh)

        root.addLayout(hdr)

        if not HAS_MPL:
            root.addWidget(QLabel("matplotlib가 설치되지 않아 차트를 표시할 수 없습니다."))
            return

        # ── 2×2 차트 그리드 ──────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(8)

        # 1) 배치 비교
        self._panel1 = _ChartPanel("① 배치 비교 — 샘플 간 지표 비교")
        self._p1_step   = self._add_combo(self._panel1, "단계:", _ALL_STEPS)
        self._p1_metric = self._add_combo(self._panel1, "지표:", list(METRICS.keys()))
        self._p1_step.currentIndexChanged.connect(self._draw_chart1)
        self._p1_metric.currentIndexChanged.connect(self._draw_chart1)
        grid.addWidget(self._panel1, 0, 0)

        # 2) Recovery 흐름
        self._panel2 = _ChartPanel("② Recovery 흐름 — 단계별 수율 추적")
        self._p2_mode = self._add_combo(
            self._panel2, "표시:", ["Total Amount (ng)", "Recovery (%)"]
        )
        self._p2_mode.currentIndexChanged.connect(self._draw_chart2)
        grid.addWidget(self._panel2, 0, 1)

        # 3) 분포 히스토그램
        self._panel3 = _ChartPanel("③ QC 분포 히스토그램")
        self._p3_metric = self._add_combo(self._panel3, "지표:", list(METRICS.keys()))
        self._p3_metric.currentIndexChanged.connect(self._draw_chart3)
        grid.addWidget(self._panel3, 1, 0)

        # 4) 단계별 Pass/Fail 통계
        self._panel4 = _ChartPanel("④ 단계별 Pass / Warning / Fail 통계")
        # 컨트롤 없음 — 빈 스트레치로 균형 맞춤
        self._panel4.ctrl_layout.addStretch()
        grid.addWidget(self._panel4, 1, 1)

        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        charts_widget = QWidget()
        charts_widget.setLayout(grid)

        self._tab_widget = QTabWidget()
        self._tab_widget.addTab(charts_widget, "Charts")
        self._tab_widget.addTab(self._build_table_tab(), "QC Table")

        root.addWidget(self._tab_widget, 1)

    @staticmethod
    def _add_combo(panel: _ChartPanel, label: str, items: list) -> QComboBox:
        panel.ctrl_layout.addWidget(QLabel(label))
        cb = QComboBox()
        for it in items:
            cb.addItem(it)
        panel.ctrl_layout.addWidget(cb)
        return cb

    def _build_table_tab(self) -> QWidget:
        """QC Summary wide-form 표 탭 위젯 생성."""
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        # 상단 버튼 행
        top_row = QHBoxLayout()
        top_row.addStretch()
        export_btn = QPushButton("Export CSV")
        export_btn.setMaximumWidth(100)
        export_btn.clicked.connect(self._export_table_csv)
        top_row.addWidget(export_btn)
        vbox.addLayout(top_row)

        col_labels = [c[1] for c in _STEP_COL_SPEC]
        groups = _build_groups(_STEP_COL_SPEC)

        self._summary_table = QTableWidget()
        self._summary_table.setColumnCount(len(col_labels))

        header = _MultiHeaderView(col_labels, groups, self._summary_table)
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultSectionSize(80)
        header.setMinimumSectionSize(40)
        self._summary_table.setHorizontalHeader(header)

        self._summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._summary_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._summary_table.setAlternatingRowColors(True)
        self._summary_table.setSortingEnabled(True)
        header.setSortIndicatorShown(True)
        self._summary_table.verticalHeader().setDefaultSectionSize(22)
        self._summary_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        # 컬럼별 기본 폭 조정
        for i, (group, col, step, field) in enumerate(_STEP_COL_SPEC):
            if field in ("sample_id", "sample_name"):
                self._summary_table.setColumnWidth(i, 110)
            elif field == "status":
                self._summary_table.setColumnWidth(i, 62)
            elif field == "index_no":
                self._summary_table.setColumnWidth(i, 75)
            else:
                self._summary_table.setColumnWidth(i, 72)

        vbox.addWidget(self._summary_table)
        return w

    # ── 데이터 로드 ──────────────────────────────────────────────────

    def refresh(self):
        """DB에서 전체 데이터 로드 후 모든 차트 갱신."""
        try:
            with db_manager.session_scope() as session:
                samples = get_all_samples(session)
                self._data = []
                for s in samples:
                    metrics = get_qc_metrics_by_sample(session, s.sample_id)
                    self._data.append({
                        "sample_id":   s.sample_id,
                        "sample_name": s.sample_name or "",
                        "sample_type": s.sample_type or "",
                        "project":     getattr(s, 'project', None) or "",
                        "metrics": [
                            {
                                "step":           m.step,
                                "instrument":     m.instrument,
                                "concentration":  m.concentration,
                                "total_amount":   m.total_amount,
                                "gqn_rin":        m.gqn_rin,
                                "avg_size":       m.avg_size,
                                "purity_260_280": m.purity_260_280,
                                "index_no":       m.index_no,
                                "status":         m.status,
                                "measured_at":    m.measured_at,
                            }
                            for m in metrics
                        ],
                    })
        except Exception as e:
            logger.error(f"Analysis data load failed: {e}")
            self._data = []

        # 타입 필터 콤보 갱신
        types = sorted({d["sample_type"] for d in self._data if d["sample_type"]})
        self.type_combo.blockSignals(True)
        prev = self.type_combo.currentText()
        self.type_combo.clear()
        self.type_combo.addItem("All Types")
        for t in types:
            self.type_combo.addItem(t)
        idx = self.type_combo.findText(prev)
        self.type_combo.setCurrentIndex(max(idx, 0))
        self.type_combo.blockSignals(False)

        # 프로젝트 필터 콤보 갱신
        projects = sorted({d["project"] for d in self._data if d["project"]})
        self._proj_combo.blockSignals(True)
        prev_proj = self._proj_combo.currentText()
        self._proj_combo.clear()
        self._proj_combo.addItem("All Projects")
        for p in projects:
            self._proj_combo.addItem(p)
        proj_idx = self._proj_combo.findText(prev_proj)
        self._proj_combo.setCurrentIndex(max(proj_idx, 0))
        self._proj_combo.blockSignals(False)

        self._draw_all()
        self._refresh_table()

    def _get_thresholds(self, metric: str) -> List[tuple]:
        """현재 선택된 샘플 타입에 맞는 QC 기준선 반환."""
        if metric != "gqn_rin":
            return _THRESHOLDS.get(metric, [])
        stype = self.type_combo.currentText()
        if stype == "mRNA-seq":
            return [
                (8.0, "Pass", _STATUS_COLOR["Pass"]),
                (6.0, "Warning", _STATUS_COLOR["Warning"]),
            ]
        # WGS 또는 All Types → DNA 기준
        return [
            (7.0, "Pass", _STATUS_COLOR["Pass"]),
            (5.0, "Warning", _STATUS_COLOR["Warning"]),
        ]

    def _filtered_data(self) -> List[dict]:
        data = self._data
        stype = self.type_combo.currentText()
        proj = self._proj_combo.currentText()
        if stype != "All Types":
            data = [d for d in data if d["sample_type"] == stype]
        if proj != "All Projects":
            data = [d for d in data if d["project"] == proj]
        return data

    def _on_filter_changed(self):
        self._draw_all()
        self._refresh_table()

    # ── QC Summary 표 ────────────────────────────────────────────────

    def _pivot_to_wide(self, data: List[dict]) -> List[dict]:
        """샘플별 long-form metrics → step × field wide-form 행 리스트."""
        rows = []
        for s in data:
            row: dict = {
                "sample_id":   s["sample_id"],
                "sample_name": s["sample_name"],
                "project":     s["project"],
            }
            by_step: dict = {}
            for m in s["metrics"]:
                by_step.setdefault(m["step"], []).append(m)

            for step in _ALL_STEPS:
                mets = by_step.get(step, [])
                qubit    = next((m for m in mets if m.get("instrument") == "Qubit"),    None)
                nanodrop = next((m for m in mets if m.get("instrument") == "NanoDrop"), None)
                primary  = qubit or nanodrop or (mets[0] if mets else None)
                pfx = step + "__"
                row[pfx + "concentration"]  = primary.get("concentration")  if primary  else None
                row[pfx + "total_amount"]   = primary.get("total_amount")   if primary  else None
                row[pfx + "purity_260_280"] = nanodrop.get("purity_260_280") if nanodrop else None
                row[pfx + "avg_size"]       = primary.get("avg_size")       if primary  else None
                row[pfx + "index_no"]       = primary.get("index_no")       if primary  else None

                # gqn_rin: primary(Qubit/NanoDrop) 우선, 없으면 다른 기기(Femto Pulse) 탐색
                # RNA Extraction의 RQN(=RIN)은 Femto Pulse 레코드의 gqn_rin에 저장됨
                rin_val = primary.get("gqn_rin") if primary else None
                if rin_val is None:
                    for m in mets:
                        if m.get("gqn_rin") is not None:
                            rin_val = m["gqn_rin"]
                            break
                row[pfx + "gqn_rin"] = rin_val

                # status: 해당 step의 모든 기기 판정 중 가장 나쁜 값 사용
                _order = {"Pass": 0, "Warning": 1, "Fail": 2}
                worst = None
                for m in mets:
                    s = m.get("status")
                    if s in _order:
                        if worst is None or _order[s] > _order[worst]:
                            worst = s
                row[pfx + "status"] = worst
            rows.append(row)
        return rows

    def _apply_column_visibility(self):
        """선택된 Sample Type에 따라 DNA/RNA 스텝 컬럼을 동적으로 숨기거나 표시한다."""
        if not hasattr(self, "_summary_table"):
            return
        stype = self.type_combo.currentText()
        is_rna = stype in _RNA_SAMPLE_TYPES
        is_dna = stype != "All Types" and stype not in _RNA_SAMPLE_TYPES

        rna_steps = set(RNA_QC_STEPS)
        dna_steps = set(QC_STEPS)

        for c, (group, col_label, step, field) in enumerate(_STEP_COL_SPEC):
            if step is None:          # Sample Info — 항상 표시
                hidden = False
            elif step in rna_steps:   # RNA 전용 컬럼
                hidden = is_dna
            elif step in dna_steps:   # DNA 전용 컬럼
                hidden = is_rna
            else:
                hidden = False
            self._summary_table.setColumnHidden(c, hidden)

    def _refresh_table(self):
        """필터된 데이터로 QC Summary 표를 갱신한다."""
        if not hasattr(self, "_summary_table"):
            return
        self._apply_column_visibility()
        wide_rows = self._pivot_to_wide(self._filtered_data())
        self._summary_table.setRowCount(len(wide_rows))

        # Status 색상 (배경 반투명하게)
        _status_bg = {
            "Pass":    QColor(76, 175, 80, 60),
            "Warning": QColor(255, 152, 0, 60),
            "Fail":    QColor(244, 67, 54, 70),
        }

        _numeric_fields = {"concentration", "total_amount", "purity_260_280", "gqn_rin", "avg_size"}

        self._summary_table.setSortingEnabled(False)
        for r, row in enumerate(wide_rows):
            for c, (group, col_label, step, field) in enumerate(_STEP_COL_SPEC):
                key = (step + "__" + field) if step else field
                val = row.get(key)

                # 표시 텍스트
                if val is None:
                    text = ""
                elif field in _numeric_fields:
                    text = _fmt(val)
                else:
                    text = str(val)

                item = _SortableItem(text) if field in _numeric_fields else QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)

                if field == "status" and val in _status_bg:
                    item.setBackground(_status_bg[val])

                self._summary_table.setItem(r, c, item)
        self._summary_table.setSortingEnabled(True)

    def _export_table_csv(self):
        """현재 표시된 QC Summary 표를 CSV로 내보낸다."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export QC Summary", "qc_summary.csv",
            "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return

        import csv
        wide_rows = self._pivot_to_wide(self._filtered_data())

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                # 헤더 1행: 그룹명
                writer.writerow([c[0] for c in _STEP_COL_SPEC])
                # 헤더 2행: 컬럼명
                writer.writerow([c[1] for c in _STEP_COL_SPEC])
                # 데이터 행
                for row in wide_rows:
                    out = []
                    for group, col_label, step, field in _STEP_COL_SPEC:
                        key = (step + "__" + field) if step else field
                        val = row.get(key)
                        out.append("" if val is None else val)
                    writer.writerow(out)
            logger.info(f"QC summary exported: {path}")
        except Exception as e:
            logger.error(f"CSV export failed: {e}")

    def _draw_all(self):
        if not HAS_MPL:
            return
        self._draw_chart1()
        self._draw_chart2()
        self._draw_chart3()
        self._draw_chart4()

    # ════════════════════════════════════════════════════════════════
    # Chart 1 : 배치 비교 바 차트
    # ════════════════════════════════════════════════════════════════

    def _draw_chart1(self):
        data = self._filtered_data()
        step   = self._p1_step.currentText()
        metric = METRICS[self._p1_metric.currentText()]
        label  = self._p1_metric.currentText()

        panel = self._panel1
        panel._clear()
        ax = panel.ax

        # 선택 단계에서 각 샘플의 대표값 (마지막 측정값 우선)
        sample_ids, values, colors = [], [], []
        for d in data:
            step_metrics = [m for m in d["metrics"] if m["step"] == step
                            and m.get(metric) is not None]
            if not step_metrics:
                continue
            # 마지막 측정값
            m = step_metrics[-1]
            sample_ids.append(d["sample_id"])
            values.append(m[metric])
            colors.append(_STATUS_COLOR.get(m["status"] or "No Data", "#9E9E9E"))

        if not sample_ids:
            panel._no_data(f"'{step}' 단계 데이터 없음")
            return

        x = np.arange(len(sample_ids))
        # 샘플 수에 따라 bar width 조절
        bar_w = max(0.3, min(0.65, 6 / max(len(sample_ids), 1)))
        bars = ax.bar(x, values, color=colors, edgecolor="white",
                      linewidth=0.6, width=bar_w, zorder=3)

        # 값 레이블 (바 수가 많으면 생략)
        if len(values) <= 20:
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + max(values) * 0.015,
                        f"{val:.1f}", ha="center", va="bottom", fontsize=7.5,
                        color="#333333")

        # QC 기준선
        from matplotlib.patches import Patch
        thresh_handles = []
        for thresh_val, thresh_label, thresh_color in self._get_thresholds(metric):
            ax.axhline(thresh_val, color=thresh_color, linestyle="--",
                       linewidth=1.4, alpha=0.9, zorder=4)
            thresh_handles.append(
                Patch(facecolor=thresh_color, alpha=0.7,
                      label=f"{thresh_label} ≥{thresh_val}")
            )

        ax.set_xticks(x)
        # 샘플 ID를 짧게 표시
        short_labels = [sid.split("-")[-1] if len(sid) > 14 else sid
                        for sid in sample_ids]
        ax.set_xticklabels(short_labels, rotation=35, ha="right", fontsize=7.5)
        ax.set_ylabel(label, fontsize=8.5)
        ax.set_title(f"{step}  ·  {label}", fontsize=10, fontweight="bold",
                     color="#222222")
        ax.set_xlim(-0.6, len(sample_ids) - 0.4)
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))

        # 상태 색상 범례 + 기준선 범례
        status_handles = [
            Patch(facecolor=c, label=s, edgecolor="white")
            for s, c in _STATUS_COLOR.items()
            if any(col == c for col in colors)
        ]
        all_handles = status_handles + thresh_handles
        if all_handles:
            ax.legend(handles=all_handles, fontsize=7.5, loc="upper right",
                      ncol=min(len(all_handles), 3))

        panel._draw()

    # ════════════════════════════════════════════════════════════════
    # Chart 2 : Recovery 흐름 라인 차트
    # ════════════════════════════════════════════════════════════════

    def _draw_chart2(self):
        data   = self._filtered_data()
        mode   = self._p2_mode.currentText()
        show_pct = "Recovery" in mode

        panel = self._panel2
        panel._clear()
        ax = panel.ax

        plotted = 0
        lines_drawn = []  # (line, label)
        for i, d in enumerate(data):
            step_vals: Dict[str, float] = {}
            for m in d["metrics"]:
                if m["total_amount"] is not None and m["step"] in _ALL_STEPS:
                    if m["step"] not in step_vals or m["instrument"] == "Qubit":
                        step_vals[m["step"]] = m["total_amount"]

            ordered_steps = [s for s in _ALL_STEPS if s in step_vals]
            if len(ordered_steps) < 2:
                continue

            if show_pct:
                first_val = step_vals[ordered_steps[0]]
                if first_val == 0:
                    continue
                y_vals = [step_vals[s] / first_val * 100 for s in ordered_steps]
                y_vals[0] = 100.0
            else:
                y_vals = [step_vals[s] for s in ordered_steps]

            x = np.arange(len(ordered_steps))
            color = _SAMPLE_PALETTE[i % len(_SAMPLE_PALETTE)]
            lw = 1.6 if len(data) <= 10 else 1.2
            ms = 5 if len(data) <= 10 else 3.5
            line, = ax.plot(x, y_vals, marker="o", linewidth=lw, markersize=ms,
                            color=color, alpha=0.85, label=d["sample_id"])
            lines_drawn.append((line, d["sample_id"]))

            # 숫자 레이블: 10개 이하일 때만
            if len(data) <= 10:
                for xi, yi in zip(x, y_vals):
                    ax.annotate(f"{yi:.0f}", (xi, yi),
                                textcoords="offset points", xytext=(0, 7),
                                ha="center", fontsize=7, color=color, fontweight="bold")
            plotted += 1

        if plotted == 0:
            panel._no_data("Total Amount 데이터 없음\n(Qubit 측정값 2단계 이상 필요)")
            return

        all_steps_present = sorted(
            {s for d in data for m in d["metrics"] if m["step"] in _ALL_STEPS
             for s in [m["step"]]},
            key=lambda s: _ALL_STEPS.index(s)
        )
        ax.set_xticks(np.arange(len(all_steps_present)))
        ax.set_xticklabels(all_steps_present, rotation=20, ha="right", fontsize=8)
        ax.set_ylabel("Recovery (%)" if show_pct else "Total Amount (ng)", fontsize=8.5)
        ax.set_title("단계별  " + ("Recovery (%)" if show_pct else "Total Amount (ng)"),
                     fontsize=10, fontweight="bold", color="#222222")
        if show_pct:
            ax.axhline(100, color="#BDBDBD", linestyle="--", linewidth=0.9)

        # ── 범례 전략: 샘플 수에 따라 자동 선택 ──────────────────────
        n = len(lines_drawn)
        if n <= 8:
            # 차트 내부 우상단
            ax.legend(fontsize=7.5, loc="upper right", ncol=1)
        elif n <= 16:
            # 차트 오른쪽 외부
            panel.fig.subplots_adjust(right=0.72)
            ax.legend(fontsize=6.5, loc="upper left",
                      bbox_to_anchor=(1.01, 1.0), borderaxespad=0,
                      ncol=1, handlelength=1.5)
        else:
            # 너무 많으면 범례 생략 → 제목에 n 표기
            ax.set_title(
                "단계별  " + ("Recovery (%)" if show_pct else "Total Amount (ng)")
                + f"  (n={n})",
                fontsize=10, fontweight="bold", color="#222222"
            )

        panel._draw()

    # ════════════════════════════════════════════════════════════════
    # Chart 3 : 분포 히스토그램
    # ════════════════════════════════════════════════════════════════

    def _draw_chart3(self):
        data   = self._filtered_data()
        metric = METRICS[self._p3_metric.currentText()]
        label  = self._p3_metric.currentText()

        panel = self._panel3
        panel._clear()
        ax = panel.ax

        # 모든 샘플의 해당 지표 값 수집 (step 무관, 중복 포함)
        values = [
            m[metric] for d in data for m in d["metrics"]
            if m.get(metric) is not None
        ]

        if not values:
            panel._no_data(f"'{label}' 데이터 없음")
            return

        all_mets = [m for d_ in data for m in d_["metrics"] if m.get(metric) is not None]
        arr = np.array(values)
        bins = min(max(int(len(arr) ** 0.5) + 3, 6), 25)
        rng = (arr.min(), arr.max())
        if rng[0] == rng[1]:
            rng = (rng[0] - 0.5, rng[1] + 0.5)
        bin_edges = np.linspace(rng[0], rng[1], bins + 1)

        # 상태별 분리
        groups = {"Pass": [], "Warning": [], "Fail": [], "No Status": []}
        for v, m in zip(values, all_mets):
            s = m.get("status") or "No Status"
            groups.get(s, groups["No Status"]).append(v)

        color_map = {
            "Pass":      (_STATUS_COLOR["Pass"],    0.80),
            "Warning":   (_STATUS_COLOR["Warning"], 0.80),
            "Fail":      (_STATUS_COLOR["Fail"],    0.80),
            "No Status": (_STATUS_COLOR["No Data"], 0.55),
        }
        for s, (color, alpha) in color_map.items():
            if groups[s]:
                ax.hist(groups[s], bins=bin_edges, color=color, alpha=alpha,
                        edgecolor="white", linewidth=0.6, label=f"{s} (n={len(groups[s])})",
                        zorder=3)

        # QC 기준선
        from matplotlib.lines import Line2D
        thresh_handles = []
        for thresh_val, thresh_label, thresh_color in self._get_thresholds(metric):
            ax.axvline(thresh_val, color=thresh_color, linestyle="--",
                       linewidth=1.8, alpha=0.95, zorder=4)
            thresh_handles.append(Line2D([0], [0], color=thresh_color, linestyle="--",
                                         linewidth=1.5, label=f"{thresh_label} ≥{thresh_val}"))

        # 평균선
        mean_line = Line2D([0], [0], color="#555555", linestyle=":",
                           linewidth=1.5, label=f"Mean {arr.mean():.2f}")
        ax.axvline(arr.mean(), color="#555555", linestyle=":", linewidth=1.5, zorder=4)

        ax.set_xlabel(label, fontsize=8.5, labelpad=4)
        ax.set_ylabel("Count", fontsize=8.5, labelpad=4)
        ax.set_title(f"{label}  분포  (n={len(arr)})", fontsize=10,
                     fontweight="bold", color="#222222")
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

        handles, legends = ax.get_legend_handles_labels()
        ax.legend(handles + thresh_handles + [mean_line],
                  legends + [h.get_label() for h in thresh_handles + [mean_line]],
                  fontsize=7.5, framealpha=0.9, ncol=2)

        panel._draw()

    # ════════════════════════════════════════════════════════════════
    # Chart 4 : 단계별 Pass/Fail 스택 바 차트
    # ════════════════════════════════════════════════════════════════

    def _draw_chart4(self):
        data = self._filtered_data()

        panel = self._panel4
        panel._clear()
        ax = panel.ax

        if not data:
            panel._no_data()
            return

        # 단계별로 상태 카운트
        step_counts: Dict[str, Dict[str, int]] = {
            step: {"Pass": 0, "Warning": 0, "Fail": 0, "No Status": 0}
            for step in _ALL_STEPS
        }

        for d in data:
            seen_steps: Dict[str, str] = {}  # step -> 대표 status
            for m in d["metrics"]:
                step = m["step"]
                if step not in step_counts:
                    continue
                status = m["status"] or "No Status"
                # 같은 step에 여러 기록: 가장 낮은 상태 우선 (Fail > Warning > Pass)
                priority = {"Fail": 0, "Warning": 1, "Pass": 2, "No Status": 3}
                if step not in seen_steps or (
                    priority.get(status, 3) < priority.get(seen_steps[step], 3)
                ):
                    seen_steps[step] = status
            for step, status in seen_steps.items():
                step_counts[step][status] += 1

        # 데이터가 있는 단계만 표시
        active_steps = [s for s in _ALL_STEPS
                        if sum(step_counts[s].values()) > 0]
        if not active_steps:
            panel._no_data("QC 상태 데이터 없음\n(NanoDrop/Qubit 측정 후 표시됩니다)")
            return

        x = np.arange(len(active_steps))
        width = min(0.55, 4.5 / max(len(active_steps), 1))

        status_order = [
            ("Pass",      _STATUS_COLOR["Pass"]),
            ("Warning",   _STATUS_COLOR["Warning"]),
            ("Fail",      _STATUS_COLOR["Fail"]),
            ("No Status", _STATUS_COLOR["No Data"]),
        ]

        bottoms = np.zeros(len(active_steps))
        for status_key, color in status_order:
            counts = np.array([step_counts[s][status_key] for s in active_steps])
            if counts.sum() == 0:
                continue
            bars = ax.bar(x, counts, width, bottom=bottoms,
                          color=color, edgecolor="white", linewidth=0.8,
                          label=status_key, zorder=3)
            for bar, cnt, bot in zip(bars, counts, bottoms):
                if cnt > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bot + cnt / 2, str(int(cnt)),
                            ha="center", va="center",
                            fontsize=9, fontweight="bold", color="white",
                            zorder=4)
            bottoms += counts

        totals = np.array([sum(step_counts[s].values()) for s in active_steps])
        for xi, tot in zip(x, totals):
            if tot > 0:
                ax.text(xi, tot + max(totals) * 0.02, f"n={int(tot)}",
                        ha="center", va="bottom", fontsize=8, color="#444444",
                        fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels(active_steps, rotation=22, ha="right", fontsize=8)
        ax.set_ylabel("샘플 수", fontsize=8.5, labelpad=4)
        ax.set_ylim(0, max(totals) * 1.28)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        ax.set_title("단계별 QC 상태 분포", fontsize=10, fontweight="bold",
                     color="#222222")
        ax.legend(fontsize=8, loc="upper right", framealpha=0.9,
                  ncol=min(4, len(status_order)))

        panel._draw()

    # ── GUI 상태 저장/복원 ────────────────────────────────────────────

    def save_gui_state(self, settings):
        from config.gui_state import save_combo
        save_combo(settings, "AnalysisTab/typeCombo",  self.type_combo)
        save_combo(settings, "AnalysisTab/projCombo",  self._proj_combo)
        save_combo(settings, "AnalysisTab/p1Step",     self._p1_step)
        save_combo(settings, "AnalysisTab/p1Metric",   self._p1_metric)
        save_combo(settings, "AnalysisTab/p2Mode",     self._p2_mode)
        save_combo(settings, "AnalysisTab/p3Metric",   self._p3_metric)

    def restore_gui_state(self, settings):
        from config.gui_state import restore_combo
        # 콤보 복원 시 차트 재그리기를 방지하기 위해 시그널 임시 차단
        for combo, key in [
            (self.type_combo,  "AnalysisTab/typeCombo"),
            (self._proj_combo, "AnalysisTab/projCombo"),
            (self._p1_step,    "AnalysisTab/p1Step"),
            (self._p1_metric,  "AnalysisTab/p1Metric"),
            (self._p2_mode,    "AnalysisTab/p2Mode"),
            (self._p3_metric,  "AnalysisTab/p3Metric"),
        ]:
            combo.blockSignals(True)
            restore_combo(settings, key, combo)
            combo.blockSignals(False)

        # 복원된 필터를 차트·표에 즉시 적용
        self._draw_all()
        self._refresh_table()
