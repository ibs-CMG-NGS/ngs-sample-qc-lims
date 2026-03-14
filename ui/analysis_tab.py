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
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavToolbar
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from config.settings import QC_STEPS, RNA_QC_STEPS, QC_CRITERIA, STATUS_COLORS

_ALL_STEPS = QC_STEPS + RNA_QC_STEPS
from database import db_manager, get_all_samples, get_qc_metrics_by_sample

logger = logging.getLogger(__name__)

# ── 색상 상수 ──────────────────────────────────────────────────────
_STATUS_COLOR = {
    "Pass":    STATUS_COLORS["Pass"],
    "Warning": STATUS_COLORS["Warning"],
    "Fail":    STATUS_COLORS["Fail"],
    "No Data": "#9E9E9E",
}
_STEP_COLORS = [
    "#1565C0", "#2E7D32", "#6A1B9A", "#E65100", "#00695C",
    "#AD1457", "#37474F", "#F57F17",
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


# ════════════════════════════════════════════════════════════════════
# 차트 패널 헬퍼
# ════════════════════════════════════════════════════════════════════

class _ChartPanel(QFrame):
    """제목 + 컨트롤 바 + matplotlib 캔버스를 묶는 패널."""

    def __init__(self, title: str, figsize=(5.5, 3.8), dpi=90, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)

        # 제목
        lbl = QLabel(title)
        f = QFont(); f.setBold(True); f.setPointSize(9)
        lbl.setFont(f)
        layout.addWidget(lbl)

        # 컨트롤 슬롯 (서브클래스가 채움)
        self.ctrl_layout = QHBoxLayout()
        self.ctrl_layout.setSpacing(6)
        layout.addLayout(self.ctrl_layout)

        # matplotlib 캔버스
        if HAS_MPL:
            self.fig, self.ax = plt.subplots(figsize=figsize, dpi=dpi)
            self.fig.patch.set_facecolor("#FAFAFA")
            self.canvas = FigureCanvas(self.fig)
            self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self.canvas, 1)
        else:
            layout.addWidget(QLabel("matplotlib unavailable"), 1)

    def _clear(self):
        self.ax.clear()
        self.ax.set_facecolor("#FAFAFA")

    def _draw(self):
        try:
            self.fig.tight_layout(pad=0.6)
        except Exception:
            pass
        self.canvas.draw()

    def _no_data(self, msg="데이터 없음"):
        self._clear()
        self.ax.text(0.5, 0.5, msg, ha="center", va="center",
                     transform=self.ax.transAxes, color="#9E9E9E", fontsize=11)
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

        root.addLayout(grid, 1)

    @staticmethod
    def _add_combo(panel: _ChartPanel, label: str, items: list) -> QComboBox:
        panel.ctrl_layout.addWidget(QLabel(label))
        cb = QComboBox()
        for it in items:
            cb.addItem(it)
        panel.ctrl_layout.addWidget(cb)
        return cb

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
        bars = ax.bar(x, values, color=colors, edgecolor="white", linewidth=0.8, width=0.6)

        # 값 레이블
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.01,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=8)

        # QC 기준선
        for thresh_val, thresh_label, thresh_color in self._get_thresholds(metric):
            ax.axhline(thresh_val, color=thresh_color, linestyle="--",
                       linewidth=1.2, alpha=0.8, label=f"{thresh_label} ({thresh_val})")
            ax.legend(fontsize=7, loc="upper right", framealpha=0.8)

        ax.set_xticks(x)
        ax.set_xticklabels(sample_ids, rotation=20, ha="right", fontsize=8)
        ax.set_ylabel(label, fontsize=8)
        ax.set_title(f"{step}  —  {label}", fontsize=9, fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)

        # 범례 (상태 색상)
        from matplotlib.patches import Patch
        legend_handles = [
            Patch(facecolor=c, label=s)
            for s, c in _STATUS_COLOR.items()
            if any(col == c for col in colors)
        ]
        if legend_handles:
            ax.legend(handles=legend_handles, fontsize=7,
                      loc="upper left", framealpha=0.8)

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
        for i, d in enumerate(data):
            # 단계 순서에 따라 total_amount 정렬
            step_vals: Dict[str, float] = {}
            for m in d["metrics"]:
                if m["total_amount"] is not None and m["step"] in _ALL_STEPS:
                    # 같은 step에 여러 기록이 있으면 마지막 Qubit 우선
                    if m["step"] not in step_vals or m["instrument"] == "Qubit":
                        step_vals[m["step"]] = m["total_amount"]

            ordered_steps = [s for s in _ALL_STEPS if s in step_vals]
            if len(ordered_steps) < 2:
                continue

            x_labels = ordered_steps
            if show_pct:
                first_val = step_vals[ordered_steps[0]]
                if first_val == 0:
                    continue
                y_vals = [step_vals[s] / first_val * 100 for s in ordered_steps]
                y_vals[0] = 100.0   # 첫 단계는 항상 100%
            else:
                y_vals = [step_vals[s] for s in ordered_steps]

            x = np.arange(len(x_labels))
            color = _STEP_COLORS[i % len(_STEP_COLORS)]
            ax.plot(x, y_vals, marker="o", linewidth=1.8, markersize=5,
                    color=color, label=d["sample_id"])
            for xi, yi in zip(x, y_vals):
                ax.annotate(f"{yi:.0f}", (xi, yi),
                            textcoords="offset points", xytext=(0, 6),
                            ha="center", fontsize=7, color=color)
            plotted += 1

        if plotted == 0:
            panel._no_data("Total Amount 데이터 없음\n(Qubit 측정값 2단계 이상 필요)")
            return

        # x축은 _ALL_STEPS 전체 기준
        all_steps_present = sorted(
            {s for d in data for m in d["metrics"] if m["step"] in _ALL_STEPS
             for s in [m["step"]]},
            key=lambda s: _ALL_STEPS.index(s)
        )
        ax.set_xticks(np.arange(len(all_steps_present)))
        ax.set_xticklabels(all_steps_present, rotation=18, ha="right", fontsize=8)
        ax.set_ylabel("Recovery (%)" if show_pct else "Total Amount (ng)", fontsize=8)
        ax.set_title("단계별 " + ("Recovery (%)" if show_pct else "Total Amount (ng)"),
                     fontsize=9, fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
        if show_pct:
            ax.axhline(100, color="#BDBDBD", linestyle="--", linewidth=0.8)
        ax.legend(fontsize=7, loc="upper right", framealpha=0.8)

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

        arr = np.array(values)
        bins = min(max(int(len(arr) ** 0.5) + 2, 5), 30)

        # 상태별 색상 분리
        pass_vals    = [v for v, d in zip(values, [
            m for d_ in data for m in d_["metrics"] if m.get(metric) is not None
        ]) if d.get("status") == "Pass"]
        warn_vals    = [v for v, d in zip(values, [
            m for d_ in data for m in d_["metrics"] if m.get(metric) is not None
        ]) if d.get("status") == "Warning"]
        fail_vals    = [v for v, d in zip(values, [
            m for d_ in data for m in d_["metrics"] if m.get(metric) is not None
        ]) if d.get("status") == "Fail"]
        nodata_vals  = [v for v, d in zip(values, [
            m for d_ in data for m in d_["metrics"] if m.get(metric) is not None
        ]) if d.get("status") not in ("Pass", "Warning", "Fail")]

        rng = (arr.min(), arr.max())
        bin_edges = np.linspace(rng[0], rng[1], bins + 1)

        for vals, color, label_s in [
            (pass_vals,   _STATUS_COLOR["Pass"],    "Pass"),
            (warn_vals,   _STATUS_COLOR["Warning"], "Warning"),
            (fail_vals,   _STATUS_COLOR["Fail"],    "Fail"),
            (nodata_vals, _STATUS_COLOR["No Data"], "No Status"),
        ]:
            if vals:
                ax.hist(vals, bins=bin_edges, color=color, alpha=0.75,
                        edgecolor="white", linewidth=0.5, label=label_s)

        # QC 기준선
        for thresh_val, thresh_label, thresh_color in self._get_thresholds(metric):
            ax.axvline(thresh_val, color=thresh_color, linestyle="--",
                       linewidth=1.5, alpha=0.9,
                       label=f"{thresh_label} threshold ({thresh_val})")

        # 통계 표시
        ax.axvline(arr.mean(), color="#333333", linestyle=":",
                   linewidth=1.2, label=f"Mean ({arr.mean():.2f})")

        ax.set_xlabel(label, fontsize=8)
        ax.set_ylabel("Count", fontsize=8)
        ax.set_title(f"{label} 분포  (n={len(arr)})", fontsize=9, fontweight="bold")
        ax.tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=7, framealpha=0.8)

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
        width = 0.55

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
                          color=color, edgecolor="white", linewidth=0.6,
                          label=status_key)
            # 값 레이블 (0이 아닌 경우만)
            for bar, cnt, bot in zip(bars, counts, bottoms):
                if cnt > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bot + cnt / 2,
                            str(int(cnt)),
                            ha="center", va="center",
                            fontsize=9, fontweight="bold", color="white")
            bottoms += counts

        # 전체 합계 레이블 (바 위)
        totals = np.array([sum(step_counts[s].values()) for s in active_steps])
        for xi, tot in zip(x, totals):
            if tot > 0:
                ax.text(xi, tot + 0.05, f"n={int(tot)}",
                        ha="center", va="bottom", fontsize=8, color="#333333")

        ax.set_xticks(x)
        ax.set_xticklabels(active_steps, rotation=18, ha="right", fontsize=8)
        ax.set_ylabel("샘플 수", fontsize=8)
        ax.set_ylim(0, max(totals) * 1.25)
        ax.set_title("단계별 QC 상태 분포", fontsize=9, fontweight="bold")
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(fontsize=7, loc="upper right", framealpha=0.8)

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
