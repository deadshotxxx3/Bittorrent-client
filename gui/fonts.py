import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

FALLBACKS = ["Segoe UI", "Ubuntu", "Noto Sans", "Helvetica Neue", "Arial"]


def load_fonts() -> QFont:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    folder = base / "assets" / "fonts"
    families = []
    for file in sorted(folder.glob("*.ttf")):
        index = QFontDatabase.addApplicationFont(str(file))
        if index >= 0:
            for name in QFontDatabase.applicationFontFamilies(index):
                if name not in families:
                    families.append(name)
    primary = "Inter" if "Inter" in families else (families[0] if families else "Inter")
    font = QFont()
    font.setFamilies([primary] + FALLBACKS)
    font.setPointSize(10)
    font.setHintingPreference(QFont.PreferNoHinting)
    font.setStyleStrategy(QFont.PreferAntialias)
    return font
