"""
메인 윈도우 - NGS Sample QC LIMS
"""
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTabWidget, QMenuBar, QMenu, QStatusBar, QMessageBox,
    QToolBar, QLabel, QAction
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon
import logging

from config.settings import WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT
from database import db_manager
from ui.sample_tab import SampleTab
from ui.dashboard_tab import DashboardTab

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
        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout()
        analysis_layout.addWidget(QLabel("QC Analysis - Coming Soon"))
        analysis_tab.setLayout(analysis_layout)
        self.tabs.addTab(analysis_tab, "📈 Analysis")
        
        # Reports 탭
        reports_tab = QWidget()
        reports_layout = QVBoxLayout()
        reports_layout.addWidget(QLabel("Reports - Coming Soon"))
        reports_tab.setLayout(reports_layout)
        self.tabs.addTab(reports_tab, "📄 Reports")
    
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
        
        molarity_calc_action = QAction('&Molarity Calculator', self)
        molarity_calc_action.triggered.connect(self.open_molarity_calculator)
        tools_menu.addAction(molarity_calc_action)
        
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
    
    def _on_tab_changed(self, index: int):
        """탭 전환 시 Dashboard 자동 새로고침."""
        if self.tabs.widget(index) is self.dashboard_tab:
            self.dashboard_tab.refresh()

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
    
    def open_molarity_calculator(self):
        """Molarity 계산기 열기"""
        # TODO: Molarity 계산기 다이얼로그 구현
        self.statusBar().showMessage('Molarity Calculator - Not implemented yet')
    
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
            "<li>Molarity calculation</li>"
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
            # 데이터베이스 연결 종료
            self.db_manager.close()
            event.accept()
        else:
            event.ignore()
