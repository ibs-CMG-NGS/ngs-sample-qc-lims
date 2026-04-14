"""
Dashboard 탭 - 샘플 현황 요약 및 차트
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import logging

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from config.settings import STATUS_COLORS, SAMPLE_TYPES
from database import db_manager, get_all_samples, get_latest_qc_metric, get_all_projects, get_all_sequencing_results
from database.models import QCMetric

logger = logging.getLogger(__name__)

# KPI card 색상
CARD_COLORS = {
    "Total":   ("#1565C0", "#E3F2FD"),   # blue
    "Pass":    ("#2E7D32", "#E8F5E9"),   # green
    "Warning": ("#E65100", "#FFF3E0"),   # orange
    "Fail":    ("#B71C1C", "#FFEBEE"),   # red
    "No Data": ("#424242", "#F5F5F5"),   # grey
}

RECENT_COLS = ["Sample ID", "Name", "Type", "Latest Step", "Status", "Registered"]
PROJECT_COLS = [
    "Project", "Species", "Material",
    "Total", "Pass", "Warning", "Fail",
    "Extraction", "Lib Prep", "Sequencing",
]

# ── 단계 진행 현황 헬퍼 ──────────────────────────────────────────────────
_CONC_INST = {"Qubit", "NanoDrop"}

_STAGE_STYLE = {
    "done":     ("#E8F5E9", "#2E7D32", "✓"),   # bg, fg, icon
    "progress": ("#FFF3E0", "#E65100", "⟳"),
    "pending":  ("#F5F5F5", "#757575", "—"),
}


def _sample_stages(sample, metrics: list, parent_metrics: list = None) -> tuple:
    """(extraction_done, libprep_done) 반환.

    parent_metrics: Aliquot 샘플의 경우 부모 QCMetric 리스트를 전달하면
                    Extraction 단계를 부모 데이터로 상속.
    """
    is_rna = (sample.sample_type == "mRNA-seq")
    ext_steps = {"RNA Extraction", "mRNA Elution"} if is_rna else {"gDNA Extraction", "SRE"}
    lib_step  = "Library Prep (RNA)" if is_rna else "Library Prep"

    # Extraction: 자기 데이터 + 부모 데이터(Aliquot 상속) 합산 확인
    ext_check = list(metrics) + (parent_metrics or [])
    ext_conc  = any(m.step in ext_steps and m.instrument in _CONC_INST and m.concentration for m in ext_check)
    ext_femto = any(m.step in ext_steps and m.instrument == "Femto Pulse" for m in ext_check)

    # Library Prep: 자기 데이터만 (Aliquot도 자체 Library Prep 필요)
    lib_conc  = any(m.step == lib_step and m.instrument in _CONC_INST and m.concentration for m in metrics)
    lib_femto = any(m.step == lib_step and m.instrument == "Femto Pulse" for m in metrics)
    return (ext_conc and ext_femto), (lib_conc and lib_femto)


def _stage_cell_style(done: int, total: int) -> tuple:
    if total == 0 or done == 0:
        return _STAGE_STYLE["pending"]
    if done >= total:
        return _STAGE_STYLE["done"]
    return _STAGE_STYLE["progress"]


class _KpiCard(QFrame):
    """숫자 하나를 강조하는 KPI 카드."""

    def __init__(self, title: str, value: str, parent=None):
        super().__init__(parent)
        accent, bg = CARD_COLORS.get(title, ("#37474F", "#ECEFF1"))

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: 1px solid {accent}; "
            f"border-radius: 8px; }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        title_lbl = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(10)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(f"color: {accent}; background: transparent;")
        layout.addWidget(title_lbl)

        self.value_lbl = QLabel(value)
        value_font = QFont()
        value_font.setPointSize(28)
        value_font.setBold(True)
        self.value_lbl.setFont(value_font)
        self.value_lbl.setStyleSheet(f"color: {accent}; background: transparent;")
        layout.addWidget(self.value_lbl)

    def set_value(self, value: str):
        self.value_lbl.setText(value)


class DashboardTab(QWidget):
    """Dashboard 탭 위젯"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    # ── UI 구성 ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── 헤더 바 ──────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)
        root.addLayout(header)

        # ── KPI 카드 행 ──────────────────────────────────────────────
        self._kpi_cards = {}
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        for title_key in ("Total", "Pass", "Warning", "Fail", "No Data"):
            card = _KpiCard(title_key, "–")
            self._kpi_cards[title_key] = card
            kpi_row.addWidget(card)
        root.addLayout(kpi_row)

        # ── 차트 행 ──────────────────────────────────────────────────
        chart_row = QHBoxLayout()
        chart_row.setSpacing(8)

        if HAS_MPL:
            # 왼쪽: QC Status 도넛 차트
            self._status_fig, self._status_ax = plt.subplots(
                figsize=(4.5, 3.2), dpi=90
            )
            self._status_fig.patch.set_facecolor("#FAFAFA")
            self._status_canvas = FigureCanvas(self._status_fig)
            self._status_canvas.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            status_frame = self._wrap_chart(self._status_canvas, "QC Status Distribution")
            chart_row.addWidget(status_frame, 1)

            # 오른쪽: Sample Type 바 차트
            self._type_fig, self._type_ax = plt.subplots(
                figsize=(4.5, 3.2), dpi=90
            )
            self._type_fig.patch.set_facecolor("#FAFAFA")
            self._type_canvas = FigureCanvas(self._type_fig)
            self._type_canvas.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            type_frame = self._wrap_chart(self._type_canvas, "Sample Type Distribution")
            chart_row.addWidget(type_frame, 1)
        else:
            no_chart_lbl = QLabel("matplotlib not available – charts disabled.")
            chart_row.addWidget(no_chart_lbl)

        root.addLayout(chart_row, 2)

        # ── 최근 샘플 테이블 ─────────────────────────────────────────
        recent_frame = QFrame()
        recent_frame.setFrameShape(QFrame.StyledPanel)
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setContentsMargins(8, 8, 8, 8)

        recent_title = QLabel("Recent Samples (latest 10)")
        font2 = QFont()
        font2.setBold(True)
        recent_title.setFont(font2)
        recent_layout.addWidget(recent_title)

        self._recent_table = QTableWidget()
        self._recent_table.setColumnCount(len(RECENT_COLS))
        self._recent_table.setHorizontalHeaderLabels(RECENT_COLS)
        self._recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._recent_table.horizontalHeader().setStretchLastSection(True)
        self._recent_table.setAlternatingRowColors(True)
        recent_layout.addWidget(self._recent_table)

        # ── Project Overview 테이블 ───────────────────────────────────
        proj_frame = QFrame()
        proj_frame.setFrameShape(QFrame.StyledPanel)
        proj_layout = QVBoxLayout(proj_frame)
        proj_layout.setContentsMargins(8, 8, 8, 8)

        proj_title = QLabel("Project Overview")
        proj_title.setFont(font2)
        proj_layout.addWidget(proj_title)

        self._project_table = QTableWidget()
        self._project_table.setColumnCount(len(PROJECT_COLS))
        self._project_table.setHorizontalHeaderLabels(PROJECT_COLS)
        self._project_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._project_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._project_table.horizontalHeader().setStretchLastSection(True)
        self._project_table.setAlternatingRowColors(True)
        proj_layout.addWidget(self._project_table)

        # ── Recent + Project 가로 배치 (스플리터) ─────────────────────
        self._bottom_splitter = QSplitter(Qt.Horizontal)
        self._bottom_splitter.addWidget(recent_frame)
        self._bottom_splitter.addWidget(proj_frame)
        self._bottom_splitter.setStretchFactor(0, 1)
        self._bottom_splitter.setStretchFactor(1, 2)
        root.addWidget(self._bottom_splitter, 1)

    @staticmethod
    def _wrap_chart(canvas, title_text: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel(title_text)
        font = QFont()
        font.setBold(True)
        lbl.setFont(font)
        layout.addWidget(lbl)
        layout.addWidget(canvas)
        return frame

    # ── 데이터 로드 & 렌더링 ─────────────────────────────────────────

    def refresh(self):
        """DB에서 최신 데이터를 읽어 모든 위젯 갱신."""
        try:
            with db_manager.session_scope() as session:
                samples = get_all_samples(session)

                total = len(samples)
                status_counts = {"Pass": 0, "Warning": 0, "Fail": 0, "No Data": 0}
                type_counts: dict[str, int] = {}
                recent_rows = []
                project_stats: dict[str, dict] = {}
                proj_meta = {p.project_name: p for p in get_all_projects(session)}

                # 단계 진행 집계용 배치 로드
                all_metrics = session.query(QCMetric).all()
                metrics_by_sid: dict[str, list] = {}
                for m in all_metrics:
                    metrics_by_sid.setdefault(m.sample_id, []).append(m)

                seq_sample_ids = {r.sample_id for r in get_all_sequencing_results(session)}

                # 어떤 branch 유형이든 자식이 있는 부모 → Gantt 분모에서 제외 (자식이 전진)
                branched_parent_ids = {
                    s.parent_sample_id
                    for s in samples
                    if s.parent_sample_id
                }

                for s in samples:
                    # Sample type 집계
                    type_counts[s.sample_type] = type_counts.get(s.sample_type, 0) + 1

                    # 최신 QC status 집계
                    latest = get_latest_qc_metric(session, s.sample_id)
                    status_key = (
                        latest.status
                        if latest and latest.status in status_counts
                        else "No Data"
                    )
                    status_counts[status_key] += 1

                    # Project별 집계
                    pname = s.project or "(No Project)"
                    if pname not in project_stats:
                        pm = proj_meta.get(pname)
                        project_stats[pname] = {
                            "total": 0, "Pass": 0, "Warning": 0, "Fail": 0, "No Data": 0,
                            "species":  (pm.species  or "") if pm else "",
                            "material": (pm.material or "") if pm else "",
                            "gantt_total": 0,   # Re-extraction 부모 제외한 유효 샘플 수
                            "ext_done": 0, "lib_done": 0, "seq_done": 0,
                        }
                    project_stats[pname]["total"] += 1
                    project_stats[pname][status_key] += 1

                    # Gantt: 자식(branch)이 있는 부모는 분모/분자 모두 제외 (자식이 대표)
                    if s.sample_id in branched_parent_ids:
                        recent_rows.append((
                            s.sample_id,
                            s.sample_name or "",
                            s.sample_type or "",
                            latest.step if latest else "-",
                            latest.status if latest else "No Data",
                            s.created_at.strftime("%Y-%m-%d") if s.created_at else "-",
                        ))
                        continue

                    project_stats[pname]["gantt_total"] += 1

                    # Aliquot 샘플 → 부모 Extraction 데이터 상속
                    parent_metrics = (
                        metrics_by_sid.get(s.parent_sample_id, [])
                        if s.branch_type == "Aliquot" and s.parent_sample_id
                        else []
                    )

                    # 단계 완료 집계
                    ext_ok, lib_ok = _sample_stages(
                        s, metrics_by_sid.get(s.sample_id, []), parent_metrics
                    )
                    if ext_ok:
                        project_stats[pname]["ext_done"] += 1
                    if lib_ok:
                        project_stats[pname]["lib_done"] += 1
                    if s.sample_id in seq_sample_ids:
                        project_stats[pname]["seq_done"] += 1

                    recent_rows.append((
                        s.sample_id,
                        s.sample_name or "",
                        s.sample_type or "",
                        latest.step if latest else "-",
                        latest.status if latest else "No Data",
                        s.created_at.strftime("%Y-%m-%d") if s.created_at else "-",
                    ))

            # 최근 10개 (최신 등록순 — get_all_samples가 desc이므로 첫 10개)
            recent_rows = recent_rows[:10]

        except Exception as e:
            logger.error(f"Dashboard refresh failed: {e}")
            return

        # KPI 카드 업데이트
        self._kpi_cards["Total"].set_value(str(total))
        for key in ("Pass", "Warning", "Fail", "No Data"):
            self._kpi_cards[key].set_value(str(status_counts[key]))

        # 차트 업데이트
        if HAS_MPL:
            self._draw_status_chart(status_counts)
            self._draw_type_chart(type_counts)

        # 최근 샘플 테이블 업데이트
        self._fill_recent_table(recent_rows)

        # Project Overview 테이블 업데이트
        self._fill_project_table(project_stats)

    def _fill_project_table(self, stats: dict):
        rows = sorted(stats.items(), key=lambda x: x[0])
        self._project_table.setRowCount(len(rows))

        col_map = {
            "Pass":    (4, STATUS_COLORS["Pass"]),
            "Warning": (5, STATUS_COLORS["Warning"]),
            "Fail":    (6, STATUS_COLORS["Fail"]),
        }

        for row_idx, (pname, d) in enumerate(rows):
            self._project_table.setItem(row_idx, 0, QTableWidgetItem(pname))
            self._project_table.setItem(row_idx, 1, QTableWidgetItem(d["species"]))
            self._project_table.setItem(row_idx, 2, QTableWidgetItem(d["material"]))
            self._project_table.setItem(row_idx, 3, QTableWidgetItem(str(d["total"])))

            for key, (col, color_hex) in col_map.items():
                item = QTableWidgetItem(str(d[key]))
                if d[key] > 0:
                    item.setForeground(QColor(color_hex))
                    item.setFont(self._bold_font())
                self._project_table.setItem(row_idx, col, item)

            # 단계별 진행 현황 셀 (cols 7, 8, 9) — Re-extraction 교체 부모 제외한 분모
            total = d["gantt_total"]
            for col_off, key in enumerate(["ext_done", "lib_done", "seq_done"]):
                done = d[key]
                bg, fg, icon = _stage_cell_style(done, total)
                item = QTableWidgetItem(f"{icon} {done}/{total}")
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
                self._project_table.setItem(row_idx, 7 + col_off, item)

        self._project_table.resizeColumnsToContents()

    def _draw_status_chart(self, counts: dict):
        ax = self._status_ax
        ax.clear()

        labels = []
        sizes = []
        colors = []
        color_map = {
            "Pass":    STATUS_COLORS["Pass"],
            "Warning": STATUS_COLORS["Warning"],
            "Fail":    STATUS_COLORS["Fail"],
            "No Data": "#9E9E9E",
        }
        for key in ("Pass", "Warning", "Fail", "No Data"):
            if counts[key] > 0:
                labels.append(f"{key} ({counts[key]})")
                sizes.append(counts[key])
                colors.append(color_map[key])

        if not sizes:
            ax.text(
                0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="#9E9E9E",
            )
            ax.axis("off")
        else:
            wedges, texts, autotexts = ax.pie(
                sizes,
                labels=None,
                colors=colors,
                autopct="%1.0f%%",
                pctdistance=0.75,
                startangle=90,
                wedgeprops={"width": 0.55, "edgecolor": "white", "linewidth": 2},
            )
            for at in autotexts:
                at.set_fontsize(9)
                at.set_color("white")
                at.set_fontweight("bold")

            ax.legend(
                wedges, labels,
                loc="lower center",
                bbox_to_anchor=(0.5, -0.15),
                ncol=2,
                fontsize=8,
                frameon=False,
            )

        ax.set_facecolor("#FAFAFA")
        self._status_fig.tight_layout(pad=0.5)
        self._status_canvas.draw()

    def _draw_type_chart(self, counts: dict):
        ax = self._type_ax
        ax.clear()

        if not counts:
            ax.text(
                0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="#9E9E9E",
            )
            ax.axis("off")
        else:
            labels = list(counts.keys())
            values = [counts[k] for k in labels]

            bar_colors = [
                "#1565C0", "#2E7D32", "#6A1B9A", "#E65100",
                "#00695C", "#AD1457", "#37474F",
            ]
            colors = [bar_colors[i % len(bar_colors)] for i in range(len(labels))]

            bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.8)
            for bar, val in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.05,
                    str(val),
                    ha="center", va="bottom", fontsize=10, fontweight="bold",
                )

            ax.set_ylabel("Count", fontsize=9)
            ax.set_ylim(0, max(values) * 1.3)
            ax.tick_params(axis="x", labelsize=9)
            ax.tick_params(axis="y", labelsize=8)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_facecolor("#FAFAFA")

        self._type_fig.tight_layout(pad=0.5)
        self._type_canvas.draw()

    def _fill_recent_table(self, rows):
        self._recent_table.setRowCount(len(rows))
        for row_idx, (sid, name, stype, step, status, reg) in enumerate(rows):
            self._recent_table.setItem(row_idx, 0, QTableWidgetItem(sid))
            self._recent_table.setItem(row_idx, 1, QTableWidgetItem(name))
            self._recent_table.setItem(row_idx, 2, QTableWidgetItem(stype))
            self._recent_table.setItem(row_idx, 3, QTableWidgetItem(step))

            status_item = QTableWidgetItem(status)
            color_hex = STATUS_COLORS.get(status)
            if color_hex:
                status_item.setForeground(QColor(color_hex))
            if status in ("Pass", "Warning", "Fail"):
                status_item.setFont(
                    self._bold_font()
                )
            self._recent_table.setItem(row_idx, 4, status_item)

            self._recent_table.setItem(row_idx, 5, QTableWidgetItem(reg))

        self._recent_table.resizeColumnsToContents()

    @staticmethod
    def _bold_font() -> QFont:
        f = QFont()
        f.setBold(True)
        return f

    # ── GUI 상태 저장/복원 ────────────────────────────────────────────

    def save_gui_state(self, settings):
        from config.gui_state import save_table_widths, save_splitter
        save_table_widths(settings, "DashboardTab/recentTableWidths", self._recent_table)
        save_table_widths(settings, "DashboardTab/projectTableWidths", self._project_table)
        save_splitter(settings, "DashboardTab/bottomSplitter", self._bottom_splitter)

    def restore_gui_state(self, settings):
        from config.gui_state import restore_table_widths, restore_splitter
        restore_table_widths(settings, "DashboardTab/recentTableWidths", self._recent_table)
        restore_table_widths(settings, "DashboardTab/projectTableWidths", self._project_table)
        restore_splitter(settings, "DashboardTab/bottomSplitter", self._bottom_splitter)
