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
        
        # High DPI 지원 (PyQt5)
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
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
