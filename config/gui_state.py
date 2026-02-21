"""
GUI 상태 저장/복원 유틸리티
QSettings(IniFormat)를 사용하여 config/gui_state.ini에 저장
"""
from PyQt5.QtCore import QSettings, QByteArray
from PyQt5.QtWidgets import QTableWidget, QSplitter, QComboBox

from config.settings import BASE_DIR

_SETTINGS_FILE = str(BASE_DIR / "config" / "gui_state.ini")


def get_settings() -> QSettings:
    """앱 전역 QSettings 인스턴스 반환."""
    return QSettings(_SETTINGS_FILE, QSettings.IniFormat)


def save_table_widths(settings: QSettings, key: str, table: QTableWidget):
    """QTableWidget 각 컬럼 너비 저장."""
    widths = [table.columnWidth(i) for i in range(table.columnCount())]
    settings.setValue(key, widths)


def restore_table_widths(settings: QSettings, key: str, table: QTableWidget):
    """저장된 컬럼 너비 복원. 컬럼 수가 달라도 안전하게 처리."""
    widths = settings.value(key)
    if not widths:
        return
    for i, w in enumerate(widths):
        try:
            w_int = int(w)
            if i < table.columnCount() and w_int > 0:
                table.setColumnWidth(i, w_int)
        except (ValueError, TypeError):
            pass


def save_splitter(settings: QSettings, key: str, splitter: QSplitter):
    """QSplitter 상태 저장."""
    settings.setValue(key, splitter.saveState())


def restore_splitter(settings: QSettings, key: str, splitter: QSplitter):
    """저장된 QSplitter 상태 복원."""
    state = settings.value(key)
    if isinstance(state, QByteArray) and not state.isEmpty():
        splitter.restoreState(state)


def save_combo(settings: QSettings, key: str, combo: QComboBox):
    """QComboBox 현재 텍스트 저장 (인덱스 대신 텍스트로 저장해 순서 변경에 강건)."""
    settings.setValue(key, combo.currentText())


def restore_combo(settings: QSettings, key: str, combo: QComboBox):
    """저장된 텍스트로 QComboBox 복원. 없으면 변경 안 함."""
    text = settings.value(key)
    if text:
        idx = combo.findText(str(text))
        if idx >= 0:
            combo.setCurrentIndex(idx)
