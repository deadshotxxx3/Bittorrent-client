from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPropertyAnimation, Qt, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QLabel, QPushButton,
)

from gui import theme


def fade_in(widget, duration: int = 220, start: float = 0.0) -> None:
    previous = getattr(widget, "_fade_animation", None)
    if previous is not None:
        try:
            previous.stop()
        except RuntimeError:
            pass
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)

    def finish():
        if getattr(widget, "_fade_animation", None) is animation:
            widget.setGraphicsEffect(None)

    animation.finished.connect(finish)
    widget._fade_animation = animation
    animation.start()


def pulse(widget, low: float = 0.4, duration: int = 2400) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setKeyValueAt(0.0, 1.0)
    animation.setKeyValueAt(0.5, low)
    animation.setKeyValueAt(1.0, 1.0)
    animation.setEasingCurve(QEasingCurve.InOutSine)
    animation.setLoopCount(-1)
    animation.start()


def crossfade(window, apply, duration: int = 420) -> None:
    pixmap = window.grab()
    apply()
    overlay = QLabel(window)
    overlay.setPixmap(pixmap)
    overlay.setGeometry(window.rect())
    overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
    effect = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(effect)
    overlay.show()
    overlay.raise_()
    animation = QPropertyAnimation(effect, b"opacity", overlay)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setEndValue(0.0)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.finished.connect(overlay.deleteLater)
    animation.start()


def window_fade(window, duration: int = 380) -> None:
    window.setWindowOpacity(0.0)
    animation = QPropertyAnimation(window, b"windowOpacity", window)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.OutCubic)
    window._window_fade = animation
    animation.start()


class FadeDialog(QDialog):
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            window_fade(self, 200)


class GlowButton(QPushButton):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.effect = QGraphicsDropShadowEffect(self)
        self.effect.setOffset(0, 4)
        self.effect.setBlurRadius(0)
        self.effect.setColor(QColor(0, 0, 0, 0))
        self.setGraphicsEffect(self.effect)
        self.glow = QVariantAnimation(self)
        self.glow.setDuration(220)
        self.glow.setEasingCurve(QEasingCurve.OutCubic)
        self.glow.valueChanged.connect(self.apply_glow)
        self.level = 0.0

    def apply_glow(self, value) -> None:
        self.level = float(value)
        color = QColor(theme.ACCENT)
        color.setAlpha(int(140 * self.level))
        self.effect.setColor(color)
        self.effect.setBlurRadius(28 * self.level)

    def animate_to(self, target: float) -> None:
        self.glow.stop()
        self.glow.setStartValue(self.level)
        self.glow.setEndValue(target)
        self.glow.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isEnabled():
            self.animate_to(1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.animate_to(0.0)
