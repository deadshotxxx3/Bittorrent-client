import re
from pathlib import Path

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget,
)

from core.rss import Feed
from core.schedule import Schedule

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def title_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    return label


def muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(True)
    return label


def buttons_row(dialog: QDialog, ok_text: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton("Отмена")
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName("primary")
    ok.clicked.connect(dialog.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row


def speed_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, 10000)
    spin.setDecimals(1)
    spin.setSuffix(" МБ/с")
    spin.setSpecialValueText("без лимита")
    return spin


class FolderRow(QHBoxLayout):
    def __init__(self, path: str, parent=None):
        super().__init__()
        self.edit = QLineEdit(path)
        self.button = QPushButton("Обзор…")
        self.button.clicked.connect(self.browse)
        self.addWidget(self.edit, 1)
        self.addWidget(self.button)
        self.parent_widget = parent

    def browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.parent_widget, "Папка загрузки", self.edit.text())
        if folder:
            self.edit.setText(folder)

    def path(self) -> str:
        return self.edit.text().strip() or str(Path.home() / "Downloads")


def wrap_layout(layout) -> QWidget:
    holder = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    holder.setLayout(layout)
    return holder


class MagnetDialog(QDialog):
    def __init__(self, default_dir: str, categories: list[str], current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить magnet-ссылку")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title_label("Magnet-ссылки"))
        layout.addWidget(muted_label("Вставьте одну или несколько ссылок, по одной на строку"))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("magnet:?xt=urn:btih:…")
        self.text.setMinimumHeight(120)
        layout.addWidget(self.text)
        layout.addWidget(QLabel("Категория"))
        self.category_box = QComboBox()
        self.category_box.addItem("— без категории —", "")
        for name in categories:
            self.category_box.addItem(name, name)
        index = self.category_box.findData(current)
        self.category_box.setCurrentIndex(max(index, 0))
        layout.addWidget(self.category_box)
        layout.addWidget(QLabel("Папка (если категория не выбрана)"))
        self.folder = FolderRow(default_dir, self)
        layout.addLayout(self.folder)
        layout.addSpacing(6)
        layout.addLayout(buttons_row(self, "Добавить"))

    def links(self) -> list[str]:
        return [line.strip() for line in self.text.toPlainText().splitlines()
                if line.strip().startswith("magnet:")]

    def save_dir(self) -> str:
        return self.folder.path()

    def category(self) -> str:
        return self.category_box.currentData() or ""


class SettingsDialog(QDialog):
    def __init__(self, save_dir: str, down_mb: float, up_mb: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(title_label("Настройки"))
        self.folder = FolderRow(save_dir, self)
        self.down = speed_spin()
        self.down.setValue(down_mb)
        self.up = speed_spin()
        self.up.setValue(up_mb)
        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Папка по умолчанию", wrap_layout(self.folder))
        form.addRow("Лимит скачивания", self.down)
        form.addRow("Лимит отдачи", self.up)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addLayout(buttons_row(self, "Сохранить"))

    def values(self) -> tuple[str, float, float]:
        return self.folder.path(), self.down.value(), self.up.value()


class ScheduleDialog(QDialog):
    def __init__(self, schedule: Schedule, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Расписание скоростей")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(title_label("Расписание скоростей"))
        layout.addWidget(muted_label(
            "В выбранные часы и дни действуют лимиты ниже, в остальное время — "
            "лимиты из настроек. Если время конца раньше начала, интервал переходит через полночь."))
        self.enabled = QCheckBox("Включить расписание")
        self.enabled.setChecked(schedule.enabled)
        layout.addWidget(self.enabled)
        self.start = QTimeEdit(QTime.fromString(schedule.start, "HH:mm"))
        self.start.setDisplayFormat("HH:mm")
        self.end = QTimeEdit(QTime.fromString(schedule.end, "HH:mm"))
        self.end.setDisplayFormat("HH:mm")
        self.down = speed_spin()
        self.down.setValue(schedule.down)
        self.up = speed_spin()
        self.up.setValue(schedule.up)
        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("С", self.start)
        form.addRow("До", self.end)
        form.addRow("Лимит скачивания", self.down)
        form.addRow("Лимит отдачи", self.up)
        layout.addLayout(form)
        days_row = QHBoxLayout()
        self.day_boxes = []
        for i, name in enumerate(DAYS):
            box = QCheckBox(name)
            box.setChecked(i in schedule.days)
            self.day_boxes.append(box)
            days_row.addWidget(box)
        layout.addLayout(days_row)
        layout.addSpacing(6)
        layout.addLayout(buttons_row(self, "Сохранить"))

    def schedule(self) -> Schedule:
        return Schedule(
            enabled=self.enabled.isChecked(),
            start=self.start.time().toString("HH:mm"),
            end=self.end.time().toString("HH:mm"),
            down=self.down.value(),
            up=self.up.value(),
            days=[i for i, box in enumerate(self.day_boxes) if box.isChecked()],
        )


class CategoriesDialog(QDialog):
    def __init__(self, categories: dict, default_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Категории")
        self.setMinimumSize(640, 420)
        self.default_dir = default_dir
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title_label("Категории"))
        layout.addWidget(muted_label(
            "У каждой категории своя папка загрузки. Название и папку можно править прямо в таблице."))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["НАЗВАНИЕ", "ПАПКА"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 180)
        layout.addWidget(self.table, 1)
        for name, path in categories.items():
            self.add_row(name, path)
        tools = QHBoxLayout()
        add = QPushButton("＋  Добавить")
        add.clicked.connect(lambda: self.add_row("", self.default_dir))
        browse = QPushButton("Папка…")
        browse.clicked.connect(self.browse)
        remove = QPushButton("Удалить")
        remove.setObjectName("danger")
        remove.clicked.connect(self.remove_row)
        tools.addWidget(add)
        tools.addWidget(browse)
        tools.addWidget(remove)
        tools.addStretch(1)
        layout.addLayout(tools)
        layout.addLayout(buttons_row(self, "Сохранить"))

    def add_row(self, name: str, path: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(path))
        self.table.setRowHeight(row, 40)

    def remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def browse(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка категории", self.default_dir)
        if folder:
            self.table.item(row, 1).setText(folder)

    def categories(self) -> dict:
        result = {}
        for row in range(self.table.rowCount()):
            name = (self.table.item(row, 0).text() if self.table.item(row, 0) else "").strip()
            path = (self.table.item(row, 1).text() if self.table.item(row, 1) else "").strip()
            if name and path:
                result[name] = path
        return result


class RssDialog(QDialog):
    COLUMNS = ["ВКЛ", "НАЗВАНИЕ", "АДРЕС ЛЕНТЫ", "ВКЛЮЧИТЬ (REGEX)", "ИСКЛЮЧИТЬ (REGEX)", "КАТЕГОРИЯ", "МИН"]

    def __init__(self, feeds: list[Feed], categories: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("RSS-автозагрузка")
        self.setMinimumSize(900, 460)
        self.categories = categories
        self.original = {f.url: f for f in feeds}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title_label("RSS-автозагрузка"))
        layout.addWidget(muted_label(
            "Первая проверка новой ленты только запоминает текущие записи, скачиваются лишь те, "
            "что появятся после. Фильтры — регулярные выражения без учёта регистра, "
            "например: 1080p|2160p"))
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for column, width in ((0, 50), (1, 140), (3, 150), (4, 150), (5, 150), (6, 80)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)
        for feed in feeds:
            self.add_row(feed)
        tools = QHBoxLayout()
        add = QPushButton("＋  Добавить ленту")
        add.clicked.connect(lambda: self.add_row(Feed(name="Новая лента", url="")))
        remove = QPushButton("Удалить")
        remove.setObjectName("danger")
        remove.clicked.connect(self.remove_row)
        tools.addWidget(add)
        tools.addWidget(remove)
        tools.addStretch(1)
        layout.addLayout(tools)
        layout.addLayout(buttons_row(self, "Сохранить"))

    def add_row(self, feed: Feed) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check.setCheckState(Qt.Checked if feed.enabled else Qt.Unchecked)
        self.table.setItem(row, 0, check)
        for column, value in ((1, feed.name), (2, feed.url), (3, feed.include), (4, feed.exclude)):
            self.table.setItem(row, column, QTableWidgetItem(value))
        combo = QComboBox()
        combo.addItem("—", "")
        for name in self.categories:
            combo.addItem(name, name)
        combo.setCurrentIndex(max(combo.findData(feed.category), 0))
        self.table.setCellWidget(row, 5, combo)
        spin = QSpinBox()
        spin.setRange(5, 1440)
        spin.setValue(feed.interval)
        self.table.setCellWidget(row, 6, spin)
        self.table.setRowHeight(row, 44)

    def remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    def feeds(self) -> list[Feed]:
        result = []
        for row in range(self.table.rowCount()):
            url = self._text(row, 2)
            if not url:
                continue
            old = self.original.get(url)
            result.append(Feed(
                name=self._text(row, 1) or url,
                url=url,
                include=self._text(row, 3),
                exclude=self._text(row, 4),
                category=self.table.cellWidget(row, 5).currentData() or "",
                interval=self.table.cellWidget(row, 6).value(),
                enabled=self.table.item(row, 0).checkState() == Qt.Checked,
                last_check=old.last_check if old else 0.0,
                primed=old.primed if old else False,
            ))
        return result

    def accept(self) -> None:
        for row in range(self.table.rowCount()):
            for column in (3, 4):
                pattern = self._text(row, column)
                if not pattern:
                    continue
                try:
                    re.compile(pattern)
                except re.error as e:
                    QMessageBox.warning(self, "Неверное выражение", f"Строка {row + 1}: {e}")
                    return
        super().accept()
