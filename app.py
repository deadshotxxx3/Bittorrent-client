import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from gui.theme import STYLESHEET


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("BitClient")
    font = QFont()
    font.setFamilies(["Inter", "Segoe UI", "Ubuntu", "Noto Sans", "Helvetica Neue", "Arial"])
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(initial=sys.argv[1:])
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
