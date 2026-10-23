import time
from collections import deque

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget

from gui import theme

PROGRESS_ROLE = Qt.UserRole + 1


class SpeedGraph(QWidget):
    POINTS = 61

    def __init__(self, parent=None):
        super().__init__(parent)
        self.down = deque([0] * self.POINTS, maxlen=self.POINTS)
        self.up = deque([0] * self.POINTS, maxlen=self.POINTS)
        self.shift = 0.0
        self.peak = 256 * 1024
        self.setMinimumHeight(86)
        self.slide = QVariantAnimation(self)
        self.slide.setDuration(1000)
        self.slide.setStartValue(1.0)
        self.slide.setEndValue(0.0)
        self.slide.setEasingCurve(QEasingCurve.Linear)
        self.slide.valueChanged.connect(self.on_slide)

    def on_slide(self, value) -> None:
        self.shift = float(value)
        target = max(max(self.down), max(self.up), 256 * 1024)
        self.peak += (target - self.peak) * 0.08
        self.update()

    def push(self, down: float, up: float) -> None:
        self.down.append(down)
        self.up.append(up)
        self.slide.stop()
        self.slide.start()

    def _points(self, values, rect):
        step = rect.width() / (self.POINTS - 2)
        peak = max(self.peak, 1.0)
        return [
            (rect.left() + (i - 1 + self.shift) * step, rect.bottom() - (v / peak) * rect.height())
            for i, v in enumerate(values)
        ]

    @staticmethod
    def _smooth(points):
        path = QPainterPath()
        path.moveTo(*points[0])
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            mid = (x0 + x1) / 2
            path.cubicTo(mid, y0, mid, y1, x1, y1)
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 6, -2, -4)
        painter.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
        for i in range(1, 4):
            y = rect.top() + rect.height() * i / 4
            painter.drawLine(rect.left(), y, rect.right(), y)
        painter.setClipRect(rect.adjusted(0, -6, 0, 4))
        for values, color in ((self.up, theme.ACCENT), (self.down, theme.ACCENT_2)):
            points = self._points(values, rect)
            line = self._smooth(points)
            fill = QPainterPath(line)
            fill.lineTo(points[-1][0], rect.bottom())
            fill.lineTo(points[0][0], rect.bottom())
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
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.targets = {}
        self.shown = {}
        self.busy = False
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def tick(self) -> None:
        moving = False
        for key, target in self.targets.items():
            current = self.shown.get(key, target)
            if abs(target - current) > 0.0004:
                self.shown[key] = current + (target - current) * 0.22
                moving = True
            else:
                self.shown[key] = target
        if moving or self.busy:
            self.busy = False
            self.view.viewport().update()

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
        progress = max(0.0, min(1.0, info.progress))
        self.targets[info.key] = progress
        shown = self.shown.setdefault(info.key, progress)
        track = QRectF(option.rect).adjusted(10, 0, -14, 0)
        track.setTop(option.rect.center().y() - 7)
        track.setHeight(14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.SURFACE_3))
        painter.drawRoundedRect(track, 7, 7)
        if shown > 0:
            fill = QRectF(track)
            fill.setWidth(max(track.width() * shown, 14))
            color = QColor(theme.STATE_COLORS.get(info.state, theme.ACCENT))
            if info.state == "downloading":
                gradient = QLinearGradient(fill.left(), 0, fill.right(), 0)
                gradient.setColorAt(0, QColor(theme.ACCENT))
                gradient.setColorAt(1, QColor(theme.ACCENT_2))
                painter.setBrush(gradient)
            else:
                painter.setBrush(color)
            painter.drawRoundedRect(fill, 7, 7)
            if info.state == "downloading" and not info.paused:
                self.busy = True
                clip = QPainterPath()
                clip.addRoundedRect(fill, 7, 7)
                painter.setClipPath(clip)
                phase = (time.monotonic() * 0.8) % 1.0
                band = 70.0
                x = fill.left() - band + phase * (fill.width() + band * 2)
                shine = QLinearGradient(x, 0, x + band, 0)
                transparent = QColor(255, 255, 255, 0)
                shine.setColorAt(0, transparent)
                shine.setColorAt(0.5, QColor(255, 255, 255, 85))
                shine.setColorAt(1, transparent)
                painter.setBrush(shine)
                painter.drawRect(QRectF(x, fill.top(), band, fill.height()))
                painter.setClipping(False)
        font = painter.font()
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff") if shown > 0.5 else QColor(theme.TEXT))
        painter.drawText(track, Qt.AlignCenter, f"{progress * 100:.1f}%")
        painter.restore()
