"""
Femto Pulse Ladder Comparison Dialog
선택한 FemtoPulseRun들의 ladder electropherogram + size calibration curve 오버레이
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
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

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavToolbar
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from config.settings import QC_STEPS
from database import db_manager
from database.models import FemtoPulseRun
from parsers import extract_ladder_trace, parse_size_calibration

logger = logging.getLogger(__name__)

# run별 색상 (최대 10개)
_RUN_COLORS = [
    "#1565C0", "#C62828", "#2E7D32", "#6A1B9A",
    "#E65100", "#00695C", "#AD1457", "#37474F",
    "#F57F17", "#0277BD",
]


class LadderCompareDialog(QDialog):
    """Femto Pulse ladder 비교 다이얼로그.

    - 왼쪽: FemtoPulseRun 체크박스 목록 (Step 필터, Select All / Clear)
    - 오른쪽: 두 개의 matplotlib 차트
        ① Ladder Electropherogram overlay  (size bp vs RFU)
        ② Size Calibration Curves overlay  (ladder size bp vs migration time sec)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Femto Pulse — Ladder Comparison")
        self.setMinimumSize(1050, 680)
        self._runs: List[dict] = []
        self._cache: Dict[int, Tuple] = {}  # run_id -> (electro, calib)
        self._build_ui()
        self._load_runs()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 상단 컨트롤 바 ──────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Step:"))

        self._step_combo = QComboBox()
        self._step_combo.addItem("All Steps")
        for s in QC_STEPS:
            self._step_combo.addItem(s)
        self._step_combo.currentIndexChanged.connect(self._on_filter_changed)
        top_bar.addWidget(self._step_combo)
        top_bar.addSpacing(12)

        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self._select_all)
        top_bar.addWidget(btn_all)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_all)
        top_bar.addWidget(btn_clear)

        top_bar.addSpacing(20)
        top_bar.addWidget(QLabel("X-axis max:"))
        self._xmax_combo = QComboBox()
        for label_text, bp in [
            ("50 kbp",  50_000),
            ("100 kbp", 100_000),
            ("200 kbp", 200_000),
            ("500 kbp", 500_000),
            ("All",     None),
        ]:
            self._xmax_combo.addItem(label_text, bp)
        self._xmax_combo.setCurrentIndex(2)  # 200 kbp default
        self._xmax_combo.currentIndexChanged.connect(self._redraw)
        top_bar.addWidget(self._xmax_combo)

        top_bar.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._load_runs)
        top_bar.addWidget(btn_refresh)

        layout.addLayout(top_bar)

        # ── 메인 스플리터 ────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # 왼쪽: Run 목록
        self._run_table = QTableWidget()
        self._run_table.setColumnCount(3)
        self._run_table.setHorizontalHeaderLabels(["Date", "Step", "Folder"])
        self._run_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._run_table.setSelectionMode(QAbstractItemView.NoSelection)
        self._run_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._run_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._run_table.horizontalHeader().setStretchLastSection(True)
        self._run_table.setMinimumWidth(330)
        self._run_table.itemChanged.connect(self._on_check_changed)
        splitter.addWidget(self._run_table)

        # 오른쪽: matplotlib 차트
        if HAS_MPL:
            self._fig, (self._ax1, self._ax2) = plt.subplots(
                2, 1, figsize=(7, 6), dpi=90
            )
            self._fig.patch.set_facecolor("#FAFAFA")
            self._canvas = FigureCanvas(self._fig)
            self._canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            right_widget = QWidget()
            right_layout = QVBoxLayout(right_widget)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(0)
            nav = NavToolbar(self._canvas, right_widget)
            right_layout.addWidget(nav)
            right_layout.addWidget(self._canvas, 1)
            splitter.addWidget(right_widget)
        else:
            splitter.addWidget(QLabel("matplotlib 미설치 — 차트를 표시할 수 없습니다."))

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        # ── 하단 닫기 버튼 ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    # ── 데이터 로드 ──────────────────────────────────────────────────

    def _load_runs(self):
        """DB에서 FemtoPulseRun 목록 로드."""
        try:
            with db_manager.session_scope() as session:
                runs = (
                    session.query(FemtoPulseRun)
                    .order_by(FemtoPulseRun.created_at.desc())
                    .all()
                )
                self._runs = [
                    {
                        "id": r.id,
                        "step": r.step or "",
                        "measured_at": r.measured_at,
                        "created_at": r.created_at,
                        "run_folder": r.run_folder or "",
                        "electropherogram_path": r.electropherogram_path,
                        "size_calibration_path": r.size_calibration_path,
                    }
                    for r in runs
                ]
        except Exception as e:
            logger.error(f"LadderCompare DB load failed: {e}")
            self._runs = []

        self._cache.clear()
        self._refresh_table()

    def _refresh_table(self):
        """Step 필터 적용 후 테이블 갱신."""
        step_filter = self._step_combo.currentText()
        filtered = [
            r for r in self._runs
            if step_filter == "All Steps" or r["step"] == step_filter
        ]

        self._run_table.blockSignals(True)
        self._run_table.setRowCount(len(filtered))
        for row, r in enumerate(filtered):
            display_dt = r["measured_at"] or r["created_at"]
            date_str = display_dt.strftime("%Y-%m-%d") if display_dt else "-"

            date_item = QTableWidgetItem(date_str)
            date_item.setData(Qt.UserRole, r["id"])
            date_item.setCheckState(Qt.Unchecked)
            date_item.setFlags(date_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            self._run_table.setItem(row, 0, date_item)
            self._run_table.setItem(row, 1, QTableWidgetItem(r["step"]))

            folder_name = Path(r["run_folder"]).name if r["run_folder"] else "-"
            self._run_table.setItem(row, 2, QTableWidgetItem(folder_name))

        self._run_table.blockSignals(False)
        self._redraw()

    # ── 체크박스 / 필터 조작 ─────────────────────────────────────────

    def _on_filter_changed(self):
        self._refresh_table()

    def _select_all(self):
        self._run_table.blockSignals(True)
        for row in range(self._run_table.rowCount()):
            item = self._run_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self._run_table.blockSignals(False)
        self._redraw()

    def _clear_all(self):
        self._run_table.blockSignals(True)
        for row in range(self._run_table.rowCount()):
            item = self._run_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self._run_table.blockSignals(False)
        self._redraw()

    def _on_check_changed(self, item):
        if item.column() == 0:
            self._redraw()

    def _get_checked_run_ids(self) -> List[int]:
        ids = []
        for row in range(self._run_table.rowCount()):
            item = self._run_table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                ids.append(item.data(Qt.UserRole))
        return ids

    def _get_run_by_id(self, run_id: int) -> Optional[dict]:
        for r in self._runs:
            if r["id"] == run_id:
                return r
        return None

    # ── 데이터 파싱 (캐시) ───────────────────────────────────────────

    def _load_run_data(self, run: dict) -> Tuple:
        """(electro, calib) 로드 및 캐시.

        electro : (size_bp ndarray, rfu ndarray) or None
        calib   : [(ladder_size_bp, time_sec), ...] or None
        """
        run_id = run["id"]
        if run_id in self._cache:
            return self._cache[run_id]

        electro = None
        calib = None

        if run.get("electropherogram_path"):
            try:
                electro = extract_ladder_trace(run["electropherogram_path"])
            except Exception as e:
                logger.warning(f"Ladder trace failed (run {run_id}): {e}")

        if run.get("size_calibration_path"):
            try:
                rows = parse_size_calibration(run["size_calibration_path"])
                pts = [
                    (r["ladder_size_bp"], r["time_sec"])
                    for r in rows
                    if r["ladder_size_bp"] is not None and r["time_sec"] is not None
                ]
                calib = pts if pts else None
            except Exception as e:
                logger.warning(f"Calibration failed (run {run_id}): {e}")

        self._cache[run_id] = (electro, calib)
        return self._cache[run_id]

    # ── 차트 그리기 ──────────────────────────────────────────────────

    def _redraw(self):
        if not HAS_MPL:
            return

        ax1, ax2 = self._ax1, self._ax2
        ax1.clear()
        ax2.clear()
        ax1.set_facecolor("#FAFAFA")
        ax2.set_facecolor("#FAFAFA")

        plotted1 = plotted2 = 0

        for i, run_id in enumerate(self._get_checked_run_ids()):
            run = self._get_run_by_id(run_id)
            if not run:
                continue

            color = _RUN_COLORS[i % len(_RUN_COLORS)]
            display_dt = run["measured_at"] or run["created_at"]
            date_str = display_dt.strftime("%Y-%m-%d") if display_dt else "-"
            label = f"{date_str}  {run['step']}"

            electro, calib = self._load_run_data(run)

            # ① Ladder Electropherogram — convert bp → migration time using calibration
            if electro is not None:
                x_bp, rfu = electro  # x_bp is Size (bp) from the electropherogram CSV
                if calib is not None:
                    pts_sorted = sorted(calib, key=lambda p: p[0])  # sort by bp
                    c_bps   = np.array([p[0] for p in pts_sorted])
                    c_times = np.array([p[1] for p in pts_sorted])
                    x = np.interp(x_bp, c_bps, c_times)  # bp → migration time
                else:
                    x = x_bp
                mask = np.isfinite(x) & np.isfinite(rfu)
                if mask.any():
                    ax1.plot(
                        x[mask], rfu[mask],
                        linewidth=1.3, color=color, label=label, alpha=0.85,
                    )
                    plotted1 += 1

            # ② Size Calibration
            if calib is not None:
                sizes = [p[0] for p in calib]
                times = [p[1] for p in calib]
                ax2.plot(
                    sizes, times,
                    marker="o", linewidth=1.5, markersize=5,
                    color=color, label=label, alpha=0.85,
                )
                plotted2 += 1

        # ── ax1 스타일 ───────────────────────────────────────────────
        if plotted1:
            # Collect all calibration data from checked runs for tick labels
            all_calib = None
            for run_id in self._get_checked_run_ids():
                run = self._get_run_by_id(run_id)
                if run:
                    _, calib = self._load_run_data(run)
                    if calib:
                        all_calib = calib  # use first available calibration
                        break

            if all_calib:
                import matplotlib.ticker as mticker
                # Ticks at migration time positions, labeled with bp sizes
                pts = sorted(all_calib, key=lambda p: p[0])  # sort by bp
                c_bps   = [p[0] for p in pts]
                c_times = [p[1] for p in pts]

                ax1.xaxis.set_major_locator(mticker.FixedLocator(c_times))
                labels = [
                    f'{int(bp):,}' if bp >= 1000 else str(int(bp))
                    for bp in c_bps
                ]
                ax1.xaxis.set_major_formatter(mticker.FixedFormatter(labels))
                ax1.xaxis.set_minor_locator(mticker.FixedLocator([]))
                ax1.tick_params(axis='x', rotation=45, labelsize=7)
                for t in c_times:
                    ax1.axvline(t, color='gray', linewidth=0.4,
                                linestyle='--', alpha=0.3)

                # Convert xmax_bp → migration time via interp, then clip
                xmax_bp = self._xmax_combo.currentData()
                span = max(c_times) - min(c_times)
                margin = span * 0.02
                x_left = min(c_times) - margin
                if xmax_bp is not None:
                    xmax_time = float(np.interp(xmax_bp, c_bps, c_times))
                    ax1.set_xlim(left=x_left, right=xmax_time + margin)
                else:
                    ax1.set_xlim(left=x_left, right=max(c_times) + margin)
            else:
                # No calibration: fall back to raw time autoscale
                ax1.tick_params(axis='x', labelsize=7)

            ax1.set_xlabel("Size (bp)  [migration time axis, calibrated by ladder]", fontsize=8)
            ax1.set_ylabel("RFU", fontsize=8)
            ax1.set_title("① Ladder Electropherogram", fontsize=9, fontweight="bold")
            ax1.tick_params(axis='y', labelsize=7)
            ax1.spines[["top", "right"]].set_visible(False)
            ax1.grid(axis="y", alpha=0.25)
            ax1.legend(fontsize=7, loc="upper right", framealpha=0.8)
        else:
            ax1.text(
                0.5, 0.5,
                "선택된 런에 Electropherogram 파일 없음",
                ha="center", va="center",
                transform=ax1.transAxes, color="#9E9E9E", fontsize=9,
            )
            ax1.axis("off")

        # ── ax2 스타일 ───────────────────────────────────────────────
        if plotted2:
            ax2.set_xlabel("Ladder Size (bp)", fontsize=8)
            ax2.set_ylabel("Migration Time (sec)", fontsize=8)
            ax2.set_title("② Size Calibration Curves", fontsize=9, fontweight="bold")
            ax2.tick_params(labelsize=7)
            ax2.spines[["top", "right"]].set_visible(False)
            ax2.grid(alpha=0.25)
            ax2.legend(fontsize=7, loc="upper left", framealpha=0.8)
        else:
            ax2.text(
                0.5, 0.5,
                "선택된 런에 Size Calibration 파일 없음",
                ha="center", va="center",
                transform=ax2.transAxes, color="#9E9E9E", fontsize=9,
            )
            ax2.axis("off")

        try:
            self._fig.tight_layout(pad=0.8, h_pad=1.4)
        except Exception:
            pass
        self._canvas.draw()
