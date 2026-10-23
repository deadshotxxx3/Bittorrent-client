PALETTES = {
    "dark": {
        "BG": "#0e1017", "SURFACE": "#151824", "SURFACE_2": "#1c2030", "SURFACE_3": "#252a3d",
        "BORDER": "#2a3047", "TEXT": "#e8ebf5", "MUTED": "#8b93ab", "ACCENT": "#7c8cff",
        "ACCENT_2": "#22d3ee", "GREEN": "#34d399", "ORANGE": "#fbbf24", "RED": "#f87171",
        "GREY": "#6b7390", "ON_ACCENT": "#0b0d14",
    },
    "light": {
        "BG": "#f3f5fb", "SURFACE": "#ffffff", "SURFACE_2": "#eef1f9", "SURFACE_3": "#dde3f1",
        "BORDER": "#d3d9ea", "TEXT": "#1a2033", "MUTED": "#68718e", "ACCENT": "#5865f2",
        "ACCENT_2": "#0891b2", "GREEN": "#059669", "ORANGE": "#d97706", "RED": "#dc2626",
        "GREY": "#8a92a8", "ON_ACCENT": "#ffffff",
    },
}

BG = SURFACE = SURFACE_2 = SURFACE_3 = BORDER = TEXT = MUTED = ""
ACCENT = ACCENT_2 = GREEN = ORANGE = RED = GREY = ON_ACCENT = ""
STATE_COLORS = {}

STATE_TITLES = {
    "downloading": "Загрузка",
    "metadata": "Метаданные",
    "checking": "Проверка",
    "completed": "Завершён",
    "seeding": "Раздача",
    "paused": "Пауза",
    "queued": "В очереди",
    "error": "Ошибка",
}


def set_theme(name: str) -> str:
    global STATE_COLORS
    if name not in PALETTES:
        name = "dark"
    globals().update(PALETTES[name])
    STATE_COLORS = {
        "downloading": ACCENT,
        "metadata": ORANGE,
        "checking": ORANGE,
        "completed": GREEN,
        "seeding": GREEN,
        "paused": GREY,
        "queued": GREY,
        "error": RED,
    }
    return build_stylesheet()


def build_stylesheet() -> str:
    return f"""
* {{
    outline: none;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QWidget {{
    color: {TEXT};
    font-family: "Inter", "Segoe UI", "Ubuntu", "Noto Sans", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}
QToolTip {{
    background: {SURFACE_3};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px 8px;
    border-radius: 6px;
}}
#sidebar {{
    background: {SURFACE};
    border-right: 1px solid {BORDER};
}}
#logo {{
    font-size: 22px;
    font-weight: 800;
    color: {TEXT};
    letter-spacing: 0.5px;
}}
#logoSub {{
    color: {MUTED};
    font-size: 11px;
}}
#sectionLabel {{
    color: {MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.4px;
}}
QPushButton#navButton {{
    text-align: left;
    padding: 10px 14px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: {MUTED};
    font-weight: 600;
}}
QPushButton#navButton:hover {{
    background: {SURFACE_2};
    color: {TEXT};
}}
QPushButton#navButton:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(124,140,255,0.28), stop:1 rgba(34,211,238,0.10));
    color: {TEXT};
}}
#graphCard, #card {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
#cardTitle {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
#cardValue {{
    font-size: 16px;
    font-weight: 700;
}}
#speedDown {{
    color: {ACCENT_2};
    font-weight: 700;
}}
#speedUp {{
    color: {ACCENT};
    font-weight: 700;
}}
#content {{
    background: {BG};
}}
#pageTitle {{
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.4px;
}}
#pageSub {{
    color: {MUTED};
}}
QLineEdit, QPlainTextEdit, QDoubleSpinBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 12px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {SURFACE_3};
}}
QPushButton:pressed {{
    background: {SURFACE};
}}
QPushButton:disabled {{
    color: {GREY};
    background: {SURFACE};
}}
QPushButton#primary {{
    border: none;
    color: {ON_ACCENT};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #94a1ff, stop:1 #5be4f7);
}}
QPushButton#danger:hover {{
    background: rgba(248,113,113,0.18);
    border: 1px solid {RED};
    color: {RED};
}}
QTableView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    gridline-color: transparent;
    selection-background-color: transparent;
}}
QTableView {{
    font-weight: 500;
}}
QTableView::item {{
    padding-left: 10px;
    border-bottom: 1px solid {SURFACE_2};
}}
QHeaderView {{
    background: transparent;
}}
QHeaderView::section {{
    background: {SURFACE};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 10px;
    font-size: 11px;
    font-weight: 700;
}}
QTableCornerButton::section {{
    background: {SURFACE};
    border: none;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 14px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 18px;
    margin-right: 4px;
    border-radius: 9px;
    font-weight: 700;
}}
QTabBar::tab:selected {{
    background: {SURFACE_2};
    color: {TEXT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}
QProgressBar {{
    background: {SURFACE_3};
    border: none;
    border-radius: 6px;
    text-align: center;
    height: 12px;
    font-size: 10px;
    font-weight: 700;
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {SURFACE_3};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {GREY};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {SURFACE_3};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QMenu {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 22px;
    border-radius: 7px;
}}
QMenu::item:selected {{
    background: {SURFACE_3};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}
QStatusBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {MUTED};
}}
QStatusBar::item {{
    border: none;
}}
QSplitter::handle {{
    background: transparent;
    height: 8px;
}}
#dropZone {{
    background: {SURFACE};
    border: 2px dashed {BORDER};
    border-radius: 18px;
}}
#dropIcon {{
    font-size: 54px;
    color: {ACCENT};
}}
#dropTitle {{
    font-size: 18px;
    font-weight: 700;
}}
QLabel#muted {{
    color: {MUTED};
}}

QComboBox, QSpinBox, QTimeEdit {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 18px;
}}
QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE_3};
    selection-color: {TEXT};
    outline: none;
}}
QCheckBox {{
    spacing: 8px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QPushButton::menu-indicator {{
    image: none;
    width: 0px;
}}
QPushButton#themeButton, QPushButton#menuButton {{
    padding: 9px 0px;
}}
QTableWidget {{
    background: {SURFACE};
    alternate-background-color: {SURFACE};
}}
QTableWidget::item {{
    padding-left: 8px;
}}
QDialog QTableWidget {{
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
}}
"""
