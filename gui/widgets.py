from collections import deque

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget

from gui import theme

PROGRESS_ROLE = Qt.UserRole + 1


class SpeedGraph(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.down = deque([0] * 60, maxlen=60)
        self.up = deque([0] * 60, maxlen=60)
        self.setMinimumHeight(86)

    def push(self, down: float, up: float) -> None:
        self.down.append(down)
        self.up.append(up)
        self.update()

    def _line(self, values, peak, rect):
        path = QPainterPath()
        step = rect.width() / (len(values) - 1)
        for i, value in enumerate(values):
            x = rect.left() + i * step
            y = rect.bottom() - (value / peak) * rect.height()
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 6, -2, -4)
        peak = max(max(self.down), max(self.up), 256 * 1024)
        painter.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
        for i in range(1, 4):
            y = rect.top() + rect.height() * i / 4
            painter.drawLine(rect.left(), y, rect.right(), y)
        for values, color in ((self.up, theme.ACCENT), (self.down, theme.ACCENT_2)):
            line = self._line(values, peak, rect)
            fill = QPainterPath(line)
            fill.lineTo(rect.right(), rect.bottom())
            fill.lineTo(rect.left(), rect.bottom())
            fill.closeSubpath()
            top = QColor(color)
            top.setAlpha(95)
            bottom = QColor(color)
            bottom.setAlpha(0)
            gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
            gradient.setColorAt(0, top)
            gradient.setColorAt(1, bottom)
            painter.fillPath(fill, gradient)
            painter.setPen(QPen(QColor(color), 1.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(line)


class StatCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("cardValue")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        info = index.data(PROGRESS_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(124, 140, 255, 36))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(128, 128, 128, 28))
        if info is None:
            painter.restore()
            return
        track = QRectF(option.rect).adjusted(10, 0, -14, 0)
        track.setTop(option.rect.center().y() - 7)
        track.setHeight(14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.SURFACE_3))
        painter.drawRoundedRect(track, 7, 7)
        progress = max(0.0, min(1.0, info.progress))
        if progress > 0:
            fill = QRectF(track)
            fill.setWidth(max(track.width() * progress, 14))
            color = QColor(theme.STATE_COLORS.get(info.state, theme.ACCENT))
            if info.state == "downloading":
                gradient = QLinearGradient(fill.left(), 0, fill.right(), 0)
                gradient.setColorAt(0, QColor(theme.ACCENT))
                gradient.setColorAt(1, QColor(theme.ACCENT_2))
                painter.setBrush(gradient)
            else:
                painter.setBrush(color)
            painter.drawRoundedRect(fill, 7, 7)
        font = painter.font()
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff") if progress > 0.5 else QColor(theme.TEXT))
        painter.drawText(track, Qt.AlignCenter, f"{progress * 100:.1f}%")
        painter.restore()
