"""
메인 윈도우 - NGS Sample QC LIMS
"""
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QMenuBar, QMenu, QStatusBar, QMessageBox,
    QToolBar, QLabel, QAction, QProgressDialog,
    QDialog, QDialogButtonBox, QRadioButton, QButtonGroup, QGroupBox,
)
from PyQt5.QtCore import Qt, QSize
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
        
        # 툴바 생성
        self._create_toolbar()
        
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
        
        about_action = QAction('&About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def _create_toolbar(self):
        """툴바 생성"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # 새 샘플
        new_sample_action = QAction("New Sample", self)
        new_sample_action.triggered.connect(self.new_sample)
        toolbar.addAction(new_sample_action)
        
        toolbar.addSeparator()
        
        # 새로고침
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh_data)
        toolbar.addAction(refresh_action)
    
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
