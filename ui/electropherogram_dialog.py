"""
Electropherogram Interactive Dialog
좌측 패널: 트레이스 토글(체크박스 + 범례 클릭) + X/Y 축 범위 컨트롤
우측: NavigationToolbar + matplotlib 캔버스

설정 영속성: QSettings("NGS-LIMS", "ElectropherogramDialog")
  - 창 geometry, 스플리터 위치, X/Y 범위 컨트롤 상태를 저장·복원
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.colors import to_hex
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

logger = logging.getLogger(__name__)

_SETTINGS_ORG  = "NGS-LIMS"
_SETTINGS_APP  = "ElectropherogramDialog"

_XMAX_PRESETS = [
    ("50 kbp",  50_000),
    ("100 kbp", 100_000),
    ("200 kbp", 200_000),
    ("500 kbp", 500_000),
    ("All",     None),
    ("Custom",  "custom"),
]
_XMAX_ALL_INDEX    = 4
_XMAX_CUSTOM_INDEX = 5
_LEFT_PANEL_DEFAULT_WIDTH = 185


class ElectropherogramDialog(QDialog):
    """Electropherogram overlay 뷰어.

    좌측 사이드패널에서 트레이스 가시성 토글 및 X/Y 축 범위를 조절한다.
    범례 라인 클릭으로도 토글 가능하며 체크박스와 양방향 동기화된다.

    - 창 최대화 가능 (Qt.Window 플래그)
    - QSplitter로 좌우 패널 폭 드래그 조절
    - QSettings로 창 크기·스플리터·범위 설정 자동 저장/복원

    Parameters
    ----------
    title       : 다이얼로그 창 제목
    fig         : plot_electropherogram_overlay()가 반환한 Figure
    ax          : 해당 Axes
    lines_dict  : {label: Line2D} — 플롯된 트레이스 매핑
    cal_bps     : 눈금 bp 배열 (없으면 None)
    cal_times   : 눈금 migration-time 배열 (없으면 None)
    """

    def __init__(
        self,
        title: str,
        fig,
        ax,
        lines_dict: Dict,
        cal_bps: Optional[np.ndarray],
        cal_times: Optional[np.ndarray],
        parent=None,
    ):
        super().__init__(parent)
        # 최대화·최소화 버튼을 포함한 일반 창으로 설정
        self.setWindowFlags(Qt.Window)

        self._fig = fig
        self._ax = ax
        self._lines = lines_dict       # {label: Line2D}
        self._cal_bps = cal_bps        # sorted ndarray or None
        self._cal_times = cal_times    # sorted ndarray or None
        self._initial_xlim = ax.get_xlim()
        self._initial_ylim = ax.get_ylim()
        self._checkboxes: Dict[str, QCheckBox] = {}
        self._legend_to_label: Dict = {}   # legend handle → label string

        self.setWindowTitle(title)
        self.setMinimumSize(900, 550)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self._build_left_panel())
        self._splitter.addWidget(self._build_right_panel())
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([_LEFT_PANEL_DEFAULT_WIDTH, 900])

        root.addWidget(self._splitter)

        self._setup_legend_pick()
        self._load_settings()   # 저장된 설정 복원 (창 크기, 스플리터, 범위)

    # ------------------------------------------------------------------ #
    #  Coordinate helpers                                                  #
    # ------------------------------------------------------------------ #

    def _bp_to_time(self, bp_val: float) -> float:
        if self._cal_bps is None or self._cal_times is None:
            return float(bp_val)
        bps = self._cal_bps
        times = self._cal_times
        t = float(np.interp(bp_val, bps, times))
        if bp_val > bps[-1] and len(bps) >= 2:
            slope = (times[-1] - times[-2]) / (bps[-1] - bps[-2])
            t = float(times[-1] + slope * (bp_val - bps[-1]))
        return t

    def _time_to_bp(self, time_val: float) -> float:
        if self._cal_bps is None or self._cal_times is None:
            return float(time_val)
        return float(np.interp(time_val, self._cal_times, self._cal_bps))

    # ------------------------------------------------------------------ #
    #  UI builders                                                         #
    # ------------------------------------------------------------------ #

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(140)   # 드래그 최소 폭; setFixedWidth 제거
        layout = QVBoxLayout(panel)
        layout.setSpacing(5)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Traces ──────────────────────────────────────────────────────
        hdr_traces = QLabel("Traces")
        hdr_traces.setStyleSheet("font-weight: bold;")
        layout.addWidget(hdr_traces)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(220)

        trace_widget = QWidget()
        trace_layout = QVBoxLayout(trace_widget)
        trace_layout.setSpacing(2)
        trace_layout.setContentsMargins(2, 2, 2, 2)

        for label, line in self._lines.items():
            cb = QCheckBox()
            cb.setChecked(True)
            try:
                hex_color = to_hex(line.get_color())
                px = QPixmap(12, 12)
                px.fill(QColor(hex_color))
                cb.setIcon(QIcon(px))
            except Exception:
                pass
            display = label if len(label) <= 24 else label[:21] + "…"
            cb.setText(display)
            cb.setToolTip(label)
            cb.toggled.connect(lambda checked, lbl=label: self._on_checkbox_changed(lbl, checked))
            self._checkboxes[label] = cb
            trace_layout.addWidget(cb)

        trace_layout.addStretch()
        scroll.setWidget(trace_widget)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        all_btn = QPushButton("All")
        all_btn.setMaximumHeight(22)
        all_btn.clicked.connect(self._select_all)
        none_btn = QPushButton("None")
        none_btn.setMaximumHeight(22)
        none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        layout.addLayout(btn_row)

        layout.addWidget(self._make_separator())

        # ── X range ─────────────────────────────────────────────────────
        hdr_x = QLabel("X range")
        hdr_x.setStyleSheet("font-weight: bold;")
        layout.addWidget(hdr_x)

        xmin_row = QHBoxLayout()
        xmin_row.addWidget(QLabel("Min"))
        self._xmin_spin = QSpinBox()
        self._xmin_spin.setRange(0, 500_000)
        self._xmin_spin.setSingleStep(500)
        self._xmin_spin.setSuffix(" bp")
        self._xmin_spin.setValue(max(0, int(self._time_to_bp(self._initial_xlim[0]))))
        self._xmin_spin.valueChanged.connect(self._apply_xlim)
        xmin_row.addWidget(self._xmin_spin)
        layout.addLayout(xmin_row)

        xmax_row = QHBoxLayout()
        xmax_row.addWidget(QLabel("Max"))
        self._xmax_combo = QComboBox()
        for label_txt, bp_val in _XMAX_PRESETS:
            self._xmax_combo.addItem(label_txt, bp_val)
        self._xmax_combo.setCurrentIndex(_XMAX_ALL_INDEX)
        self._xmax_combo.currentIndexChanged.connect(self._on_xmax_combo_changed)
        xmax_row.addWidget(self._xmax_combo)
        layout.addLayout(xmax_row)

        self._xmax_custom_spin = QSpinBox()
        self._xmax_custom_spin.setRange(1_000, 1_000_000)
        self._xmax_custom_spin.setSingleStep(1_000)
        self._xmax_custom_spin.setSuffix(" bp")
        self._xmax_custom_spin.setValue(200_000)
        self._xmax_custom_spin.setVisible(False)
        self._xmax_custom_spin.valueChanged.connect(self._apply_xlim)
        layout.addWidget(self._xmax_custom_spin)

        layout.addWidget(self._make_separator())

        # ── Y range ─────────────────────────────────────────────────────
        hdr_y = QLabel("Y range")
        hdr_y.setStyleSheet("font-weight: bold;")
        layout.addWidget(hdr_y)

        self._yauto_cb = QCheckBox("Auto Y")
        self._yauto_cb.setChecked(True)
        self._yauto_cb.toggled.connect(self._on_yauto_changed)
        layout.addWidget(self._yauto_cb)

        self._y_controls = QWidget()
        y_ctrl_layout = QVBoxLayout(self._y_controls)
        y_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        y_ctrl_layout.setSpacing(2)

        ymin_row = QHBoxLayout()
        ymin_row.addWidget(QLabel("Min"))
        self._ymin_spin = QDoubleSpinBox()
        self._ymin_spin.setRange(-1_000_000, 1_000_000)
        self._ymin_spin.setSingleStep(500)
        self._ymin_spin.setDecimals(0)
        self._ymin_spin.setSuffix(" RFU")
        self._ymin_spin.setValue(max(0.0, self._initial_ylim[0]))
        self._ymin_spin.valueChanged.connect(self._apply_ylim)
        ymin_row.addWidget(self._ymin_spin)
        y_ctrl_layout.addLayout(ymin_row)

        ymax_row = QHBoxLayout()
        ymax_row.addWidget(QLabel("Max"))
        self._ymax_spin = QDoubleSpinBox()
        self._ymax_spin.setRange(1, 10_000_000)
        self._ymax_spin.setSingleStep(500)
        self._ymax_spin.setDecimals(0)
        self._ymax_spin.setSuffix(" RFU")
        self._ymax_spin.setValue(max(100.0, self._initial_ylim[1]))
        self._ymax_spin.valueChanged.connect(self._apply_ylim)
        ymax_row.addWidget(self._ymax_spin)
        y_ctrl_layout.addLayout(ymax_row)

        layout.addWidget(self._y_controls)
        self._y_controls.setVisible(False)

        layout.addStretch()

        reset_btn = QPushButton("Reset View")
        reset_btn.clicked.connect(self._reset_view)
        layout.addWidget(reset_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        return panel

    def _build_right_panel(self) -> QWidget:
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._canvas = FigureCanvas(self._fig)
        toolbar = NavigationToolbar(self._canvas, self)
        layout.addWidget(toolbar)
        layout.addWidget(self._canvas)

        return right

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #bbb;")
        return sep

    # ------------------------------------------------------------------ #
    #  Settings persistence                                                #
    # ------------------------------------------------------------------ #

    def _load_settings(self):
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        geom = s.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.resize(1200, 720)

        splitter_state = s.value("splitter")
        if splitter_state:
            self._splitter.restoreState(splitter_state)

        # X range
        xmin = s.value("xmin", type=int)
        if xmin is not None:
            self._xmin_spin.blockSignals(True)
            self._xmin_spin.setValue(xmin)
            self._xmin_spin.blockSignals(False)

        xmax_idx = s.value("xmax_idx", type=int)
        if xmax_idx is not None and 0 <= xmax_idx < self._xmax_combo.count():
            self._xmax_combo.blockSignals(True)
            self._xmax_combo.setCurrentIndex(xmax_idx)
            self._xmax_combo.blockSignals(False)
            self._xmax_custom_spin.setVisible(self._xmax_combo.currentData() == "custom")

        xmax_custom = s.value("xmax_custom", type=int)
        if xmax_custom is not None:
            self._xmax_custom_spin.blockSignals(True)
            self._xmax_custom_spin.setValue(xmax_custom)
            self._xmax_custom_spin.blockSignals(False)

        # Y range
        yauto = s.value("yauto", type=bool)
        if yauto is not None:
            self._yauto_cb.blockSignals(True)
            self._yauto_cb.setChecked(yauto)
            self._yauto_cb.blockSignals(False)
            self._y_controls.setVisible(not yauto)

        ymin = s.value("ymin", type=float)
        if ymin is not None:
            self._ymin_spin.blockSignals(True)
            self._ymin_spin.setValue(ymin)
            self._ymin_spin.blockSignals(False)

        ymax = s.value("ymax", type=float)
        if ymax is not None:
            self._ymax_spin.blockSignals(True)
            self._ymax_spin.setValue(ymax)
            self._ymax_spin.blockSignals(False)

        # 복원된 설정을 axes에 즉시 적용
        self._apply_xlim()
        if not self._yauto_cb.isChecked():
            self._apply_ylim()

    def _save_settings(self):
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue("geometry",     self.saveGeometry())
        s.setValue("splitter",     self._splitter.saveState())
        s.setValue("xmin",         self._xmin_spin.value())
        s.setValue("xmax_idx",     self._xmax_combo.currentIndex())
        s.setValue("xmax_custom",  self._xmax_custom_spin.value())
        s.setValue("yauto",        self._yauto_cb.isChecked())
        s.setValue("ymin",         self._ymin_spin.value())
        s.setValue("ymax",         self._ymax_spin.value())

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    #  Legend pick setup                                                   #
    # ------------------------------------------------------------------ #

    def _setup_legend_pick(self):
        leg = self._ax.get_legend()
        if leg is None:
            return
        labels = list(self._lines.keys())
        for i, leg_line in enumerate(leg.get_lines()):
            if i < len(labels):
                leg_line.set_picker(5)
                self._legend_to_label[leg_line] = labels[i]
        self._canvas.mpl_connect('pick_event', self._on_pick)

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #

    def _on_pick(self, event):
        label = self._legend_to_label.get(event.artist)
        if label is None:
            return
        cb = self._checkboxes.get(label)
        if cb:
            cb.setChecked(not cb.isChecked())

    def _on_checkbox_changed(self, label: str, checked: bool):
        line = self._lines.get(label)
        if line:
            line.set_visible(checked)
        leg = self._ax.get_legend()
        if leg:
            for leg_line, lbl in self._legend_to_label.items():
                if lbl == label:
                    leg_line.set_alpha(1.0 if checked else 0.2)
                    break
        self._canvas.draw_idle()

    def _select_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(True)

    def _select_none(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    def _on_xmax_combo_changed(self):
        self._xmax_custom_spin.setVisible(self._xmax_combo.currentData() == "custom")
        self._apply_xlim()

    def _get_xmax_time(self) -> float:
        data = self._xmax_combo.currentData()
        if data is None:
            return self._initial_xlim[1]
        if data == "custom":
            return self._bp_to_time(self._xmax_custom_spin.value())
        return self._bp_to_time(data)

    def _apply_xlim(self):
        xmin_time = self._bp_to_time(self._xmin_spin.value())
        xmax_time = self._get_xmax_time()
        if xmax_time > xmin_time:
            self._ax.set_xlim(xmin_time, xmax_time)
            self._canvas.draw_idle()

    def _on_yauto_changed(self, checked: bool):
        self._y_controls.setVisible(not checked)
        if checked:
            self._ax.autoscale(axis='y')
            self._ax.set_ylim(auto=True)
            self._canvas.draw_idle()
        else:
            self._apply_ylim()

    def _apply_ylim(self):
        ymin = self._ymin_spin.value()
        ymax = self._ymax_spin.value()
        if ymax > ymin:
            self._ax.set_ylim(ymin, ymax)
            self._canvas.draw_idle()

    def _reset_view(self):
        self._ax.set_xlim(*self._initial_xlim)
        self._ax.set_ylim(*self._initial_ylim)

        self._xmax_combo.blockSignals(True)
        self._xmax_combo.setCurrentIndex(_XMAX_ALL_INDEX)
        self._xmax_combo.blockSignals(False)
        self._xmax_custom_spin.setVisible(False)

        self._xmin_spin.blockSignals(True)
        self._xmin_spin.setValue(max(0, int(self._time_to_bp(self._initial_xlim[0]))))
        self._xmin_spin.blockSignals(False)

        self._yauto_cb.setChecked(True)

        for cb in self._checkboxes.values():
            cb.setChecked(True)

        self._canvas.draw_idle()
