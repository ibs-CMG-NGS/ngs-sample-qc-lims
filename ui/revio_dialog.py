"""
Revio Run Designer — PacBio Revio 런 설계 다이얼로그
"""
import datetime
import json
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox,
    QComboBox, QPushButton, QSplitter, QWidget, QFileDialog,
    QMessageBox, QGridLayout, QSizePolicy, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from database import db_manager, get_all_samples, get_all_projects
from database.models import QCMetric
from parsers.revio_csv import generate_run_csv, bc_for_well, ROWS, COLS, SMRT_WELLS

logger = logging.getLogger(__name__)

# 4개 SMRT Cell 별 강조 색상 (파랑/초록/주황/보라)
_CELL_FG = ["#1565C0", "#2E7D32", "#BF360C", "#4A148C"]
_CELL_BG = ["#BBDEFB", "#C8E6C9", "#FFE0B2", "#E1BEE7"]

APPLICATIONS = ["Other WGS", "Other", "HiFi WGS", "Iso-Seq"]


# ── Adapter Plate Widget ─────────────────────────────────────────────

class _AdapterPlateWidget(QWidget):
    """SMRTbell Adapter Index Plate 96A — 8×12 클릭 가능 그리드."""

    well_clicked = pyqtSignal(str)  # well_id: 'A01', 'D08' 등

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}   # well_id → button
        self._assignment: dict[str, int] = {}         # well_id → smrt row_idx
        self._build()

    def _build(self):
        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)

        tiny = QFont()
        tiny.setPointSize(7)

        # 열 헤더 (01~12)
        for j, col in enumerate(COLS):
            lbl = QLabel(str(int(col)))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(tiny)
            layout.addWidget(lbl, 0, j + 1)

        # 행 헤더 + 버튼
        for i, row in enumerate(ROWS):
            row_lbl = QLabel(row)
            row_lbl.setAlignment(Qt.AlignCenter)
            row_lbl.setFont(tiny)
            layout.addWidget(row_lbl, i + 1, 0)

            for j, col in enumerate(COLS):
                well_id = f"{row}{col}"
                btn = QPushButton(well_id)
                btn.setFixedSize(34, 20)
                btn.setFont(tiny)
                btn.setToolTip(bc_for_well(well_id))
                btn.clicked.connect(lambda _checked, w=well_id: self.well_clicked.emit(w))
                self._buttons[well_id] = btn
                layout.addWidget(btn, i + 1, j + 1)

    # ── 공개 API ──────────────────────────────────────────────────────

    def set_assignment(self, well_id: str, row_idx: Optional[int]):
        """row_idx=None → 배정 해제, 0~3 → 해당 SMRT Cell 색상."""
        btn = self._buttons.get(well_id)
        if btn is None:
            return
        if row_idx is None:
            self._assignment.pop(well_id, None)
            btn.setStyleSheet("")
            btn.setToolTip(bc_for_well(well_id))
        else:
            self._assignment[well_id] = row_idx
            fg = _CELL_FG[row_idx]
            bg = _CELL_BG[row_idx]
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {fg}; "
                f"border: 1px solid {fg}; font-weight: bold; }}"
            )
            btn.setToolTip(f"{bc_for_well(well_id)}  ← {SMRT_WELLS[row_idx]}")

    def get_well_for_row(self, row_idx: int) -> Optional[str]:
        """해당 SMRT Cell 행에 배정된 well_id 반환."""
        for w, r in self._assignment.items():
            if r == row_idx:
                return w
        return None

    def get_row_for_well(self, well_id: str) -> Optional[int]:
        """해당 well에 배정된 SMRT Cell 행 번호 반환."""
        return self._assignment.get(well_id)

    def clear_row(self, row_idx: int):
        """특정 SMRT Cell 배정 해제."""
        wells = [w for w, r in list(self._assignment.items()) if r == row_idx]
        for w in wells:
            self.set_assignment(w, None)


# ── Main Dialog ──────────────────────────────────────────────────────

class RevioRunDesignerDialog(QDialog):
    """Revio Run Designer 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revio Run Designer")
        self.setMinimumSize(1050, 600)
        self.resize(1200, 680)

        self._active_row: int = 0
        self._all_samples: list = []  # [(sample_id, display, project), ...]

        # 각 SMRT Cell 행의 위젯 레퍼런스 (인덱스 = 행 번호)
        self._sample_combos:    list[QComboBox]       = []
        self._well_name_edits:  list[QLineEdit]       = []
        self._movie_time_spins: list[QDoubleSpinBox]  = []
        self._insert_size_spins:list[QSpinBox]        = []
        self._conc_spins:       list[QSpinBox]        = []
        self._kinetics_checks:  list[QCheckBox]       = []
        self._app_combos:       list[QComboBox]       = []
        self._adapter_labels:   list[QLabel]          = []
        self._smrt_labels:      list[QLabel]          = []   # SMRT Cell 라벨 (하이라이트용)
        self._row_bg_widgets:   list[list]            = []   # 배경색 적용 위젯 묶음

        self._build_ui()
        self._load_samples()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # ── 좌: Run Settings + SMRT Cell 테이블 ─────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(self._build_run_settings_group())
        left_layout.addWidget(self._build_smrt_table_group(), stretch=1)
        splitter.addWidget(left)

        # ── 우: 어댑터 플레이트 ─────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(4)
        right_layout.setContentsMargins(4, 0, 0, 0)

        plate_title = QLabel("Adapter Index Plate 96A")
        bold = QFont()
        bold.setBold(True)
        plate_title.setFont(bold)
        right_layout.addWidget(plate_title)

        hint = QLabel("SMRT Cell 행 선택 후 well을 클릭해 어댑터를 배정하세요.")
        hint.setStyleSheet("color: #666; font-style: italic;")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        self._plate_widget = _AdapterPlateWidget()
        self._plate_widget.well_clicked.connect(self._on_well_clicked)
        right_layout.addWidget(self._plate_widget)
        right_layout.addWidget(self._build_legend())
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # ── 하단 버튼 바 ─────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        btn_bar.addWidget(QLabel("Project:"))

        self._project_combo = QComboBox()
        self._project_combo.setMinimumWidth(180)
        self._project_combo.currentIndexChanged.connect(self._on_project_filter_changed)
        btn_bar.addWidget(self._project_combo)
        btn_bar.addStretch()

        btn_save = QPushButton("Save Design…")
        btn_save.setToolTip("런 설계를 JSON 파일로 저장")
        btn_save.clicked.connect(self._save_design)
        btn_bar.addWidget(btn_save)

        btn_load = QPushButton("Load Design…")
        btn_load.setToolTip("저장된 런 설계 JSON 파일 불러오기")
        btn_load.clicked.connect(self._load_design)
        btn_bar.addWidget(btn_load)

        btn_export = QPushButton("Export CSV…")
        btn_export.setDefault(True)
        btn_export.clicked.connect(self._on_export)
        btn_bar.addWidget(btn_export)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_bar.addWidget(btn_close)

        root.addLayout(btn_bar)

    def _build_run_settings_group(self) -> QGroupBox:
        group = QGroupBox("Run Settings")
        form = QFormLayout(group)
        form.setSpacing(3)
        form.setContentsMargins(8, 6, 8, 6)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        default_name = f"Run {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self._run_name    = QLineEdit(default_name)
        self._run_comments= QLineEdit()
        self._transfer_dir= QLineEdit()

        form.addRow("Run Name *:",    self._run_name)
        form.addRow("Comments:",      self._run_comments)
        form.addRow("Plate 1 *:",     self._build_plate_fields(1))
        form.addRow("Plate 2:",       self._build_plate_fields(2))
        form.addRow("Transfer Dir:",  self._transfer_dir)
        return group

    def _build_plate_fields(self, plate_num: int) -> QWidget:
        """REF / LOT / SN / Exp 4개 서브필드를 가진 플레이트 바코드 입력 위젯."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        _tip = (
            "플레이트 박스 라벨 예) REF 103-496-700  LOT 039423  SN 00113  Exp 2026-01-22\n"
            "조합 순서: REF(dashes 제거) + LOT + SN + Exp(YYYYMMDD)\n"
            "결과 예) 1034967000394230011320260122"
        )

        def _field(label, placeholder, width):
            h.addWidget(QLabel(label))
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setFixedWidth(width)
            edit.setToolTip(_tip)
            h.addWidget(edit)
            return edit

        ref  = _field("REF", "103-496-700", 90)
        lot  = _field("LOT", "039423",      70)
        sn   = _field("SN",  "00113",       60)
        exp  = _field("Exp", "2026-01-22",  80)
        h.addStretch()

        if plate_num == 1:
            self._p1_ref, self._p1_lot, self._p1_sn, self._p1_exp = ref, lot, sn, exp
        else:
            self._p2_ref, self._p2_lot, self._p2_sn, self._p2_exp = ref, lot, sn, exp
        return w

    def _build_smrt_table_group(self) -> QGroupBox:
        group = QGroupBox("SMRT Cell Assignment")
        outer = QVBoxLayout(group)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)

        # ── 헤더 행 (고정 높이 위젯) ─────────────────────────────────
        hdr_widget = QWidget()
        hdr_widget.setFixedHeight(24)
        hdr_widget.setStyleSheet(
            "background-color: #ECEFF1; border-bottom: 2px solid #B0BEC5;"
        )
        grid_hdr = QGridLayout(hdr_widget)
        grid_hdr.setContentsMargins(6, 0, 6, 0)
        grid_hdr.setHorizontalSpacing(6)
        grid_hdr.setVerticalSpacing(0)

        headers = ["SMRT Cell", "Sample", "Well Name",
                   "Movie (h)", "Insert (bp)", "Conc (pM)", "Kinetics", "Application", "Adapter"]
        hdr_font = QFont(); hdr_font.setBold(True); hdr_font.setPointSize(8)
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFont(hdr_font)
            lbl.setStyleSheet("color: #37474F; background: transparent;")
            grid_hdr.addWidget(lbl, 0, col)

        grid_hdr.setColumnStretch(1, 1)
        grid_hdr.setColumnMinimumWidth(0, 58)
        grid_hdr.setColumnMinimumWidth(2, 100)
        grid_hdr.setColumnMinimumWidth(3, 58)
        grid_hdr.setColumnMinimumWidth(4, 76)
        grid_hdr.setColumnMinimumWidth(5, 76)
        grid_hdr.setColumnMinimumWidth(6, 52)
        grid_hdr.setColumnMinimumWidth(7, 108)
        grid_hdr.setColumnMinimumWidth(8, 66)
        outer.addWidget(hdr_widget)

        # ── 데이터 행들 (별도 grid, 헤더와 컬럼 너비 공유) ───────────
        data_widget = QWidget()
        self._smrt_grid = QGridLayout(data_widget)
        self._smrt_grid.setContentsMargins(6, 4, 6, 4)
        self._smrt_grid.setHorizontalSpacing(6)
        self._smrt_grid.setVerticalSpacing(4)
        self._smrt_grid.setColumnStretch(1, 1)
        self._smrt_grid.setColumnMinimumWidth(0, 58)
        self._smrt_grid.setColumnMinimumWidth(2, 100)
        self._smrt_grid.setColumnMinimumWidth(3, 58)
        self._smrt_grid.setColumnMinimumWidth(4, 76)
        self._smrt_grid.setColumnMinimumWidth(5, 76)
        self._smrt_grid.setColumnMinimumWidth(6, 52)
        self._smrt_grid.setColumnMinimumWidth(7, 108)
        self._smrt_grid.setColumnMinimumWidth(8, 66)

        for i, smrt_well in enumerate(SMRT_WELLS):
            self._add_smrt_row(self._smrt_grid, i, i, smrt_well)

        # 빈 공간을 아래로 밀어내기
        self._smrt_grid.setRowStretch(len(SMRT_WELLS), 1)
        outer.addWidget(data_widget, stretch=1)

        self._highlight_active_row(0)
        return group

    def _add_smrt_row(self, grid: QGridLayout, grid_row: int, row_idx: int, smrt_well: str):
        bold = QFont(); bold.setBold(True)

        # ── SMRT Cell 라벨 (클릭 → 행 활성화) ──
        smrt_lbl = QLabel(smrt_well)
        smrt_lbl.setAlignment(Qt.AlignCenter)
        smrt_lbl.setFont(bold)
        smrt_lbl.setCursor(Qt.PointingHandCursor)
        smrt_lbl.setFixedHeight(32)
        smrt_lbl.mousePressEvent = lambda _e, r=row_idx: self._set_active_row(r)
        self._smrt_labels.append(smrt_lbl)
        grid.addWidget(smrt_lbl, grid_row, 0)

        # ── Sample combo ──
        sample_combo = QComboBox()
        sample_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sample_combo.addItem("", "")
        sample_combo.currentIndexChanged.connect(
            lambda _idx, r=row_idx: self._on_sample_changed(r)
        )
        self._sample_combos.append(sample_combo)
        grid.addWidget(sample_combo, grid_row, 1)

        # ── Well Name ──
        well_edit = QLineEdit()
        well_edit.setPlaceholderText("auto")
        self._well_name_edits.append(well_edit)
        grid.addWidget(well_edit, grid_row, 2)

        # ── Movie time ──
        movie_spin = QDoubleSpinBox()
        movie_spin.setRange(1, 48)
        movie_spin.setValue(30)
        movie_spin.setDecimals(0)
        self._movie_time_spins.append(movie_spin)
        grid.addWidget(movie_spin, grid_row, 3)

        # ── Insert size ──
        insert_spin = QSpinBox()
        insert_spin.setRange(1000, 200000)
        insert_spin.setValue(15000)
        insert_spin.setSingleStep(500)
        self._insert_size_spins.append(insert_spin)
        grid.addWidget(insert_spin, grid_row, 4)

        # ── Concentration (pM, 사용자 설정값) ──
        conc_spin = QSpinBox()
        conc_spin.setRange(50, 2000)
        conc_spin.setValue(300)
        conc_spin.setSingleStep(50)
        self._conc_spins.append(conc_spin)
        grid.addWidget(conc_spin, grid_row, 5)

        # ── Kinetics ──
        kinetics_cb = QCheckBox()
        kinetics_cb.setChecked(True)
        self._kinetics_checks.append(kinetics_cb)
        grid.addWidget(kinetics_cb, grid_row, 6, Qt.AlignCenter)

        # ── Application ──
        app_combo = QComboBox()
        app_combo.addItems(APPLICATIONS)
        self._app_combos.append(app_combo)
        grid.addWidget(app_combo, grid_row, 7)

        # ── Adapter label ──
        adapter_lbl = QLabel("—")
        adapter_lbl.setAlignment(Qt.AlignCenter)
        adapter_lbl.setFont(bold)
        self._adapter_labels.append(adapter_lbl)
        grid.addWidget(adapter_lbl, grid_row, 8)

        # 배경 하이라이트 대상 (adapter_lbl 제외 — 자체 색상 관리)
        self._row_bg_widgets.append([
            smrt_lbl, sample_combo, well_edit,
            movie_spin, insert_spin, conc_spin,
            kinetics_cb, app_combo,
        ])

    def _build_legend(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 4, 0, 0)
        tiny = QFont(); tiny.setPointSize(8)
        for i, well in enumerate(SMRT_WELLS):
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {_CELL_FG[i]};")
            dot.setFont(tiny)
            lbl = QLabel(well)
            lbl.setFont(tiny)
            layout.addWidget(dot)
            layout.addWidget(lbl)
        layout.addStretch()
        return widget

    # ── 데이터 로드 ──────────────────────────────────────────────────

    def _load_samples(self):
        try:
            with db_manager.session_scope() as session:
                samples  = get_all_samples(session)
                projects = get_all_projects(session)
                self._all_samples = [
                    (s.sample_id, f"{s.sample_id}  {s.sample_name or ''}", s.project or "")
                    for s in samples
                ]
                proj_names = [p.project_name for p in projects]
        except Exception as e:
            logger.error(f"RevioDesigner: failed to load samples: {e}")
            self._all_samples = []
            proj_names = []

        self._project_combo.blockSignals(True)
        self._project_combo.clear()
        self._project_combo.addItem("All Projects", "")
        for pname in proj_names:
            self._project_combo.addItem(pname, pname)
        self._project_combo.blockSignals(False)

        self._populate_sample_combos("")

    def _populate_sample_combos(self, project_filter: str):
        filtered = [
            (sid, disp)
            for sid, disp, proj in self._all_samples
            if not project_filter or proj == project_filter
        ]
        for combo in self._sample_combos:
            prev = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("", "")
            for sid, disp in filtered:
                combo.addItem(disp, sid)
            if prev:
                idx = combo.findData(prev)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    # ── 이벤트 핸들러 ────────────────────────────────────────────────

    def _set_active_row(self, row_idx: int):
        self._active_row = row_idx
        self._highlight_active_row(row_idx)

    def _highlight_active_row(self, active: int):
        for i, widgets in enumerate(self._row_bg_widgets):
            if i == active:
                bg  = _CELL_BG[i]
                fg  = _CELL_FG[i]
                # SMRT 라벨: 컬러 배지 스타일
                self._smrt_labels[i].setStyleSheet(
                    f"background-color: {fg}; color: white; border-radius: 6px; "
                    f"font-weight: bold; padding: 4px;"
                )
                # 나머지 셀: 연한 배경
                for w in widgets[1:]:
                    w.setStyleSheet(f"background-color: {bg};")
            else:
                self._smrt_labels[i].setStyleSheet(
                    "font-weight: bold; color: #333;"
                )
                for w in widgets[1:]:
                    w.setStyleSheet("")

    def _on_project_filter_changed(self):
        self._populate_sample_combos(self._project_combo.currentData() or "")

    def _on_sample_changed(self, row_idx: int):
        sample_id = self._sample_combos[row_idx].currentData() or ""

        # Well Name 자동 채움
        self._well_name_edits[row_idx].setText(sample_id)

        if not sample_id:
            return

        try:
            with db_manager.session_scope() as session:
                # ── Insert Size: Library Prep + Femto Pulse avg_size ──
                fp_metric = (
                    session.query(QCMetric)
                    .filter(
                        QCMetric.sample_id == sample_id,
                        QCMetric.step == "Library Prep",
                        QCMetric.instrument == "Femto Pulse",
                    )
                    .order_by(QCMetric.measured_at.desc())
                    .first()
                )
                if fp_metric and fp_metric.avg_size:
                    self._insert_size_spins[row_idx].setValue(int(fp_metric.avg_size))

                # ── Adapter Index: Library Prep (어느 instrument든) ──
                lib_metric = (
                    session.query(QCMetric)
                    .filter(
                        QCMetric.sample_id == sample_id,
                        QCMetric.step == "Library Prep",
                        QCMetric.index_no.isnot(None),
                    )
                    .order_by(QCMetric.measured_at.desc())
                    .first()
                )
                if lib_metric and lib_metric.index_no:
                    self._assign_adapter(row_idx, lib_metric.index_no.strip())


        except Exception as e:
            logger.warning(f"RevioDesigner: QC fetch failed for {sample_id}: {e}")

    def _assign_adapter(self, row_idx: int, well_id: str):
        """어댑터 플레이트 well → SMRT Cell 행에 배정 (내부 공통 로직)."""
        # well_id 유효성 체크 (예: 'A04', 'D08')
        if not well_id or len(well_id) < 3:
            return
        if well_id[0].upper() not in ROWS or not well_id[1:].isdigit():
            return
        col_num = int(well_id[1:])
        if col_num < 1 or col_num > 12:
            return

        # 기존 이 행의 well 배정 해제
        old_well = self._plate_widget.get_well_for_row(row_idx)
        if old_well:
            self._plate_widget.set_assignment(old_well, None)

        # 이미 다른 행에 배정된 well이면 그 행도 해제
        existing_row = self._plate_widget.get_row_for_well(well_id)
        if existing_row is not None and existing_row != row_idx:
            self._adapter_labels[existing_row].setText("—")
            self._adapter_labels[existing_row].setStyleSheet("")

        # 새 배정
        self._plate_widget.set_assignment(well_id, row_idx)
        bc = bc_for_well(well_id)
        self._adapter_labels[row_idx].setText(bc)
        self._adapter_labels[row_idx].setStyleSheet(
            f"color: {_CELL_FG[row_idx]}; font-weight: bold;"
        )

    def _on_well_clicked(self, well_id: str):
        """어댑터 플레이트 well 클릭 → active SMRT Cell 행에 배정."""
        self._assign_adapter(self._active_row, well_id)

    # ── Plate barcode 조합 ───────────────────────────────────────────

    def _get_plate_barcode(self, plate_num: int) -> str:
        """REF+LOT+SN+Exp 서브필드를 합쳐 Revio 바코드 문자열 반환.
        순서: REF(dashes 제거, 9자) + LOT(6자) + SN(5자) + Exp(YYYYMMDD, 8자)
        """
        if plate_num == 1:
            ref, lot, sn, exp = self._p1_ref, self._p1_lot, self._p1_sn, self._p1_exp
        else:
            ref, lot, sn, exp = self._p2_ref, self._p2_lot, self._p2_sn, self._p2_exp

        ref_val = ref.text().strip().replace("-", "")
        lot_val = lot.text().strip()
        sn_val  = sn.text().strip()
        exp_val = exp.text().strip().replace("-", "")  # YYYY-MM-DD → YYYYMMDD

        return ref_val + lot_val + sn_val + exp_val

    def _plate_to_dict(self, plate_num: int) -> dict:
        if plate_num == 1:
            ref, lot, sn, exp = self._p1_ref, self._p1_lot, self._p1_sn, self._p1_exp
        else:
            ref, lot, sn, exp = self._p2_ref, self._p2_lot, self._p2_sn, self._p2_exp
        return {
            "ref": ref.text().strip(),
            "lot": lot.text().strip(),
            "sn":  sn.text().strip(),
            "exp": exp.text().strip(),
        }

    def _dict_to_plate(self, plate_num: int, d: dict):
        if plate_num == 1:
            ref, lot, sn, exp = self._p1_ref, self._p1_lot, self._p1_sn, self._p1_exp
        else:
            ref, lot, sn, exp = self._p2_ref, self._p2_lot, self._p2_sn, self._p2_exp
        ref.setText(d.get("ref", ""))
        lot.setText(d.get("lot", ""))
        sn.setText(d.get("sn",  ""))
        exp.setText(d.get("exp", ""))

    # ── Save / Load Design ───────────────────────────────────────────

    def _collect_design(self) -> dict:
        """현재 다이얼로그 상태를 dict로 수집."""
        cells = []
        for i in range(len(SMRT_WELLS)):
            cells.append({
                "sample_id":     self._sample_combos[i].currentData() or "",
                "well_name":     self._well_name_edits[i].text(),
                "movie_time":    self._movie_time_spins[i].value(),
                "insert_size":   self._insert_size_spins[i].value(),
                "concentration": self._conc_spins[i].value(),
                "kinetics":      self._kinetics_checks[i].isChecked(),
                "application":   self._app_combos[i].currentText(),
                "adapter_well":  self._plate_widget.get_well_for_row(i) or "",
            })
        return {
            "run_name":     self._run_name.text(),
            "comments":     self._run_comments.text(),
            "plate1":       self._plate_to_dict(1),
            "plate2":       self._plate_to_dict(2),
            "transfer_dir": self._transfer_dir.text(),
            "project":      self._project_combo.currentData() or "",
            "smrt_cells":   cells,
        }

    def _apply_design(self, design: dict):
        """dict를 읽어 다이얼로그 필드를 채움."""
        self._run_name.setText(design.get("run_name", ""))
        self._run_comments.setText(design.get("comments", ""))
        self._dict_to_plate(1, design.get("plate1", {}))
        self._dict_to_plate(2, design.get("plate2", {}))
        self._transfer_dir.setText(design.get("transfer_dir", ""))

        # Project filter 복원
        proj = design.get("project", "")
        if proj:
            idx = self._project_combo.findData(proj)
            if idx >= 0:
                self._project_combo.setCurrentIndex(idx)

        for i, cell in enumerate(design.get("smrt_cells", [])):
            if i >= len(SMRT_WELLS):
                break
            # Sample 선택 복원 (blockSignals로 중간 이벤트 억제)
            combo = self._sample_combos[i]
            combo.blockSignals(True)
            sid = cell.get("sample_id", "")
            idx = combo.findData(sid) if sid else 0
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

            self._well_name_edits[i].setText(cell.get("well_name", ""))
            self._movie_time_spins[i].setValue(cell.get("movie_time", 30))
            self._insert_size_spins[i].setValue(cell.get("insert_size", 15000))
            self._conc_spins[i].setValue(cell.get("concentration", 300))
            self._kinetics_checks[i].setChecked(cell.get("kinetics", True))
            app_idx = self._app_combos[i].findText(cell.get("application", ""))
            if app_idx >= 0:
                self._app_combos[i].setCurrentIndex(app_idx)

            # 어댑터 복원
            aw = cell.get("adapter_well", "")
            if aw:
                self._assign_adapter(i, aw)
            else:
                old = self._plate_widget.get_well_for_row(i)
                if old:
                    self._plate_widget.set_assignment(old, None)
                self._adapter_labels[i].setText("—")
                self._adapter_labels[i].setStyleSheet("")

    def _save_design(self):
        default_name = (
            self._run_name.text().strip().replace(":", "-").replace(" ", "_")
            or "revio_design"
        ) + ".json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Run Design", default_name, "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._collect_design(), f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Save Design", f"저장 완료:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"저장 실패:\n{e}")

    def _load_design(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Run Design", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                design = json.load(f)
            self._apply_design(design)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"불러오기 실패:\n{e}")

    # ── Export ───────────────────────────────────────────────────────

    def _on_export(self):
        # 활성 행 수집 (샘플이 선택된 행만)
        active_cells = []
        missing_adapter = []

        for i, smrt_well in enumerate(SMRT_WELLS):
            sample_id = self._sample_combos[i].currentData() or ""
            if not sample_id:
                continue  # 이 SMRT Cell 미사용

            well_name  = self._well_name_edits[i].text().strip() or sample_id
            adapter_bc = self._adapter_labels[i].text()
            if adapter_bc == "—":
                adapter_bc = ""
                missing_adapter.append(smrt_well)

            active_cells.append({
                "smrt_cell":    smrt_well,
                "well_name":    well_name,
                "movie_time":   int(self._movie_time_spins[i].value()),
                "insert_size":  self._insert_size_spins[i].value(),
                "concentration":self._conc_spins[i].value(),
                "kinetics":     self._kinetics_checks[i].isChecked(),
                "application":  self._app_combos[i].currentText(),
                "adapter_bc":   adapter_bc,
            })

        if not active_cells:
            QMessageBox.warning(self, "Export", "샘플이 하나 이상 지정되어야 합니다.")
            return

        if missing_adapter:
            reply = QMessageBox.question(
                self, "Export",
                f"다음 SMRT Cell에 어댑터가 지정되지 않았습니다:\n"
                f"{', '.join(missing_adapter)}\n\n계속 진행하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        run_name = self._run_name.text().strip()
        if not run_name:
            QMessageBox.warning(self, "Export", "Run Name을 입력하세요.")
            return

        run_settings = {
            "run_name":     run_name,
            "comments":     self._run_comments.text().strip(),
            "plate1":       self._get_plate_barcode(1),
            "plate2":       self._get_plate_barcode(2),
            "transfer_dir": self._transfer_dir.text().strip(),
        }

        try:
            csv_text = generate_run_csv(run_settings, active_cells)
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
            return

        default_name = run_name.replace(":", "-").replace(" ", "_") + ".csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Run Design CSV", default_name, "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text)
            QMessageBox.information(self, "Export", f"저장 완료:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"파일 저장 실패:\n{e}")
