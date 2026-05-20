"""
NGS Sample QC LIMS - Main Entry Point
"""
import sys
import logging
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from config.settings import LOG_LEVEL, LOG_FORMAT, LOG_FILE
from ui.main_window import MainWindow
from ui.app_icon import make_app_icon


def setup_logging():
    """로깅 설정"""
    # 로그 디렉토리 생성
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # 로깅 설정
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("NGS Sample QC LIMS Started")
    logger.info("=" * 60)


def main():
    """메인 함수"""
    # 로깅 설정
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # PyQt 애플리케이션 생성
        app = QApplication(sys.argv)
        app.setApplicationName("NGS Sample QC LIMS")
        app.setOrganizationName("NGS Lab")
        app.setWindowIcon(make_app_icon())
        
        # High DPI 지원 (PyQt5)
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
        # ── Global UI stylesheet ──────────────────────────────────────────
        app.setStyleSheet("""

            /* ── Menu bar ── */
            QMenuBar {
                background: #FFFFFF;
                border-bottom: 1px solid #DEE2E6;
                font-size: 11pt;
                spacing: 2px;
            }
            QMenuBar::item {
                padding: 6px 12px;
                background: transparent;
                border-radius: 3px;
            }
            QMenuBar::item:selected {
                background: #E8F0FE;
                color: #1A73E8;
            }
            QMenu {
                background: #FFFFFF;
                border: 1px solid #DEE2E6;
                border-radius: 4px;
                font-size: 11pt;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 32px 6px 24px;
            }
            QMenu::item:selected {
                background: #E8F0FE;
                color: #1A73E8;
            }
            QMenu::separator {
                height: 1px;
                background: #DEE2E6;
                margin: 4px 10px;
            }

            /* ── Tab bar ── */
            QTabWidget::pane {
                border: none;
                border-top: 1px solid #DEE2E6;
                background: #FFFFFF;
            }
            QTabBar {
                font-size: 10pt;
            }
            QTabBar::tab {
                font-size: 10pt;
                padding: 12px 24px;
                background: #F1F3F4;
                color: #5F6368;
                border: none;
                border-bottom: 3px solid transparent;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #1A73E8;
                border-bottom: 3px solid #1A73E8;
            }
            QTabBar::tab:!selected:hover {
                background: #E8F0FE;
                color: #1A73E8;
            }

            /* ── Push buttons ── */
            QPushButton {
                font-size: 9pt;
                padding: 4px 14px;
                min-height: 24px;
                background: #FFFFFF;
                border: 1px solid #DADCE0;
                border-radius: 4px;
                color: #3C4043;
            }
            QPushButton:hover {
                background: #F1F3F4;
                border-color: #1A73E8;
                color: #1A73E8;
            }
            QPushButton:pressed {
                background: #E8F0FE;
            }
            QPushButton:disabled {
                color: #BDBDBD;
                border-color: #E8EAED;
                background: #F8F9FA;
            }

            /* ── Tables ── */
            QTableWidget, QTableView {
                background: #FFFFFF;
                alternate-background-color: #F8F9FA;
                gridline-color: #E8EAED;
                border: 1px solid #DEE2E6;
                selection-background-color: #E8F0FE;
                selection-color: #1A73E8;
                font-size: 9pt;
            }
            QHeaderView::section {
                background: #1A237E;
                color: #FFFFFF;
                font-size: 9pt;
                font-weight: bold;
                padding: 6px 8px;
                border: none;
                border-right: 1px solid #283593;
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QHeaderView::section:vertical {
                background: #F1F3F4;
                color: #5F6368;
                font-weight: normal;
                border-right: 1px solid #DEE2E6;
                border-bottom: 1px solid #E8EAED;
            }

            /* ── Input fields ── */
            QLineEdit {
                font-size: 9pt;
                padding: 4px 8px;
                border: 1px solid #DADCE0;
                border-radius: 4px;
                background: #FFFFFF;
                min-height: 24px;
                selection-background-color: #E8F0FE;
            }
            QLineEdit:focus {
                border-color: #1A73E8;
            }
            QSpinBox, QDoubleSpinBox {
                font-size: 9pt;
                padding: 3px 6px;
                border: 1px solid #DADCE0;
                border-radius: 4px;
                background: #FFFFFF;
                min-height: 24px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #1A73E8;
            }
            QComboBox {
                font-size: 9pt;
                padding: 3px 8px;
                border: 1px solid #DADCE0;
                border-radius: 4px;
                background: #FFFFFF;
                min-height: 24px;
            }
            QComboBox:focus {
                border-color: #1A73E8;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #DADCE0;
                selection-background-color: #E8F0FE;
                selection-color: #1A73E8;
                font-size: 9pt;
            }

            /* ── Labels ── */
            QLabel {
                font-size: 9pt;
                color: #3C4043;
            }

            /* ── Group box ── */
            QGroupBox {
                font-size: 9pt;
                font-weight: bold;
                border: 1px solid #DEE2E6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 4px;
                color: #1A73E8;
            }

            /* ── Check box ── */
            QCheckBox {
                font-size: 9pt;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #DADCE0;
                border-radius: 2px;
                background: #FFFFFF;
            }
            QCheckBox::indicator:checked {
                background: #1A73E8;
                border-color: #1A73E8;
            }

            /* ── Scroll bars ── */
            QScrollBar:vertical {
                background: #F1F3F4;
                width: 10px;
                margin: 0;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #BDBDBD;
                border-radius: 5px;
                min-height: 24px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #1A73E8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: #F1F3F4;
                height: 10px;
                margin: 0;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background: #BDBDBD;
                border-radius: 5px;
                min-width: 24px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #1A73E8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }

            /* ── Splitter ── */
            QSplitter::handle:horizontal {
                background: #DEE2E6;
                width: 1px;
            }
            QSplitter::handle:vertical {
                background: #DEE2E6;
                height: 1px;
            }

            /* ── Status bar ── */
            QStatusBar {
                background: #F1F3F4;
                border-top: 1px solid #DEE2E6;
                font-size: 9pt;
                color: #5F6368;
                padding: 2px 8px;
            }

        """)

        # 메인 윈도우 생성 및 표시
        window = MainWindow()
        window.show()
        
        logger.info("Application started successfully")
        
        # 이벤트 루프 실행
        sys.exit(app.exec())
        
    except Exception as e:
        logger.critical(f"Application crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
