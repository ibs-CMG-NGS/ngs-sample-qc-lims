"""
메인 윈도우 - NGS Sample QC LIMS
"""
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QMenuBar, QMenu, QStatusBar, QMessageBox,
    QLabel, QAction, QProgressDialog,
    QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QGroupBox,
    QTextBrowser,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
import logging

from config.settings import WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT
from database import db_manager
from ui.sample_tab import SampleTab
from ui.dashboard_tab import DashboardTab
from ui.reports_tab import ReportsTab
from ui.analysis_tab import AnalysisTab
from ui.calendar_tab import CalendarTab

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """메인 윈도우 클래스"""
    
    def __init__(self):
        super().__init__()
        self.db_manager = db_manager
        self.init_ui()
        self.init_database()
        
    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle(WINDOW_TITLE)
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 레이아웃
        layout = QVBoxLayout(central_widget)
        
        # 탭 위젯 생성
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        
        # 탭 추가 (placeholder - 추후 구현)
        self._create_tabs()
        
        # 메뉴바 생성
        self._create_menu_bar()

        # 상태바 생성
        self.statusBar().showMessage('Ready')
        
        logger.info("Main window initialized")
    
    def _create_tabs(self):
        """탭 생성"""
        # Dashboard 탭
        self.dashboard_tab = DashboardTab()
        self.tabs.addTab(self.dashboard_tab, "📊 Dashboard")

        # Sample Management 탭
        self.sample_tab = SampleTab()
        self.tabs.addTab(self.sample_tab, "🧬 Samples")
        
        # QC Analysis 탭
        self.analysis_tab = AnalysisTab()
        self.tabs.addTab(self.analysis_tab, "📈 Analysis")

        # Reports 탭
        self.reports_tab = ReportsTab()
        self.tabs.addTab(self.reports_tab, "📄 Reports")

        # Calendar 탭
        self.calendar_tab = CalendarTab()
        self.tabs.addTab(self.calendar_tab, "📅 Calendar")
    
    def _create_menu_bar(self):
        """메뉴바 생성"""
        menubar = self.menuBar()
        
        # File 메뉴
        file_menu = menubar.addMenu('&File')
        
        new_sample_action = QAction('&New Sample', self)
        new_sample_action.setShortcut('Ctrl+N')
        new_sample_action.triggered.connect(self.new_sample)
        file_menu.addAction(new_sample_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('&Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit 메뉴
        edit_menu = menubar.addMenu('&Edit')
        
        settings_action = QAction('&Settings', self)
        settings_action.triggered.connect(self.open_settings)
        edit_menu.addAction(settings_action)
        
        # View 메뉴
        view_menu = menubar.addMenu('&View')

        refresh_action = QAction('&Refresh', self)
        refresh_action.setShortcut('F5')
        refresh_action.triggered.connect(self.refresh_data)
        view_menu.addAction(refresh_action)

        view_menu.addSeparator()

        # 탭 이동 단축키 (Ctrl+1 ~ Ctrl+5)
        tab_shortcuts = [
            ('📊 &Dashboard',  'Ctrl+1', 0),
            ('🧬 &Samples',    'Ctrl+2', 1),
            ('📈 &Analysis',   'Ctrl+3', 2),
            ('📄 &Reports',    'Ctrl+4', 3),
            ('📅 &Calendar',   'Ctrl+5', 4),
        ]
        for label, shortcut, idx in tab_shortcuts:
            act = QAction(label, self)
            act.setShortcut(shortcut)
            act.triggered.connect(lambda checked, i=idx: self.tabs.setCurrentIndex(i))
            view_menu.addAction(act)

        # Reports 메뉴
        reports_menu = menubar.addMenu('&Reports')

        pdf_action = QAction('Export &PDF…', self)
        pdf_action.setShortcut('Ctrl+Shift+P')
        pdf_action.setStatusTip('선택된 샘플의 QC 리포트를 PDF로 내보냅니다')
        pdf_action.triggered.connect(self._export_pdf_menu)
        reports_menu.addAction(pdf_action)

        excel_action = QAction('Export &Excel…', self)
        excel_action.setShortcut('Ctrl+Shift+E')
        excel_action.setStatusTip('선택된 샘플의 QC 데이터를 Excel로 내보냅니다')
        excel_action.triggered.connect(self._export_excel_menu)
        reports_menu.addAction(excel_action)

        # Tools 메뉴
        tools_menu = menubar.addMenu('&Tools')

        ladder_compare_action = QAction('&Compare Ladder Runs', self)
        ladder_compare_action.triggered.connect(self._open_ladder_compare)
        tools_menu.addAction(ladder_compare_action)

        dilution_action = QAction('&Femto Pulse Dilution Calculator', self)
        dilution_action.triggered.connect(self._open_dilution_calc)
        tools_menu.addAction(dilution_action)

        rejudge_action = QAction('&Re-judge All QC Status', self)
        rejudge_action.triggered.connect(self._rejudge_all_qc)
        tools_menu.addAction(rejudge_action)

        revio_action = QAction('&Revio Run Designer…', self)
        revio_action.triggered.connect(self._open_revio_designer)
        tools_menu.addAction(revio_action)

        seq_import_action = QAction('&Import Sequencing QC…', self)
        seq_import_action.triggered.connect(self._open_seq_import)
        tools_menu.addAction(seq_import_action)

        migrate_action = QAction('&Migrate FemtoPulse Files to Local…', self)
        migrate_action.triggered.connect(self._migrate_femtopulse_files)
        tools_menu.addAction(migrate_action)

        tools_menu.addSeparator()

        # Google Sheets 서브메뉴
        sheets_menu = tools_menu.addMenu('&Google Sheets')

        sheets_config_action = QAction('&Configure...', self)
        sheets_config_action.triggered.connect(self._open_sheets_config)
        sheets_menu.addAction(sheets_config_action)

        sheets_push_action = QAction('&Push to Sheets (DB → 시트)', self)
        sheets_push_action.triggered.connect(self._sheets_push)
        sheets_menu.addAction(sheets_push_action)

        sheets_pull_action = QAction('P&ull from Sheets (시트 → DB)', self)
        sheets_pull_action.triggered.connect(self._sheets_pull)
        sheets_menu.addAction(sheets_pull_action)

        sheets_menu.addSeparator()
        tg_push_action = QAction('Push &TG Template (TG 형식 내보내기)', self)
        tg_push_action.triggered.connect(self._sheets_push_tg)
        sheets_menu.addAction(tg_push_action)

        # Help 메뉴
        help_menu = menubar.addMenu('&Help')

        guide_action = QAction('사용법 안내…', self)
        guide_action.setShortcut('F1')
        guide_action.triggered.connect(lambda: self._show_help_dialog(0))
        help_menu.addAction(guide_action)

        criteria_action = QAction('QC 판정 기준…', self)
        criteria_action.triggered.connect(lambda: self._show_help_dialog(1))
        help_menu.addAction(criteria_action)

        shortcuts_action = QAction('단축키 목록…', self)
        shortcuts_action.setShortcut('Ctrl+/')
        shortcuts_action.triggered.connect(lambda: self._show_help_dialog(2))
        help_menu.addAction(shortcuts_action)

        tools_desc_action = QAction('도구 설명…', self)
        tools_desc_action.triggered.connect(lambda: self._show_help_dialog(3))
        help_menu.addAction(tools_desc_action)

        help_menu.addSeparator()

        about_action = QAction('&About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def init_database(self):
        """데이터베이스 초기화"""
        try:
            self.db_manager.initialize()
            logger.info("Database initialized successfully")
            self.statusBar().showMessage('Database connected', 3000)
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            QMessageBox.critical(
                self,
                "Database Error",
                f"Failed to initialize database:\n{str(e)}"
            )
        # DB 초기화 후 GUI 상태 복원
        self._restore_gui_state()

    # ── GUI 상태 저장/복원 ────────────────────────────────────────────

    def _save_gui_state(self):
        """종료 시 모든 GUI 상태를 settings 파일에 저장."""
        from config.gui_state import get_settings
        s = get_settings()
        s.setValue("MainWindow/geometry",   self.saveGeometry())
        s.setValue("MainWindow/windowState", self.saveState())
        s.setValue("MainWindow/currentTab", self.tabs.currentIndex())
        self.sample_tab.save_gui_state(s)
        self.dashboard_tab.save_gui_state(s)
        self.analysis_tab.save_gui_state(s)
        self.reports_tab.save_gui_state(s)
        self.calendar_tab.save_gui_state(s)
        s.sync()
        logger.info("GUI state saved")

    def _restore_gui_state(self):
        """시작 시 저장된 GUI 상태를 복원."""
        from config.gui_state import get_settings
        from PyQt5.QtCore import QByteArray
        s = get_settings()

        geom = s.value("MainWindow/geometry")
        if isinstance(geom, QByteArray) and not geom.isEmpty():
            self.restoreGeometry(geom)

        state = s.value("MainWindow/windowState")
        if isinstance(state, QByteArray) and not state.isEmpty():
            self.restoreState(state)

        tab_idx = s.value("MainWindow/currentTab")
        if tab_idx is not None:
            try:
                self.tabs.setCurrentIndex(int(tab_idx))
            except (ValueError, TypeError):
                pass

        self.sample_tab.restore_gui_state(s)
        self.dashboard_tab.restore_gui_state(s)
        self.analysis_tab.restore_gui_state(s)
        self.reports_tab.restore_gui_state(s)
        self.calendar_tab.restore_gui_state(s)
        logger.info("GUI state restored")
    
    def _on_tab_changed(self, index: int):
        """탭 전환 시 자동 새로고침."""
        widget = self.tabs.widget(index)
        if widget is self.dashboard_tab:
            self.dashboard_tab.refresh()
        elif widget is self.analysis_tab:
            self.analysis_tab.refresh()
        elif widget is self.reports_tab:
            self.reports_tab.refresh()
        elif widget is self.calendar_tab:
            self.calendar_tab.refresh()

    def new_sample(self):
        """새 샘플 등록"""
        self.tabs.setCurrentWidget(self.sample_tab)
        self.sample_tab.open_new_sample_dialog()
    
    def open_settings(self):
        """설정 열기"""
        self.statusBar().showMessage('Settings - Not implemented yet')
    
    def refresh_data(self):
        """데이터 새로고침"""
        self.statusBar().showMessage('Refreshing data...')
        self.sample_tab.refresh_samples()
        self.statusBar().showMessage('Data refreshed', 3000)
    
    def _open_ladder_compare(self):
        from ui.ladder_compare_dialog import LadderCompareDialog
        dlg = LadderCompareDialog(self)
        dlg.exec_()

    def _open_dilution_calc(self):
        from ui.dilution_calc_dialog import DilutionCalcDialog
        dlg = DilutionCalcDialog(self)
        dlg.exec_()

    def _open_revio_designer(self):
        from ui.revio_dialog import RevioRunDesignerDialog
        dlg = RevioRunDesignerDialog(self)
        dlg.exec_()

    def _open_seq_import(self):
        from ui.sequencing_result_dialog import SequencingResultDialog
        dlg = SequencingResultDialog(self)
        if dlg.exec_() == SequencingResultDialog.Accepted:
            # Sample 탭 seq 결과 갱신
            sample_tab = self.tabs.widget(1)
            if hasattr(sample_tab, '_selected_sample_id') and sample_tab._selected_sample_id:
                sample_tab._load_seq_results(sample_tab._selected_sample_id)

    def _migrate_femtopulse_files(self):
        """기존 FemtoPulseRun 절대 경로 레코드를 로컬 복사 + 상대 경로로 소급 적용."""
        import shutil
        from pathlib import Path
        from config.settings import FEMTOPULSE_IMAGES_DIR, DATA_DIR
        from database.models import FemtoPulseRun, RawTrace, QCMetric

        reply = QMessageBox.question(
            self, "Migrate FemtoPulse Files",
            "DB에 저장된 기존 FemtoPulse 파일을 data/femtopulse_images/ 로 복사하고\n"
            "경로를 상대 경로로 업데이트합니다.\n\n"
            "원본 파일이 현재 PC에 존재해야 복사 가능합니다.\n"
            "계속할까요?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 파일 1개를 복사하고 상대경로 문자열 반환. 실패/없으면 원본 반환.
        def _copy_file(abs_path: str, dest_dir: Path) -> tuple[str, str]:
            """(new_path_str, status) — status: 'copied'|'exists'|'missing'"""
            p = Path(abs_path)
            if not p.is_file():
                return abs_path, 'missing'
            dest = dest_dir / p.name
            if not dest.exists():
                shutil.copy2(p, dest)
                status = 'copied'
            else:
                status = 'exists'
            return str(dest.relative_to(DATA_DIR)), status

        FILE_COLS = [
            'quality_table_path', 'peak_table_path',
            'electropherogram_path', 'size_calibration_path', 'smear_analysis_path',
        ]

        n_copied = n_skipped = n_missing = 0

        try:
            with db_manager.session_scope() as session:
                runs = session.query(FemtoPulseRun).all()
                progress = QProgressDialog(
                    "FemtoPulse 파일 마이그레이션 중…", "Cancel", 0, len(runs), self
                )
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(0)

                for i, run in enumerate(runs):
                    progress.setValue(i)
                    if progress.wasCanceled():
                        break

                    # electropherogram_path로 이미 상대 경로인지 판단
                    sample_path = run.electropherogram_path or run.quality_table_path or ""
                    if sample_path and not Path(sample_path).is_absolute():
                        n_skipped += 1
                        continue

                    # 대상 폴더: measured_at 타임스탬프 기준
                    ts = run.measured_at or run.created_at
                    ts_str = ts.strftime("%Y%m%d_%H%M%S") if ts else f"run_{run.id}"
                    dest_dir = FEMTOPULSE_IMAGES_DIR / ts_str
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    # run_folder 업데이트 (디렉터리)
                    run.run_folder = str(dest_dir.relative_to(DATA_DIR))

                    # 5개 파일 컬럼 처리
                    old_new: dict[str, str] = {}   # old_abs -> new_rel
                    for col in FILE_COLS:
                        old_path = getattr(run, col)
                        if not old_path:
                            continue
                        new_path, status = _copy_file(old_path, dest_dir)
                        if status == 'copied':
                            n_copied += 1
                        elif status == 'missing':
                            n_missing += 1
                        old_new[old_path] = new_path
                        setattr(run, col, new_path)

                    # RawTrace.raw_file_path 업데이트 (electropherogram 경로 변경분)
                    for old_p, new_p in old_new.items():
                        if old_p == new_p:
                            continue
                        (session.query(RawTrace)
                         .filter(RawTrace.raw_file_path == old_p)
                         .update({'raw_file_path': new_p}, synchronize_session=False))
                        # QCMetric.data_file 업데이트
                        (session.query(QCMetric)
                         .filter(QCMetric.data_file == old_p)
                         .update({'data_file': new_p}, synchronize_session=False))

                progress.setValue(len(runs))

        except Exception as e:
            logger.error(f"FemtoPulse migration failed: {e}")
            QMessageBox.critical(self, "Migration Error", f"마이그레이션 중 오류 발생:\n{e}")
            return

        QMessageBox.information(
            self, "Migration Complete",
            f"마이그레이션 완료\n\n"
            f"  복사됨:        {n_copied}개 파일\n"
            f"  이미 완료:     {n_skipped}개 run (스킵)\n"
            f"  파일 없음:     {n_missing}개 (원본 경로 유지)\n\n"
            "이제 data/lims.db + data/femtopulse_images/ 를\n"
            "복사하면 다른 PC에서도 그래프가 표시됩니다."
        )

    def _rejudge_all_qc(self):
        """모든 QCMetric 레코드에 판정 로직 재실행."""
        reply = QMessageBox.question(
            self, "Re-judge All QC Status",
            "모든 QC 레코드에 대해 Pass/Warning/Fail 판정을 다시 실행합니다.\n"
            "기존 status 값이 덮어씌워집니다. 계속할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        from database.models import QCMetric, Sample
        from analysis.qc_judge import qc_judge

        counts = {"updated": 0, "Pass": 0, "Warning": 0, "Fail": 0, "Pending": 0}
        try:
            with self.db_manager.session_scope() as session:
                metrics = session.query(QCMetric).all()
                for m in metrics:
                    sample = session.query(Sample).filter(
                        Sample.sample_id == m.sample_id
                    ).first()
                    if not sample:
                        continue

                    qc_data = {
                        "step":           m.step,
                        "concentration":  m.concentration,
                        "total_amount":   m.total_amount,
                        "gqn_rin":        m.gqn_rin,
                        "avg_size":       m.avg_size,
                        "purity_260_280": m.purity_260_280,
                        "purity_260_230": m.purity_260_230,
                    }
                    new_status = qc_judge.judge_qc(sample.sample_type, qc_data)
                    m.status = new_status
                    counts["updated"] += 1
                    counts[new_status] = counts.get(new_status, 0) + 1

            msg = (
                f"판정 완료: {counts['updated']}개 레코드 업데이트\n\n"
                f"  Pass:    {counts.get('Pass', 0)}\n"
                f"  Warning: {counts.get('Warning', 0)}\n"
                f"  Fail:    {counts.get('Fail', 0)}\n"
                f"  Pending: {counts.get('Pending', 0)}"
            )
            QMessageBox.information(self, "Re-judge Complete", msg)

            # Sample 탭 갱신
            if hasattr(self, 'sample_tab'):
                self.sample_tab.refresh_samples()

        except Exception as e:
            logger.error(f"Re-judge failed: {e}")
            QMessageBox.critical(self, "Error", f"Re-judge 실패:\n{e}")

    # ── Google Sheets 연동 ─────────────────────────────────────────────

    def _open_sheets_config(self):
        from ui.sheets_config_dialog import SheetsConfigDialog
        dlg = SheetsConfigDialog(self)
        dlg.exec_()

    def _get_sheets_sync(self):
        """설정을 읽어 GSheetSync 인스턴스 반환. 설정 미완료 시 None."""
        from config.settings import get_gsheets_config
        cfg = get_gsheets_config()
        if not cfg["credentials_path"] or not cfg["spreadsheet_id"]:
            reply = QMessageBox.question(
                self, "Google Sheets 설정 필요",
                "Google Sheets 연동 설정이 완료되지 않았습니다.\n"
                "지금 설정하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._open_sheets_config()
                cfg = get_gsheets_config()
            if not cfg["credentials_path"] or not cfg["spreadsheet_id"]:
                return None

        try:
            from integration.google_sheets import GSheetSync
            return GSheetSync(
                cfg["credentials_path"],
                cfg["spreadsheet_id"],
                cfg["sheet_names"],
            )
        except ImportError:
            QMessageBox.critical(
                self, "패키지 없음",
                "gspread 패키지가 설치되지 않았습니다.\n"
                "pip install gspread google-auth 를 실행하세요."
            )
            return None

    def _sheets_push(self):
        """DB → Google Sheets 내보내기."""
        sync = self._get_sheets_sync()
        if sync is None:
            return

        prog = QProgressDialog("Google Sheets로 내보내는 중…", None, 0, 0, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.show()

        try:
            with self.db_manager.session_scope() as session:
                counts = sync.push(session)
            prog.close()
            QMessageBox.information(
                self, "Push 완료",
                f"Google Sheets 내보내기 완료\n\n"
                f"  Samples:    {counts['samples']}개\n"
                f"  QC Metrics: {counts['metrics']}개\n"
                f"  Notes:      {counts['notes']}개",
            )
        except Exception as e:
            prog.close()
            logger.error(f"Sheets push failed: {e}")
            QMessageBox.critical(self, "Push 실패", f"오류:\n{e}")

    def _sheets_push_tg(self):
        """DB → Google Sheets TG 템플릿 형식 내보내기 (범위 선택 다이얼로그)."""
        sync = self._get_sheets_sync()
        if sync is None:
            return

        # ── 범위 선택 다이얼로그 ──
        visible_ids  = self.sample_tab.get_visible_sample_ids()
        selected_ids = self.sample_tab.get_selected_sample_ids()

        dlg = QDialog(self)
        dlg.setWindowTitle("TG Template 내보내기 범위 선택")
        dlg.setMinimumWidth(320)
        layout = QVBoxLayout(dlg)

        box = QGroupBox("내보낼 샘플 범위")
        grp = QButtonGroup(dlg)
        vl  = QVBoxLayout(box)

        rb_all      = QRadioButton("전체 샘플")
        rb_visible  = QRadioButton(f"필터된 목록  ({len(visible_ids)}개)")
        rb_selected = QRadioButton(f"선택된 항목  ({len(selected_ids)}개)")

        rb_selected.setEnabled(bool(selected_ids))
        rb_all.setChecked(True)

        for rb in (rb_all, rb_visible, rb_selected):
            grp.addButton(rb)
            vl.addWidget(rb)

        layout.addWidget(box)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return

        if rb_selected.isChecked():
            sample_ids = selected_ids
        elif rb_visible.isChecked():
            sample_ids = visible_ids
        else:
            sample_ids = None  # 전체

        # ── 내보내기 실행 ──
        prog = QProgressDialog("TG 템플릿 형식으로 내보내는 중…", None, 0, 0, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.show()

        try:
            with self.db_manager.session_scope() as session:
                count = sync.push_tg_template(session, sample_ids=sample_ids)
            prog.close()
            QMessageBox.information(
                self, "TG Template Push 완료",
                f"TG_process 시트에 {count}개 샘플을 내보냈습니다.",
            )
        except Exception as e:
            prog.close()
            logger.error(f"TG template push failed: {e}")
            QMessageBox.critical(self, "Push 실패", f"오류:\n{e}")

    def _sheets_pull(self):
        """Google Sheets → DB 가져오기."""
        sync = self._get_sheets_sync()
        if sync is None:
            return

        prog = QProgressDialog("Google Sheets에서 가져오는 중…", None, 0, 0, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.show()

        try:
            with self.db_manager.session_scope() as session:
                counts = sync.pull(session)
            prog.close()
            QMessageBox.information(
                self, "Pull 완료",
                f"Google Sheets 가져오기 완료\n\n"
                f"  Samples:  신규 {counts['samples_new']} / "
                f"업데이트 {counts['samples_updated']}\n"
                f"  Metrics:  신규 {counts['metrics_new']} / "
                f"업데이트 {counts['metrics_updated']}\n"
                f"  Notes:    신규 {counts['notes_new']}",
            )
            self.sample_tab.refresh_samples()
        except Exception as e:
            prog.close()
            logger.error(f"Sheets pull failed: {e}")
            QMessageBox.critical(self, "Pull 실패", f"오류:\n{e}")

    def _export_pdf_menu(self):
        """Reports 탭으로 이동 후 PDF 내보내기 실행."""
        self.tabs.setCurrentWidget(self.reports_tab)
        self.reports_tab._export_pdf()

    def _export_excel_menu(self):
        """Reports 탭으로 이동 후 Excel 내보내기 실행."""
        self.tabs.setCurrentWidget(self.reports_tab)
        self.reports_tab._export_excel()

    def _show_help_dialog(self, tab_index: int = 0):
        """도움말 다이얼로그 열기."""
        dlg = HelpDialog(self)
        dlg.tab_widget.setCurrentIndex(tab_index)
        dlg.exec_()

    def show_about(self):
        """About 다이얼로그 표시"""
        QMessageBox.about(
            self,
            "About NGS Sample QC LIMS",
            "<h3>NGS Sample QC LIMS v1.0</h3>"
            "<p>Laboratory Information Management System for NGS Sample Quality Control</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>NanoDrop/Qubit/Femto Pulse data integration</li>"
            "<li>Automated QC judgment</li>"
            "<li>Progress tracking and visualization</li>"
            "</ul>"
            "<p>© 2026 NGS Lab</p>"
        )
    
    def closeEvent(self, event):
        """윈도우 종료 이벤트"""
        reply = QMessageBox.question(
            self,
            'Exit',
            'Are you sure you want to exit?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._save_gui_state()
            self.db_manager.close()
            event.accept()
        else:
            event.ignore()


# ── Help Dialog ────────────────────────────────────────────────────────────────

_HELP_STYLE = """
<style>
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; color: #222; margin: 12px; }
h2 { color: #1A237E; border-bottom: 2px solid #1A237E; padding-bottom: 4px; margin-top: 18px; }
h3 { color: #283593; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th { background: #1A237E; color: white; padding: 6px 10px; text-align: left; }
td { border: 1px solid #ddd; padding: 5px 10px; vertical-align: top; }
tr:nth-child(even) td { background: #F3F4F6; }
.pass  { color: #2E7D32; font-weight: bold; }
.warn  { color: #E65100; font-weight: bold; }
.fail  { color: #C62828; font-weight: bold; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold; }
.step  { background: #E8EAF6; color: #1A237E; font-weight: bold; padding: 2px 6px; border-radius: 4px; }
code   { background: #ECEFF1; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
ul li  { margin: 3px 0; }
</style>
"""

_HTML_GUIDE = _HELP_STYLE + """
<h2>NGS Sample QC LIMS — 사용법 안내</h2>

<h3>1. 샘플 등록</h3>
<ul>
  <li><b>Samples</b> 탭 → <b>New Sample</b> 버튼 (또는 <code>Ctrl+N</code>)을 클릭합니다.</li>
  <li>Sample ID, 이름, 종, 조직 유형(WGS / mRNA-seq / ChIP-seq / ATAC-seq), 프로젝트를 입력합니다.</li>
  <li>저장 후 좌측 목록에 샘플이 추가됩니다.</li>
</ul>

<h3>2. QC 데이터 입력</h3>
<ul>
  <li>샘플을 선택한 뒤 <b>Add QC Metric</b> 버튼을 클릭합니다.</li>
  <li>측정 단계(Step), 장비, 측정값(농도·부피·RIN 등)을 입력합니다.</li>
  <li>저장 시 자동으로 Pass / Warning / Fail 판정이 수행됩니다.</li>
  <li>FemtoPulse 데이터는 <b>Import FemtoPulse</b> 버튼으로 CSV/폴더를 선택해 일괄 등록합니다.</li>
</ul>

<h3>3. Femto Pulse Electropherogram 확인</h3>
<ul>
  <li>샘플 선택 → <b>Electropherogram</b> 버튼 클릭 시 그래프 다이얼로그가 열립니다.</li>
  <li>Smear Analysis 결과(범위별 % Total, 평균 크기, DQN)를 함께 표시합니다.</li>
</ul>

<h3>4. Analysis 탭 활용</h3>
<ul>
  <li>전체 배치의 QC 진행 현황, 단계별 Pass/Warning/Fail 분포, 프로젝트별 현황을 차트로 확인합니다.</li>
  <li><b>Re-judge All QC</b> 버튼으로 판정 기준 변경 후 전체 레코드를 일괄 재판정할 수 있습니다.</li>
</ul>

<h3>5. 리포트 생성</h3>
<ul>
  <li><b>Reports</b> 탭에서 샘플을 선택하고 <b>Export PDF</b> 또는 <b>Export Excel</b>을 클릭합니다.</li>
  <li>PDF는 표지 → 배치 요약 → 샘플별 QC 페이지(+ Electropherogram) 순서로 생성됩니다.</li>
  <li>메뉴 <code>Reports → Export PDF…</code> (<code>Ctrl+Shift+P</code>)로도 실행할 수 있습니다.</li>
</ul>

<h3>6. 도구 활용</h3>
<ul>
  <li><b>Revio Run Designer</b>: PacBio Revio 런 설계 (로딩량 자동 계산).</li>
  <li><b>Ladder Compare</b>: Femto Pulse Ladder 런 비교.</li>
  <li><b>Dilution Calculator</b>: Femto Pulse 로딩 희석 계산.</li>
  <li><b>Google Sheets 연동</b>: DB ↔ Google Sheets 양방향 동기화.</li>
</ul>
"""

_HTML_CRITERIA = _HELP_STYLE + """
<h2>QC 판정 기준</h2>
<p>판정은 <span class='pass'>Pass</span> → <span class='warn'>Warning</span> → <span class='fail'>Fail</span> 순서로 최악 값이 Overall 상태에 반영됩니다.</p>

<h3>WGS (Whole Genome Sequencing)</h3>
<table>
  <tr><th>측정 항목</th><th>Pass</th><th>Warning</th><th>Fail</th><th>비고</th></tr>
  <tr>
    <td>GQN (Genomic Quality Number)</td>
    <td class='pass'>≥ 7.0</td>
    <td class='warn'>5.0 – 6.9</td>
    <td class='fail'>&lt; 5.0</td>
    <td>Femto Pulse</td>
  </tr>
  <tr>
    <td>농도 (Qubit/NanoDrop)</td>
    <td colspan='3' style='text-align:center;'>판정 없음</td>
    <td>참고값만 기록</td>
  </tr>
  <tr>
    <td>Library Size</td>
    <td class='pass'>300 – 700 bp</td>
    <td colspan='2' style='text-align:center;'>범위 이탈 시 Warning</td>
    <td>Femto Pulse</td>
  </tr>
</table>

<h3>mRNA-seq</h3>
<table>
  <tr><th>측정 항목</th><th>Pass</th><th>Warning</th><th>Fail</th><th>비고</th></tr>
  <tr>
    <td>RIN (RNA Integrity Number)</td>
    <td class='pass'>≥ 8.0</td>
    <td class='warn'>6.0 – 7.9</td>
    <td class='fail'>&lt; 6.0</td>
    <td>RIN 있으면 우선 적용</td>
  </tr>
  <tr>
    <td>Total Amount (Qubit/NanoDrop)</td>
    <td class='pass'>≥ 1,000 ng (1 µg)</td>
    <td class='warn'>&lt; 1,000 ng</td>
    <td class='fail'>없음</td>
    <td>RIN 없을 때 사용</td>
  </tr>
  <tr>
    <td>순도 260/280</td>
    <td class='pass'>≥ 2.0</td>
    <td class='warn'>1.8 – 1.99</td>
    <td class='fail'>&lt; 1.8</td>
    <td>참고 표시만</td>
  </tr>
  <tr>
    <td>순도 260/230</td>
    <td class='pass'>≥ 1.8</td>
    <td class='warn'>1.5 – 1.79</td>
    <td class='fail'>&lt; 1.5</td>
    <td>참고 표시만</td>
  </tr>
</table>

<h3>ChIP-seq / ATAC-seq</h3>
<table>
  <tr><th>측정 항목</th><th>Pass</th><th>Warning</th><th>Fail</th></tr>
  <tr>
    <td>농도</td>
    <td class='pass'>기준 충족</td>
    <td class='warn'>경계값</td>
    <td class='fail'>기준 미달</td>
  </tr>
</table>
<p style='color:#666; font-size:12px;'>※ ChIP-seq / ATAC-seq 세부 기준은 샘플 유형 설정에서 확인하세요.</p>

<h3>Sequencing QC</h3>
<table>
  <tr><th>항목</th><th>Pass</th><th>Warning</th><th>Fail</th></tr>
  <tr><td>Q30 비율</td><td class='pass'>≥ 80 %</td><td class='warn'>70 – 79 %</td><td class='fail'>&lt; 70 %</td></tr>
  <tr><td>Mapping rate</td><td class='pass'>≥ 80 %</td><td class='warn'>60 – 79 %</td><td class='fail'>&lt; 60 %</td></tr>
  <tr><td>Duplication rate</td><td class='pass'>≤ 20 %</td><td class='warn'>20 – 30 %</td><td class='fail'>&gt; 30 %</td></tr>
</table>
"""

_HTML_SHORTCUTS = _HELP_STYLE + """
<h2>단축키 목록</h2>

<h3>전역 단축키</h3>
<table>
  <tr><th>단축키</th><th>기능</th></tr>
  <tr><td><code>Ctrl+N</code></td><td>새 샘플 등록</td></tr>
  <tr><td><code>Ctrl+Q</code></td><td>프로그램 종료</td></tr>
  <tr><td><code>F5</code></td><td>현재 탭 새로고침</td></tr>
</table>

<h3>탭 이동</h3>
<table>
  <tr><th>단축키</th><th>탭</th></tr>
  <tr><td><code>Ctrl+1</code></td><td>📊 Dashboard</td></tr>
  <tr><td><code>Ctrl+2</code></td><td>🧬 Samples</td></tr>
  <tr><td><code>Ctrl+3</code></td><td>📈 Analysis</td></tr>
  <tr><td><code>Ctrl+4</code></td><td>📄 Reports</td></tr>
  <tr><td><code>Ctrl+5</code></td><td>📅 Calendar</td></tr>
</table>

<h3>리포트</h3>
<table>
  <tr><th>단축키</th><th>기능</th></tr>
  <tr><td><code>Ctrl+Shift+P</code></td><td>PDF 내보내기</td></tr>
  <tr><td><code>Ctrl+Shift+E</code></td><td>Excel 내보내기</td></tr>
</table>

<h3>도움말</h3>
<table>
  <tr><th>단축키</th><th>기능</th></tr>
  <tr><td><code>F1</code></td><td>사용법 안내</td></tr>
  <tr><td><code>Ctrl+/</code></td><td>단축키 목록 (이 창)</td></tr>
</table>
"""

_HTML_TOOLS = _HELP_STYLE + """
<h2>내장 도구 설명</h2>

<h3>Revio Run Designer</h3>
<p>PacBio Revio 시퀀서의 런 파라미터를 설계합니다.</p>
<ul>
  <li>샘플별 로딩 농도·부피를 입력하면 최적 SMRTCell 배치를 계산합니다.</li>
  <li><code>Tools → Revio Run Designer…</code> 에서 실행합니다.</li>
</ul>

<h3>Compare Ladder Runs</h3>
<p>동일 Femto Pulse 장비로 측정된 여러 Ladder 런의 마이그레이션 시간 오차를 비교합니다.</p>
<ul>
  <li>런 간 시스템 오차 여부를 확인할 때 활용합니다.</li>
  <li><code>Tools → Compare Ladder Runs</code> 에서 실행합니다.</li>
</ul>

<h3>Femto Pulse Dilution Calculator</h3>
<p>Femto Pulse ScreenTape 로딩에 필요한 희석 조건을 계산합니다.</p>
<ul>
  <li>입력: 현재 농도 (ng/µL), 목표 로딩 농도, 최종 부피.</li>
  <li>출력: 샘플 부피, 희석 완충액 부피.</li>
</ul>

<h3>Re-judge All QC Status</h3>
<p>DB에 저장된 모든 QCMetric 레코드에 대해 현재 판정 기준을 재적용합니다.</p>
<ul>
  <li>판정 기준을 변경(예: mRNA-seq total amount 기준 추가)한 뒤 기존 데이터를 일괄 업데이트할 때 사용합니다.</li>
  <li><code>Tools → Re-judge All QC Status</code> 또는 Analysis 탭의 <b>Re-judge All QC</b> 버튼.</li>
</ul>

<h3>Import Sequencing QC</h3>
<p>시퀀싱 완료 후 Q30, Mapping Rate, Duplication Rate 등의 결과를 DB에 등록합니다.</p>
<ul>
  <li>샘플 선택 후 <code>Tools → Import Sequencing QC…</code> 에서 파일을 불러옵니다.</li>
</ul>

<h3>Migrate FemtoPulse Files to Local</h3>
<p>기존 DB에 절대 경로로 저장된 FemtoPulse 파일을 로컬 <code>data/femtopulse_images/</code> 폴더로 복사하고 상대 경로로 업데이트합니다.</p>
<ul>
  <li>다른 PC로 DB를 이식할 때 실행하면 Electropherogram 그래프가 정상 표시됩니다.</li>
</ul>

<h3>Google Sheets 연동</h3>
<p>Google Service Account를 이용해 샘플·QC 데이터를 Google Sheets와 양방향으로 동기화합니다.</p>
<ul>
  <li><b>Configure</b>: Service Account JSON 파일과 Spreadsheet ID를 설정합니다.</li>
  <li><b>Push (DB → 시트)</b>: DB 데이터를 시트로 내보냅니다.</li>
  <li><b>Pull (시트 → DB)</b>: 시트 변경사항을 DB에 반영합니다.</li>
  <li><b>Push TG Template</b>: TG_process 시트 형식으로 샘플 정보를 내보냅니다.</li>
</ul>
"""


class HelpDialog(QDialog):
    """사용법·QC 기준·단축키·도구 설명을 탭으로 제공하는 도움말 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("NGS Sample QC LIMS — 도움말")
        self.setMinimumSize(720, 540)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tab_widget = self._build_tabs()
        layout.addWidget(self.tab_widget)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _build_tabs(self):
        tabs = QTabWidget()
        for title, html in [
            ("사용법 안내",   _HTML_GUIDE),
            ("QC 판정 기준", _HTML_CRITERIA),
            ("단축키 목록",  _HTML_SHORTCUTS),
            ("도구 설명",    _HTML_TOOLS),
        ]:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setHtml(html)
            tabs.addTab(browser, title)
        return tabs
