import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.logs import setup_logging
from gui import theme
from gui.fonts import load_fonts
from gui.icons import app_icon
from gui.main_window import MainWindow
from gui.single import InstanceServer, forward_to_running


def main() -> None:
    setup_logging(Path.home() / ".bitclient" / "log.txt")
    arguments = sys.argv[1:]
    minimized = "--minimized" in arguments
    arguments = [a for a in arguments if not a.startswith("--")]
    app = QApplication(sys.argv)
    if forward_to_running(arguments):
        return
    server = InstanceServer()
    server.listen()
    app.setStyle("Fusion")
    app.setApplicationName("BitClient")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    app.setFont(load_fonts())
    name = QSettings("deadshot", "BitClient").value("theme", "dark")
    app.setStyleSheet(theme.set_theme(name))
    window = MainWindow(initial=arguments)
    server.received.connect(window.handle_arguments)
    if not (minimized and window.tray is not None):
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
