"""
앱 아이콘 생성 — QPainter로 DNA 헬릭스를 그려 QIcon 반환.
외부 이미지 파일 없이 동작.
"""
import math

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (
    QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)


def make_app_icon(size: int = 64) -> QIcon:
    """DNA 헬릭스 아이콘 QIcon 생성."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # ── 배경: 파란 계열 그라디언트 둥근 사각형 ──────────────────────
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, QColor("#1976D2"))
    grad.setColorAt(1.0, QColor("#0D47A1"))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    r = size * 0.18          # corner radius
    p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), r, r)

    # ── DNA 헬릭스: 두 개의 사인파 ──────────────────────────────────
    margin = size * 0.14
    cx_start = margin
    cx_end   = size - margin
    cy       = size / 2.0
    amp      = size * 0.22    # 진폭
    steps    = 120

    def helix_point(t: float, phase: float) -> QPointF:
        x = cx_start + (cx_end - cx_start) * t
        y = cy + amp * math.sin(phase + t * math.pi * 2)
        return QPointF(x, y)

    for phase in (0.0, math.pi):
        path = QPainterPath()
        for i in range(steps + 1):
            pt = helix_point(i / steps, phase)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        pen = QPen(QColor(255, 255, 255, 230), size * 0.055,
                   Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)

    # ── 가로 결합선 (rungs) ──────────────────────────────────────────
    rung_pen = QPen(QColor(255, 255, 255, 130), size * 0.035,
                    Qt.SolidLine, Qt.RoundCap)
    p.setPen(rung_pen)
    n_rungs = 5
    for i in range(n_rungs):
        t = i / (n_rungs - 1)
        pt0 = helix_point(t, 0.0)
        pt1 = helix_point(t, math.pi)
        p.drawLine(pt0, pt1)

    p.end()

    # 여러 크기 포함 (16 / 32 / 48 / 64)
    icon = QIcon()
    for s in (16, 32, 48, 64):
        icon.addPixmap(pix.scaled(s, s, Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation))
    return icon
