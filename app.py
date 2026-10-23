import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui import theme
from gui.fonts import load_fonts
from gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("BitClient")
    app.setFont(load_fonts())
    name = QSettings("deadshot", "BitClient").value("theme", "dark")
    app.setStyleSheet(theme.set_theme(name))
    window = MainWindow(initial=sys.argv[1:])
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
