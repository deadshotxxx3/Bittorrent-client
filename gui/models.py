from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor

from core.lt_engine import TorrentInfo
from gui import theme
from gui.formatting import fmt_eta, fmt_size, fmt_speed
from gui.widgets import PROGRESS_ROLE

HEADERS = ["НАЗВАНИЕ", "РАЗМЕР", "ПРОГРЕСС", "СКАЧИВАНИЕ", "ОТДАЧА", "ПИРЫ", "ОСТАЛОСЬ", "СТАТУС"]
STATUS_COLUMN = 7


class TorrentModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[TorrentInfo] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return HEADERS[section]
        if orientation == Qt.Horizontal and role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def _display(self, t: TorrentInfo, column: int):
        if column == 0:
            return t.name
        if column == 1:
            return fmt_size(t.size) if t.size else "—"
        if column == 2:
            return f"{t.progress * 100:.1f}%"
        if column == 3:
            return fmt_speed(t.down_rate) if t.down_rate else "—"
        if column == 4:
            return fmt_speed(t.up_rate) if t.up_rate else "—"
        if column == 5:
            return f"{t.peers}  ({t.seeds})"
        if column == 6:
            if t.state in ("completed", "seeding", "paused"):
                return "—"
            return fmt_eta(t.eta)
        if column == 7:
            return "●  " + theme.STATE_TITLES.get(t.state, t.state)
        return None

    def _sort(self, t: TorrentInfo, column: int):
        return (
            t.name.lower(), t.size, t.progress, t.down_rate,
            t.up_rate, t.peers, t.eta if t.eta >= 0 else 10 ** 12, t.state,
        )[column]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        t = self.items[index.row()]
        column = index.column()
        if role == Qt.DisplayRole:
            return None if column == 2 else self._display(t, column)
        if role == Qt.UserRole:
            return self._sort(t, column)
        if role == PROGRESS_ROLE:
            return t
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            if column == STATUS_COLUMN:
                return QColor(theme.STATE_COLORS.get(t.state, theme.TEXT))
            if column in (1, 5, 6):
                return QColor(theme.MUTED)
            if column == 3 and t.down_rate:
                return QColor(theme.ACCENT_2)
            if column == 4 and t.up_rate:
                return QColor(theme.ACCENT)
            return None
        if role == Qt.ToolTipRole and column == 0:
            return f"{t.name}\n{t.save_path}"
        return None

    def update(self, items: list[TorrentInfo]) -> None:
        if [i.key for i in items] == [i.key for i in self.items]:
            self.items = items
            if items:
                self.dataChanged.emit(self.index(0, 0), self.index(len(items) - 1, len(HEADERS) - 1))
        else:
            self.beginResetModel()
            self.items = items
            self.endResetModel()


class FilterProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.category = "all"
        self.text = ""
        self.setSortRole(Qt.UserRole)

    def set_category(self, category: str) -> None:
        self.category = category
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self.text = text.lower().strip()
        self.invalidateFilter()

    @staticmethod
    def matches(category: str, t: TorrentInfo) -> bool:
        if category == "all":
            return True
        if category == "downloading":
            return t.state in ("downloading", "metadata", "checking") and not t.paused
        if category == "completed":
            return t.progress >= 1.0
        if category == "seeding":
            return t.state == "seeding"
        if category == "paused":
            return t.paused
        return True

    def filterAcceptsRow(self, source_row, source_parent):
        t = self.sourceModel().items[source_row]
        if self.text and self.text not in t.name.lower():
            return False
        return self.matches(self.category, t)
