"""
Femto Pulse 희석 계산기 다이얼로그

Qubit 정량값을 기반으로 2단계 serial 희석을 계산하여
Femto Pulse 목표 농도(5-500 pg/µl)에 맞는 희석 프로토콜을 제공한다.
"""
import math
import logging

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QDoubleSpinBox, QHeaderView,
    QAbstractItemView, QComboBox, QGroupBox, QGridLayout, QApplication,
    QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

from config.settings import QC_STEPS, RNA_QC_STEPS
from database import db_manager
from database.models import QCMetric, Sample

logger = logging.getLogger(__name__)

# ── 희석 인자 후보 (pipetting에 편한 round number) ────────────────────────
_NICE_DFS = [
    2, 5, 10, 20, 25, 50, 100, 200, 250,
    500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000,
]

# 테이블 컬럼 정의
_COLS = [
    "Sample ID",
    "Step",
    "Qubit (ng/µl)",
    "Total DF",
    "①sample (µl)",
    "①buffer (µl)",
    "①inter. (pg/µl)",
    "②sample (µl)",
    "②buffer (µl)",
    "Final (pg/µl)",
    "Note",
]
_COL_NOTE = _COLS.index("Note")


# ── 희석 계산 함수 ────────────────────────────────────────────────────────

def calc_dilution_fully_uniform(c_start_ng: float,
                                v1_fixed_ul: float, v_inter_ul: float,
                                v2_fixed_ul: float, v_final_ul: float) -> dict | None:
    """Fully Uniform 희석 계산 — v1·v2 전 샘플 완전 동일.

    부피를 먼저 고정하고 결과 농도를 계산.
    c_final은 샘플마다 다르지만, 모두 5~500 pg/µl 범위에 들어오면 OK.

    Args:
        c_start_ng:  시작 농도 (ng/µl, Qubit 값)
        v1_fixed_ul: Step1에서 취할 원본 샘플 부피 (µl) — 전 샘플 동일
        v_inter_ul:  Step1 희석 총 부피 (µl)
        v2_fixed_ul: Step2에서 취할 중간 샘플 부피 (µl) — 전 샘플 동일
        v_final_ul:  Step2 희석 총 부피 (µl)

    Returns:
        계산 결과 dict, 계산 불가시 None
    """
    if not c_start_ng or c_start_ng <= 0:
        return None
    if v1_fixed_ul <= 0 or v2_fixed_ul <= 0:
        return None
    if v1_fixed_ul > v_inter_ul or v2_fixed_ul > v_final_ul:
        return None

    d1 = v_inter_ul / v1_fixed_ul
    buf1 = v_inter_ul - v1_fixed_ul
    c_inter_pg = c_start_ng * 1_000.0 * v1_fixed_ul / v_inter_ul

    d2 = v_final_ul / v2_fixed_ul
    buf2 = v_final_ul - v2_fixed_ul
    c_final_pg = c_inter_pg * v2_fixed_ul / v_final_ul

    total_df = c_start_ng / (c_final_pg / 1_000.0) if c_final_pg > 0 else 0

    warnings = []
    if c_final_pg < 5:
        warnings.append(f"too dilute ({c_final_pg:.1f}pg/µl)")
    elif c_final_pg > 500:
        warnings.append(f"too conc. ({c_final_pg:.1f}pg/µl)")

    return {
        'total_df': total_df,
        'd1': d1, 'v1': v1_fixed_ul, 'buf1': buf1, 'c_inter': c_inter_pg,
        'd2': d2, 'v2': v2_fixed_ul, 'buf2': buf2, 'c_final': c_final_pg,
        'warnings': warnings,
    }


def suggest_uniform_volumes(concentrations_ng: list[float],
                            v_inter_ul: float, v_final_ul: float,
                            v2_fixed_ul: float) -> float | None:
    """Fully Uniform 모드에서 최적 v1을 자동 제안.

    전 샘플의 c_final이 5~500 pg/µl 범위 중앙(기하평균 ≈ 50 pg/µl)에
    오도록 v1을 계산. 범위 초과 샘플이 있으면 최대한 많이 포함하는 값 반환.

    Args:
        concentrations_ng: 샘플 농도 목록 (ng/µl)
        v_inter_ul:  Step1 희석 총 부피 (µl)
        v_final_ul:  Step2 희석 총 부피 (µl)
        v2_fixed_ul: Step2 고정 샘플 부피 (µl)

    Returns:
        제안 v1 (µl), 계산 불가 시 None
    """
    concs = [c for c in concentrations_ng if c and c > 0]
    if not concs:
        return None

    import math
    c_geomean = math.exp(sum(math.log(c) for c in concs) / len(concs))

    # c_final_geomean ≈ 50 pg/µl (5~500 범위의 기하평균)
    # c_final = c_start × v1 × v2 / (v_inter × v_final) × 1000
    # → v1 = 50 × v_inter × v_final / (c_geomean × v2 × 1000)
    v1 = 50.0 * v_inter_ul * v_final_ul / (c_geomean * v2_fixed_ul * 1_000.0)

    # 0.5µl 미만이면 0.5로 올림, v_inter 초과면 None
    v1 = max(v1, 0.5)
    if v1 > v_inter_ul:
        return None
    return round(v1, 2)


def calc_dilution(c_start_ng: float, c_target_pg: float,
                  v_inter_ul: float, v_final_ul: float,
                  min_vol_ul: float = 1.0,
                  v_sample_ul: float = 0.0) -> dict | None:
    """2단계 serial 희석 계산.

    Args:
        c_start_ng:  시작 농도 (ng/µl, Qubit 값)
        c_target_pg: 목표 최종 농도 (pg/µl)
        v_inter_ul:  1단계 희석 최종 부피 (µl)
        v_final_ul:  2단계 희석 최종 부피 (µl)
        min_vol_ul:  최소 피펫팅 부피 (µl), Step1 sample 하한 (Auto 모드에서만 사용)
        v_sample_ul: 1단계에서 취할 원본 샘플 부피 (µl); 0이면 자동 선택

    Returns:
        계산 결과 dict, 계산 불가시 None
    """
    if not c_start_ng or c_start_ng <= 0:
        return None

    c_target_ng = c_target_pg / 1_000.0
    if c_target_ng <= 0:
        return None

    total_df = c_start_ng / c_target_ng

    if v_sample_ul > 0:
        # 고정 v1 모드: 사용자가 지정한 샘플 부피로 D1 역산
        v1 = v_sample_ul
        d1 = v_inter_ul / v1
    else:
        # Auto 모드: D1을 nice number로 자동 선택
        max_d1 = v_inter_ul / min_vol_ul
        valid_d1s = [d for d in _NICE_DFS if d <= max_d1 and d <= total_df]
        if not valid_d1s:
            valid_d1s = [_NICE_DFS[0]]
        target_d1 = math.sqrt(total_df)
        d1 = min(valid_d1s,
                 key=lambda d: abs(math.log(d / target_d1) if d > 0 else float('inf')))
        v1 = v_inter_ul / d1

    d2 = total_df / d1
    buf1 = v_inter_ul - v1
    c_inter_pg = c_start_ng * 1_000.0 / d1

    v2 = v_final_ul / d2
    buf2 = v_final_ul - v2
    c_final_pg = c_inter_pg / d2

    warnings = []
    if v1 < 1.0:
        warnings.append(f"①{v1:.2f}µl<1µl")
    if v2 < 0.5:
        warnings.append(f"②{v2:.2f}µl<0.5µl")
    if c_final_pg < 5:
        warnings.append(f"too dilute ({c_final_pg:.1f}pg/µl)")
    elif c_final_pg > 500:
        warnings.append(f"too conc. ({c_final_pg:.1f}pg/µl)")

    return {
        'total_df':  total_df,
        'd1': d1,   'v1': v1,   'buf1': buf1,  'c_inter': c_inter_pg,
        'd2': d2,   'v2': v2,   'buf2': buf2,  'c_final': c_final_pg,
        'warnings':  warnings,
    }


# ── 다이얼로그 ─────────────────────────────────────────────────────────────

class DilutionCalcDialog(QDialog):
    """Femto Pulse 희석 계산기 다이얼로그.

    - 프로젝트 내 Qubit 정량값이 있는 샘플을 자동 로드
    - 목표 농도·중간 부피·최종 부피를 파라미터로 입력
    - 2단계 serial 희석 방법 자동 계산 및 표시
    - 결과를 클립보드에 복사 가능
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Femto Pulse Dilution Calculator")
        self.setMinimumSize(1150, 560)
        self._rows: list[tuple] = []   # (sample_id, step, qubit_conc_ng)
        self._build_ui()
        self._populate_projects()
        self._load_samples()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── 파라미터 그룹 ──────────────────────────────────────────
        param_box = QGroupBox("Parameters")
        pg = QGridLayout(param_box)
        pg.setHorizontalSpacing(8)

        # Row 0: filters
        pg.addWidget(QLabel("Project:"), 0, 0)
        self._project_combo = QComboBox()
        self._project_combo.setMinimumWidth(150)
        self._project_combo.currentIndexChanged.connect(self._load_samples)
        pg.addWidget(self._project_combo, 0, 1)

        pg.addWidget(QLabel("Step:"), 0, 2)
        self._step_combo = QComboBox()
        self._step_combo.addItem("All Steps")
        for s in QC_STEPS + RNA_QC_STEPS:
            self._step_combo.addItem(s)
        self._step_combo.setCurrentText("gDNA Extraction")
        self._step_combo.currentIndexChanged.connect(self._load_samples)
        pg.addWidget(self._step_combo, 0, 3)

        pg.addWidget(QLabel("Instrument:"), 0, 4)
        self._instr_combo = QComboBox()
        self._instr_combo.addItems(["Qubit", "NanoDrop"])
        self._instr_combo.currentIndexChanged.connect(self._on_instrument_changed)
        pg.addWidget(self._instr_combo, 0, 5)

        pg.addWidget(QLabel("Mode:"), 0, 6)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Precise (current)", "Fully Uniform"])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        pg.addWidget(self._mode_combo, 0, 7)

        pg.setColumnStretch(8, 1)  # spacer

        # Row 1: dilution parameters
        # ── Precise 전용 ──
        self._lbl_target = QLabel("Target (pg/µl):")
        pg.addWidget(self._lbl_target, 1, 0)
        self._target_spin = QDoubleSpinBox()
        self._target_spin.setRange(5, 500)
        self._target_spin.setValue(200.0)
        self._target_spin.setSingleStep(50)
        self._target_spin.setDecimals(0)
        self._target_spin.setFixedWidth(80)
        pg.addWidget(self._target_spin, 1, 1)

        # ── Uniform 전용: ① v1 fixed ──
        self._lbl_v1fixed = QLabel("① v1 (µl):")
        self._lbl_v1fixed.hide()
        pg.addWidget(self._lbl_v1fixed, 1, 0)
        self._v1fixed_spin = QDoubleSpinBox()
        self._v1fixed_spin.setRange(0.5, 50.0)
        self._v1fixed_spin.setValue(1.0)
        self._v1fixed_spin.setSingleStep(0.5)
        self._v1fixed_spin.setDecimals(1)
        self._v1fixed_spin.setFixedWidth(70)
        self._v1fixed_spin.hide()
        pg.addWidget(self._v1fixed_spin, 1, 1)

        pg.addWidget(QLabel("Inter. volume (µl):"), 1, 2)
        self._vinter_spin = QDoubleSpinBox()
        self._vinter_spin.setRange(10, 1000)
        self._vinter_spin.setValue(100.0)
        self._vinter_spin.setSingleStep(10)
        self._vinter_spin.setDecimals(0)
        self._vinter_spin.setFixedWidth(80)
        pg.addWidget(self._vinter_spin, 1, 3)

        pg.addWidget(QLabel("Final volume (µl):"), 1, 4)
        self._vfinal_spin = QDoubleSpinBox()
        self._vfinal_spin.setRange(2, 100)
        self._vfinal_spin.setValue(10.0)
        self._vfinal_spin.setSingleStep(2)
        self._vfinal_spin.setDecimals(0)
        self._vfinal_spin.setFixedWidth(70)
        pg.addWidget(self._vfinal_spin, 1, 5)

        # ── Precise 전용: Min pipette ──
        self._lbl_minvol = QLabel("Min pipette (µl):")
        pg.addWidget(self._lbl_minvol, 1, 6)
        self._minvol_spin = QDoubleSpinBox()
        self._minvol_spin.setRange(0.1, 5)
        self._minvol_spin.setValue(1.0)
        self._minvol_spin.setSingleStep(0.5)
        self._minvol_spin.setDecimals(1)
        self._minvol_spin.setFixedWidth(65)
        pg.addWidget(self._minvol_spin, 1, 7)

        # ── Precise 전용: ① Sample ──
        self._lbl_vsample = QLabel("① Sample (µl):")
        pg.addWidget(self._lbl_vsample, 1, 8)
        self._vsample_spin = QDoubleSpinBox()
        self._vsample_spin.setRange(0.0, 50.0)
        self._vsample_spin.setValue(0.0)
        self._vsample_spin.setSingleStep(0.5)
        self._vsample_spin.setDecimals(1)
        self._vsample_spin.setFixedWidth(70)
        self._vsample_spin.setSpecialValueText("Auto")
        pg.addWidget(self._vsample_spin, 1, 9)

        # ── Uniform 전용: ② v2 fixed + Suggest ──
        self._lbl_v2fixed = QLabel("② v2 (µl):")
        self._lbl_v2fixed.hide()
        pg.addWidget(self._lbl_v2fixed, 1, 6)
        self._v2fixed_spin = QDoubleSpinBox()
        self._v2fixed_spin.setRange(0.5, 10.0)
        self._v2fixed_spin.setValue(1.0)
        self._v2fixed_spin.setSingleStep(0.5)
        self._v2fixed_spin.setDecimals(1)
        self._v2fixed_spin.setFixedWidth(65)
        self._v2fixed_spin.hide()
        pg.addWidget(self._v2fixed_spin, 1, 7)

        self._btn_suggest = QPushButton("Suggest v1")
        self._btn_suggest.setFixedWidth(85)
        self._btn_suggest.setToolTip("현재 샘플 농도 기반으로 최적 v1을 자동 계산")
        self._btn_suggest.clicked.connect(self._suggest_v1)
        self._btn_suggest.hide()
        pg.addWidget(self._btn_suggest, 1, 8)

        btn_calc = QPushButton("Calculate")
        btn_calc.setFixedWidth(90)
        btn_calc.clicked.connect(self._calculate)
        pg.addWidget(btn_calc, 1, 12)

        pg.setColumnStretch(13, 1)
        layout.addWidget(param_box)

        # ── 도움말 레이블 ─────────────────────────────────────────
        self._help_lbl = QLabel()
        self._help_lbl.setStyleSheet("color: #555; font-size: 11px;")
        layout.addWidget(self._help_lbl)
        self._update_help_label()

        # ── 결과 테이블 ───────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setSectionResizeMode(_COL_NOTE, QHeaderView.Stretch)
        hdr.setStretchLastSection(False)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._table, 1)

        # ── 하단 버튼 ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy Table to Clipboard")
        btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        self._status_lbl = QLabel("")
        btn_row.addWidget(self._status_lbl)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    # ── 모드 전환 ────────────────────────────────────────────────────

    def _is_uniform_mode(self) -> bool:
        return self._mode_combo.currentIndex() == 1

    def _on_mode_changed(self):
        uniform = self._is_uniform_mode()
        # Precise 전용 위젯
        self._lbl_target.setVisible(not uniform)
        self._target_spin.setVisible(not uniform)
        self._lbl_minvol.setVisible(not uniform)
        self._minvol_spin.setVisible(not uniform)
        self._lbl_vsample.setVisible(not uniform)
        self._vsample_spin.setVisible(not uniform)
        # Uniform 전용 위젯
        self._lbl_v1fixed.setVisible(uniform)
        self._v1fixed_spin.setVisible(uniform)
        self._lbl_v2fixed.setVisible(uniform)
        self._v2fixed_spin.setVisible(uniform)
        self._btn_suggest.setVisible(uniform)
        self._update_help_label()
        self._calculate()

    def _update_help_label(self):
        if self._is_uniform_mode():
            self._help_lbl.setText(
                "Fully Uniform: ① v1·①buf / ② v2·②buf 전 샘플 완전 동일 (파란 열)  |  "
                "c_inter·Final은 샘플마다 다름 (5~500 pg/µl 범위 내 OK)  |  "
                "🟢 OK   🔴 out of range    [Suggest v1] = 최적 v1 자동 계산"
            )
        else:
            self._help_lbl.setText(
                "① = Step 1 (sample → intermediate)    "
                "② = Step 2 (intermediate → final)    "
                "🟢 OK   🟡 volume warning   🔴 concentration out of range"
            )

    def _suggest_v1(self):
        """현재 샘플 농도 기반으로 최적 v1을 계산해 스핀박스에 반영."""
        concs = [c for _, _, c in self._rows if c and c > 0]
        if not concs:
            self._status_lbl.setText("샘플 데이터 없음")
            return
        v1 = suggest_uniform_volumes(
            concs,
            self._vinter_spin.value(),
            self._vfinal_spin.value(),
            self._v2fixed_spin.value(),
        )
        if v1 is None:
            self._status_lbl.setText("⚠ Suggest 불가: v1이 Inter. volume 초과")
            return
        self._v1fixed_spin.setValue(v1)
        self._status_lbl.setText(f"Suggested v1 = {v1} µl  (c_final 기하평균 ≈ 50 pg/µl)")
        self._calculate()

    # ── 데이터 로드 ──────────────────────────────────────────────────

    def _on_instrument_changed(self):
        """Instrument 변경 시 Step 필터를 All Steps로 리셋 후 샘플 로드."""
        self._step_combo.blockSignals(True)
        self._step_combo.setCurrentIndex(0)  # "All Steps"
        self._step_combo.blockSignals(False)
        self._load_samples()

    def _populate_projects(self):
        """DB에서 프로젝트 목록 로드 후 콤보박스 채우기."""
        projects = []
        try:
            with db_manager.session_scope() as session:
                rows = (
                    session.query(Sample.project)
                    .filter(
                        Sample.project.isnot(None),
                        Sample.project != '',
                    )
                    .distinct()
                    .order_by(Sample.project)
                    .all()
                )
                projects = [r[0] for r in rows]
        except Exception as e:
            logger.error(f"DilutionCalc project load error: {e}")

        self._project_combo.blockSignals(True)
        self._project_combo.clear()
        self._project_combo.addItem("All Projects")
        for p in projects:
            self._project_combo.addItem(p)
        self._project_combo.blockSignals(False)

    def _load_samples(self):
        """DB에서 정량값이 있는 샘플 로드 (project/step/instrument 필터 적용)."""
        project_filter = self._project_combo.currentText()
        step_filter = self._step_combo.currentText()
        instr = self._instr_combo.currentText()  # "Qubit" or "NanoDrop"

        # 컬럼 헤더 업데이트
        self._table.setHorizontalHeaderItem(2, QTableWidgetItem(f"{instr} (ng/µl)"))

        self._rows = []

        try:
            with db_manager.session_scope() as session:
                query = (
                    session.query(QCMetric)
                    .join(Sample, Sample.sample_id == QCMetric.sample_id)
                    .filter(
                        QCMetric.instrument == instr,
                        QCMetric.concentration.isnot(None),
                    )
                )
                if project_filter != "All Projects":
                    query = query.filter(Sample.project == project_filter)
                if step_filter != "All Steps":
                    query = query.filter(QCMetric.step == step_filter)

                metrics = query.order_by(
                    QCMetric.sample_id,
                    QCMetric.measured_at.desc(),
                ).all()

                # 같은 (sample_id, step) 조합에서 최신 1개만 사용
                seen: set = set()
                for m in metrics:
                    key = (m.sample_id, m.step or '')
                    if key not in seen:
                        seen.add(key)
                        self._rows.append((
                            m.sample_id,
                            m.step or '-',
                            m.concentration,
                        ))
        except Exception as e:
            logger.error(f"DilutionCalc load error: {e}")

        self._calculate()

    # ── 계산 및 테이블 갱신 ──────────────────────────────────────────

    def _calculate(self):
        v_inter  = self._vinter_spin.value()
        v_final  = self._vfinal_spin.value()
        uniform  = self._is_uniform_mode()

        # Fully Uniform: 고정 부피 열 (파란색 강조)
        _UNIFORM_FIXED_COLS = {
            _COLS.index("①sample (µl)"),
            _COLS.index("①buffer (µl)"),
            _COLS.index("②sample (µl)"),
            _COLS.index("②buffer (µl)"),
        }

        self._table.setRowCount(len(self._rows))
        ok_count = warn_count = err_count = 0

        for row, (sid, step, conc_ng) in enumerate(self._rows):
            if uniform:
                res = calc_dilution_fully_uniform(
                    conc_ng,
                    self._v1fixed_spin.value(),
                    v_inter,
                    self._v2fixed_spin.value(),
                    v_final,
                )
            else:
                res = calc_dilution(
                    conc_ng,
                    self._target_spin.value(),
                    v_inter, v_final,
                    self._minvol_spin.value(),
                    self._vsample_spin.value(),
                )

            if res:
                note = "  |  ".join(res['warnings']) if res['warnings'] else "OK"
                row_vals = [
                    sid,
                    step,
                    f"{conc_ng:.3f}",
                    f"{res['total_df']:.0f}x",
                    f"{res['v1']:.2f}",
                    f"{res['buf1']:.2f}",
                    f"{res['c_inter']:.1f}",
                    f"{res['v2']:.2f}",
                    f"{res['buf2']:.2f}",
                    f"{res['c_final']:.1f}",
                    note,
                ]
                conc_ok = 5 <= res['c_final'] <= 500
                has_vol_warn = any('µl<' in w or '불가' in w for w in res['warnings'])
                if conc_ok and not has_vol_warn:
                    bg = QColor(220, 245, 220)
                    ok_count += 1
                elif conc_ok and has_vol_warn:
                    bg = QColor(255, 248, 200)
                    warn_count += 1
                else:
                    bg = QColor(255, 220, 220)
                    err_count += 1
            else:
                row_vals = [sid, step,
                            f"{conc_ng:.3f}" if conc_ng else "-",
                            "-", "-", "-", "-", "-", "-", "-",
                            "No Qubit data"]
                bg = QColor(240, 240, 240)

            for col, val in enumerate(row_vals):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                # Fully Uniform: 피펫팅 부피가 동일한 열은 하늘색으로 강조
                if uniform and res and col in _UNIFORM_FIXED_COLS:
                    item.setBackground(QBrush(QColor(200, 230, 255)))
                else:
                    item.setBackground(QBrush(bg))
                self._table.setItem(row, col, item)

        self._table.resizeColumnsToContents()
        self._status_lbl.setText(
            f"🟢 {ok_count}  🟡 {warn_count}  🔴 {err_count}  "
            f"(total {len(self._rows)} samples)"
        )

    # ── 클립보드 복사 ────────────────────────────────────────────────

    def _copy_to_clipboard(self):
        lines = ["\t".join(_COLS)]
        for row in range(self._table.rowCount()):
            line = [
                (self._table.item(row, col).text()
                 if self._table.item(row, col) else "")
                for col in range(self._table.columnCount())
            ]
            lines.append("\t".join(line))
        QApplication.clipboard().setText("\n".join(lines))
        self._status_lbl.setText("Copied to clipboard!")
