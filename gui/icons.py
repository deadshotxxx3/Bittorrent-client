from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def build_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, QColor("#7c8cff"))
    gradient.setColorAt(1, QColor("#22d3ee"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(rect, size * 0.24, size * 0.24)
    pen = QPen(QColor("#0b0d14"), size * 0.095, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    cx = size / 2
    painter.drawLine(QPointF(cx, size * 0.26), QPointF(cx, size * 0.62))
    arrow = QPainterPath()
    arrow.moveTo(size * 0.33, size * 0.47)
    arrow.lineTo(cx, size * 0.65)
    arrow.lineTo(size * 0.67, size * 0.47)
    painter.drawPath(arrow)
    painter.drawLine(QPointF(size * 0.3, size * 0.77), QPointF(size * 0.7, size * 0.77))
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(build_pixmap(size))
    return icon
