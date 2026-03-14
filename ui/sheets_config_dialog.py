"""
Google Sheets 연동 설정 다이얼로그

Service Account JSON 경로, Spreadsheet ID, 시트 이름을 설정하고
연결 테스트를 수행한다.
"""
import re
import logging

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox,
    QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl

from config.settings import get_gsheets_config, save_gsheets_config

logger = logging.getLogger(__name__)

_GUIDE_URL = (
    "https://docs.gspread.org/en/latest/oauth2.html"
    "#for-bots-using-service-account"
)


class SheetsConfigDialog(QDialog):
    """Google Sheets 연동 설정 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Google Sheets 연동 설정")
        self.setMinimumWidth(520)
        self._build_ui()
        self._load_config()

    # ── UI 구성 ──────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Service Account 자격증명 ──
        cred_box = QGroupBox("Service Account 자격증명 (JSON)")
        cg = QGridLayout(cred_box)

        self._cred_edit = QLineEdit()
        self._cred_edit.setPlaceholderText("service_account.json 파일 경로")
        cg.addWidget(QLabel("파일 경로:"), 0, 0)
        cg.addWidget(self._cred_edit, 0, 1)

        btn_browse = QPushButton("Browse...")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_cred)
        cg.addWidget(btn_browse, 0, 2)

        guide_lbl = QLabel(
            '<a href="#">Service Account 설정 가이드 (gspread 공식 문서)</a>'
        )
        guide_lbl.setTextFormat(Qt.RichText)
        guide_lbl.linkActivated.connect(
            lambda: QDesktopServices.openUrl(QUrl(_GUIDE_URL))
        )
        guide_lbl.setStyleSheet("color: #1565C0; font-size: 11px;")
        cg.addWidget(guide_lbl, 1, 0, 1, 3)

        cg.setColumnStretch(1, 1)
        layout.addWidget(cred_box)

        # ── Spreadsheet 설정 ──
        ss_box = QGroupBox("Spreadsheet")
        sg = QGridLayout(ss_box)

        self._sid_edit = QLineEdit()
        self._sid_edit.setPlaceholderText(
            "Spreadsheet ID 또는 URL "
            "(예: https://docs.google.com/spreadsheets/d/1ABC…/edit)"
        )
        sg.addWidget(QLabel("ID / URL:"), 0, 0)
        sg.addWidget(self._sid_edit, 0, 1)
        sg.setColumnStretch(1, 1)
        layout.addWidget(ss_box)

        # ── 시트 이름 설정 ──
        name_box = QGroupBox("시트 이름 (기존 템플릿 헤더에 맞게 조정 가능)")
        ng = QGridLayout(name_box)

        ng.addWidget(QLabel("Samples 시트:"), 0, 0)
        self._sh_samples = QLineEdit("Samples")
        ng.addWidget(self._sh_samples, 0, 1)

        ng.addWidget(QLabel("QC Metrics 시트:"), 1, 0)
        self._sh_metrics = QLineEdit("QC_Metrics")
        ng.addWidget(self._sh_metrics, 1, 1)

        ng.addWidget(QLabel("Notes 시트:"), 2, 0)
        self._sh_notes = QLineEdit("Notes")
        ng.addWidget(self._sh_notes, 2, 1)

        ng.addWidget(QLabel("TG Process 시트:"), 3, 0)
        self._sh_tg = QLineEdit("TG_process")
        ng.addWidget(self._sh_tg, 3, 1)

        ng.setColumnStretch(1, 1)
        layout.addWidget(name_box)

        # ── 연결 테스트 ──
        test_row = QHBoxLayout()
        btn_test = QPushButton("Test Connection")
        btn_test.clicked.connect(self._test_connection)
        self._test_lbl = QLabel("")
        self._test_lbl.setWordWrap(True)
        test_row.addWidget(btn_test)
        test_row.addWidget(self._test_lbl, 1)
        layout.addLayout(test_row)

        # ── OK / Cancel ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._save_and_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    # ── 로드 / 저장 ──────────────────────────────────────────────────

    def _load_config(self):
        cfg = get_gsheets_config()
        self._cred_edit.setText(cfg.get("credentials_path", ""))
        self._sid_edit.setText(cfg.get("spreadsheet_id", ""))
        names = cfg.get("sheet_names", {})
        self._sh_samples.setText(names.get("samples", "Samples"))
        self._sh_metrics.setText(names.get("qc_metrics", "QC_Metrics"))
        self._sh_notes.setText(names.get("notes", "Notes"))
        self._sh_tg.setText(names.get("tg_process", "TG_process"))

    def _save_and_accept(self):
        save_gsheets_config(
            credentials_path=self._cred_edit.text().strip(),
            spreadsheet_id=self._extract_id(self._sid_edit.text().strip()),
            sheet_names={
                "samples":    self._sh_samples.text().strip() or "Samples",
                "qc_metrics": self._sh_metrics.text().strip() or "QC_Metrics",
                "notes":      self._sh_notes.text().strip() or "Notes",
                "tg_process": self._sh_tg.text().strip() or "TG_process",
            },
        )
        self.accept()

    # ── 헬퍼 ─────────────────────────────────────────────────────────

    def _browse_cred(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Service Account JSON 선택", "",
            "JSON 파일 (*.json)"
        )
        if path:
            self._cred_edit.setText(path)

    @staticmethod
    def _extract_id(text: str) -> str:
        """URL이면 /d/{ID}/ 부분 추출, 아니면 그대로 반환."""
        m = re.search(r"/d/([a-zA-Z0-9_-]+)", text)
        return m.group(1) if m else text

    def _test_connection(self):
        from integration.google_sheets import GSheetSync

        cred = self._cred_edit.text().strip()
        sid  = self._extract_id(self._sid_edit.text().strip())

        if not cred or not sid:
            self._test_lbl.setStyleSheet("color: #b71c1c;")
            self._test_lbl.setText("자격증명 파일과 Spreadsheet ID를 먼저 입력하세요.")
            return

        self._test_lbl.setStyleSheet("color: #555;")
        self._test_lbl.setText("연결 중…")

        sheet_names = {
            "samples":    self._sh_samples.text().strip() or "Samples",
            "qc_metrics": self._sh_metrics.text().strip() or "QC_Metrics",
            "notes":      self._sh_notes.text().strip() or "Notes",
            "tg_process": self._sh_tg.text().strip() or "TG_process",
        }

        try:
            sync = GSheetSync(cred, sid, sheet_names)
            ok, msg = sync.test_connection()
            color = "#1b5e20" if ok else "#b71c1c"
            self._test_lbl.setStyleSheet(f"color: {color};")
            self._test_lbl.setText(msg)
        except ImportError:
            self._test_lbl.setStyleSheet("color: #b71c1c;")
            self._test_lbl.setText(
                "gspread 패키지가 설치되지 않았습니다. "
                "pip install gspread google-auth 를 실행하세요."
            )
        except Exception as e:
            self._test_lbl.setStyleSheet("color: #b71c1c;")
            self._test_lbl.setText(f"오류: {e}")
