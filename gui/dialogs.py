import re
import threading
from pathlib import Path

from PySide6.QtCore import QTime, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QTimeEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.maketorrent import make_torrent
from core.rss import Feed
from gui.formatting import fmt_size
from gui.widgets import BarChart, StatCard
from gui.animations import FadeDialog, GlowButton
from core.schedule import Schedule

DEFAULTS = {
    "save_dir": str(Path.home() / "Downloads"),
    "down_limit": 0.0,
    "up_limit": 0.0,
    "notify": True,
    "tray_close": True,
    "autostart": False,
    "active_downloads": 3,
    "active_seeds": 5,
    "ratio_limit": 0.0,
    "seed_minutes": 0,
    "port": 6881,
    "interface": "",
    "proxy_type": "none",
    "proxy_host": "",
    "proxy_port": 1080,
    "proxy_user": "",
    "proxy_pass": "",
    "encryption": "prefer",
    "ip_filter": "",
    "watch_dir": "",
    "move_done": "",
    "alt_down": 0.5,
    "alt_up": 0.2,
    "alt_active": False,
}

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
    ok = GlowButton(ok_text)
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
    def __init__(self, path: str, parent=None, allow_empty: bool = False):
        super().__init__()
        self.allow_empty = allow_empty
        self.edit = QLineEdit(path)
        self.button = QPushButton("Обзор…")
        self.button.clicked.connect(self.browse)
        self.addWidget(self.edit, 1)
        self.addWidget(self.button)
        self.parent_widget = parent

    def browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self.parent_widget, "Выбор папки", self.edit.text() or str(Path.home()))
        if folder:
            self.edit.setText(folder)

    def path(self) -> str:
        text = self.edit.text().strip()
        if self.allow_empty:
            return text
        return text or str(Path.home() / "Downloads")


def wrap_layout(layout) -> QWidget:
    holder = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    holder.setLayout(layout)
    return holder


class MagnetDialog(FadeDialog):
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


class SettingsDialog(FadeDialog):
    def __init__(self, values: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(600)
        self.values_in = values
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(title_label("Настройки"))
        tabs = QTabWidget()
        tabs.addTab(self.general_tab(values), "Общие")
        tabs.addTab(self.queue_tab(values), "Очередь")
        tabs.addTab(self.network_tab(values), "Сеть")
        layout.addWidget(tabs)
        layout.addSpacing(6)
        layout.addLayout(buttons_row(self, "Сохранить"))

    def page(self) -> tuple:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)
        return widget, form

    def general_tab(self, v: dict) -> QWidget:
        widget, form = self.page()
        self.folder = FolderRow(v["save_dir"], self)
        self.down = speed_spin()
        self.down.setValue(float(v["down_limit"]))
        self.up = speed_spin()
        self.up.setValue(float(v["up_limit"]))
        self.notify = QCheckBox("Уведомлять о завершении загрузки")
        self.notify.setChecked(bool(v["notify"]))
        self.tray_close = QCheckBox("Сворачивать в трей при закрытии окна")
        self.tray_close.setChecked(bool(v["tray_close"]))
        self.autostart = QCheckBox("Запускать вместе с системой")
        self.autostart.setChecked(bool(v["autostart"]))
        self.watch = FolderRow(v["watch_dir"], self, True)
        self.move_done = FolderRow(v["move_done"], self, True)
        self.alt_down = speed_spin()
        self.alt_down.setValue(float(v["alt_down"]))
        self.alt_up = speed_spin()
        self.alt_up.setValue(float(v["alt_up"]))
        form.addRow("Папка по умолчанию", wrap_layout(self.folder))
        form.addRow("Лимит скачивания", self.down)
        form.addRow("Лимит отдачи", self.up)
        form.addRow("Режим ограничения: скачивание", self.alt_down)
        form.addRow("Режим ограничения: отдача", self.alt_up)
        form.addRow("Следить за папкой (.torrent)", wrap_layout(self.watch))
        form.addRow("Переносить завершённые в", wrap_layout(self.move_done))
        form.addRow("", self.notify)
        form.addRow("", self.tray_close)
        form.addRow("", self.autostart)
        return widget

    def queue_tab(self, v: dict) -> QWidget:
        widget, form = self.page()
        self.active_downloads = QSpinBox()
        self.active_downloads.setRange(0, 100)
        self.active_downloads.setSpecialValueText("без ограничений")
        self.active_downloads.setValue(int(v["active_downloads"]))
        self.active_seeds = QSpinBox()
        self.active_seeds.setRange(0, 100)
        self.active_seeds.setSpecialValueText("без ограничений")
        self.active_seeds.setValue(int(v["active_seeds"]))
        self.ratio = QDoubleSpinBox()
        self.ratio.setRange(0, 100)
        self.ratio.setDecimals(2)
        self.ratio.setSingleStep(0.5)
        self.ratio.setSpecialValueText("выключено")
        self.ratio.setValue(float(v["ratio_limit"]))
        self.seed_minutes = QSpinBox()
        self.seed_minutes.setRange(0, 100000)
        self.seed_minutes.setSuffix(" мин")
        self.seed_minutes.setSpecialValueText("выключено")
        self.seed_minutes.setValue(int(v["seed_minutes"]))
        form.addRow("Одновременных загрузок", self.active_downloads)
        form.addRow("Одновременных раздач", self.active_seeds)
        form.addRow("Остановить раздачу при рейтинге", self.ratio)
        form.addRow("Остановить раздачу через", self.seed_minutes)
        hint = muted_label("Лишние торренты ждут в очереди и стартуют, когда освободится место. "
                           "Если вы вручную нажали «Продолжить», ограничение раздачи для него не применяется.")
        form.addRow(hint)
        return widget

    def network_tab(self, v: dict) -> QWidget:
        widget, form = self.page()
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(v["port"]))
        self.interface = QLineEdit(v["interface"])
        self.interface.setPlaceholderText("например tun0, wg0 или 10.8.0.2")
        self.proxy_type = QComboBox()
        for title, key in (("Без прокси", "none"), ("SOCKS4", "socks4"),
                           ("SOCKS5", "socks5"), ("HTTP", "http")):
            self.proxy_type.addItem(title, key)
        self.proxy_type.setCurrentIndex(max(self.proxy_type.findData(v["proxy_type"]), 0))
        self.proxy_host = QLineEdit(v["proxy_host"])
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(1, 65535)
        self.proxy_port.setValue(int(v["proxy_port"]))
        self.proxy_user = QLineEdit(v["proxy_user"])
        self.proxy_pass = QLineEdit(v["proxy_pass"])
        self.proxy_pass.setEchoMode(QLineEdit.Password)
        self.encryption = QComboBox()
        for title, key in (("Предпочитать", "prefer"), ("Требовать", "force"), ("Выключено", "off")):
            self.encryption.addItem(title, key)
        self.encryption.setCurrentIndex(max(self.encryption.findData(v["encryption"]), 0))
        self.ip_filter = QLineEdit(v["ip_filter"])
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self.browse_filter)
        filter_row = QHBoxLayout()
        filter_row.addWidget(self.ip_filter, 1)
        filter_row.addWidget(browse)
        form.addRow("Порт", self.port)
        form.addRow("Сетевой интерфейс", self.interface)
        form.addRow("Прокси", self.proxy_type)
        form.addRow("Адрес прокси", self.proxy_host)
        form.addRow("Порт прокси", self.proxy_port)
        form.addRow("Логин", self.proxy_user)
        form.addRow("Пароль", self.proxy_pass)
        form.addRow("Шифрование", self.encryption)
        form.addRow("Файл блок-листа IP", wrap_layout(filter_row))
        form.addRow(muted_label(
            "Если указан интерфейс (например, VPN), трафик пойдёт только через него, "
            "а при падении VPN соединения прекратятся. Изменение порта и интерфейса применяется сразу."))
        return widget

    def browse_filter(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Блок-лист IP", str(Path.home()))
        if file:
            self.ip_filter.setText(file)

    def values(self) -> dict:
        result = dict(self.values_in)
        result.update({
            "save_dir": self.folder.path(),
            "down_limit": self.down.value(),
            "up_limit": self.up.value(),
            "alt_down": self.alt_down.value(),
            "alt_up": self.alt_up.value(),
            "watch_dir": self.watch.path(),
            "move_done": self.move_done.path(),
            "notify": self.notify.isChecked(),
            "tray_close": self.tray_close.isChecked(),
            "autostart": self.autostart.isChecked(),
            "active_downloads": self.active_downloads.value(),
            "active_seeds": self.active_seeds.value(),
            "ratio_limit": self.ratio.value(),
            "seed_minutes": self.seed_minutes.value(),
            "port": self.port.value(),
            "interface": self.interface.text().strip(),
            "proxy_type": self.proxy_type.currentData(),
            "proxy_host": self.proxy_host.text().strip(),
            "proxy_port": self.proxy_port.value(),
            "proxy_user": self.proxy_user.text(),
            "proxy_pass": self.proxy_pass.text(),
            "encryption": self.encryption.currentData(),
            "ip_filter": self.ip_filter.text().strip(),
        })
        return result


class ScheduleDialog(FadeDialog):
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


class CategoriesDialog(FadeDialog):
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


class RssDialog(FadeDialog):
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


class FilesDialog(FadeDialog):
    def __init__(self, name: str, files: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор файлов")
        self.setMinimumSize(680, 520)
        self.files = files
        self.leaves = []
        self.pending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title_label("Выбор файлов"))
        layout.addWidget(muted_label(name))
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["ФАЙЛ", "РАЗМЕР"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 110)
        layout.addWidget(self.tree, 1)
        self.build_tree()
        tools = QHBoxLayout()
        select_all = QPushButton("Выбрать всё")
        select_all.clicked.connect(lambda: self.set_all(Qt.Checked))
        select_none = QPushButton("Снять всё")
        select_none.clicked.connect(lambda: self.set_all(Qt.Unchecked))
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        tools.addWidget(select_all)
        tools.addWidget(select_none)
        tools.addStretch(1)
        tools.addWidget(self.summary)
        layout.addLayout(tools)
        layout.addLayout(buttons_row(self, "Продолжить"))
        self.tree.itemChanged.connect(self.schedule_summary)
        self.update_summary()

    def build_tree(self) -> None:
        folders = {}
        self.tree.blockSignals(True)
        for index, (path, size, priority) in enumerate(self.files):
            parts = path.replace("\\", "/").split("/")
            parent = self.tree.invisibleRootItem()
            built = ""
            for part in parts[:-1]:
                built = f"{built}/{part}"
                item = folders.get(built)
                if item is None:
                    item = QTreeWidgetItem(parent, [part, ""])
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    item.setExpanded(True)
                    folders[built] = item
                parent = item
            leaf = QTreeWidgetItem(parent, [parts[-1], fmt_size(size)])
            leaf.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            leaf.setCheckState(0, Qt.Checked if priority > 0 else Qt.Unchecked)
            leaf.setData(0, Qt.UserRole, index)
            self.leaves.append(leaf)
        self.tree.blockSignals(False)

    def set_all(self, state) -> None:
        self.tree.blockSignals(True)
        for leaf in self.leaves:
            leaf.setCheckState(0, state)
        self.tree.blockSignals(False)
        self.tree.viewport().update()
        self.update_summary()

    def schedule_summary(self, *_) -> None:
        if not self.pending:
            self.pending = True
            QTimer.singleShot(0, self.update_summary)

    def update_summary(self) -> None:
        self.pending = False
        chosen = 0
        total = 0
        for leaf in self.leaves:
            size = self.files[leaf.data(0, Qt.UserRole)][1]
            total += size
            if leaf.checkState(0) == Qt.Checked:
                chosen += size
        self.summary.setText(f"Выбрано: {fmt_size(chosen)} из {fmt_size(total)}")

    def priorities(self) -> list:
        result = [0] * len(self.files)
        for leaf in self.leaves:
            index = leaf.data(0, Qt.UserRole)
            if leaf.checkState(0) == Qt.Checked:
                old = self.files[index][2]
                result[index] = old if old > 0 else 4
        return result

    def accept(self) -> None:
        if not any(self.priorities()):
            QMessageBox.warning(self, "Нет файлов", "Выберите хотя бы один файл.")
            return
        super().accept()


class CreateTorrentDialog(FadeDialog):
    progress = Signal(float)
    created = Signal(str)
    failed = Signal(str)

    def __init__(self, default_trackers: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создать торрент")
        self.setMinimumWidth(600)
        self.result_path = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title_label("Создать торрент"))
        layout.addWidget(muted_label("Выберите файл или папку, которую хотите раздавать"))
        row = QHBoxLayout()
        self.source = QLineEdit()
        file_button = QPushButton("Файл…")
        file_button.clicked.connect(self.pick_file)
        folder_button = QPushButton("Папка…")
        folder_button.clicked.connect(self.pick_folder)
        row.addWidget(self.source, 1)
        row.addWidget(file_button)
        row.addWidget(folder_button)
        layout.addLayout(row)
        layout.addWidget(QLabel("Трекеры (по одному в строке)"))
        self.trackers = QPlainTextEdit("\n".join(default_trackers))
        self.trackers.setMinimumHeight(110)
        layout.addWidget(self.trackers)
        layout.addWidget(QLabel("Комментарий"))
        self.comment = QLineEdit()
        layout.addWidget(self.comment)
        self.private = QCheckBox("Приватный торрент (без DHT и обмена пирами)")
        self.seed = QCheckBox("Сразу начать раздачу")
        self.seed.setChecked(True)
        layout.addWidget(self.private)
        layout.addWidget(self.seed)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setVisible(False)
        layout.addWidget(self.bar)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Закрыть")
        self.cancel_button.clicked.connect(self.reject)
        self.create_button = GlowButton("Создать")
        self.create_button.setObjectName("primary")
        self.create_button.clicked.connect(self.start)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)
        layout.addLayout(buttons)
        self.progress.connect(lambda value: self.bar.setValue(int(value * 1000)))
        self.created.connect(self.on_created)
        self.failed.connect(self.on_failed)

    def pick_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Файл для раздачи", str(Path.home()))
        if file:
            self.source.setText(file)

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка для раздачи", str(Path.home()))
        if folder:
            self.source.setText(folder)

    def start(self) -> None:
        source = self.source.text().strip()
        if not source or not Path(source).exists():
            QMessageBox.warning(self, "Источник не найден", "Выберите существующий файл или папку.")
            return
        suggested = str(Path(source).with_suffix(".torrent")) if Path(source).is_file() \
            else source.rstrip("/\\") + ".torrent"
        target, _ = QFileDialog.getSaveFileName(self, "Сохранить .torrent", suggested, "Torrent (*.torrent)")
        if not target:
            return
        trackers = [t.strip() for t in self.trackers.toPlainText().splitlines() if t.strip()]
        comment = self.comment.text().strip()
        private = self.private.isChecked()
        self.create_button.setEnabled(False)
        self.bar.setValue(0)
        self.bar.setVisible(True)

        def work():
            try:
                make_torrent(source, target, trackers, comment, private, self.progress.emit)
                self.created.emit(target)
            except Exception as e:
                self.failed.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_created(self, path: str) -> None:
        self.result_path = path
        self.accept()

    def on_failed(self, message: str) -> None:
        self.create_button.setEnabled(True)
        self.bar.setVisible(False)
        QMessageBox.warning(self, "Не удалось создать торрент", message)

    def source_path(self) -> str:
        return self.source.text().strip()

    def start_seeding(self) -> bool:
        return self.seed.isChecked()


class LimitsDialog(FadeDialog):
    def __init__(self, down_mb: float, up_mb: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Лимиты торрента")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(title_label("Лимиты торрента"))
        self.down = speed_spin()
        self.down.setValue(down_mb)
        self.up = speed_spin()
        self.up.setValue(up_mb)
        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Скачивание", self.down)
        form.addRow("Отдача", self.up)
        layout.addLayout(form)
        layout.addLayout(buttons_row(self, "Применить"))

    def values(self) -> tuple:
        return self.down.value(), self.up.value()


class StatsDialog(FadeDialog):
    def __init__(self, stats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Статистика")
        self.setMinimumSize(720, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(title_label("Статистика трафика"))
        grid = QHBoxLayout()
        grid.setSpacing(12)
        for title, days in (("Сегодня", 1), ("7 дней", 7), ("30 дней", 30), ("Всего", None)):
            down, up = stats.totals(days)
            card = StatCard(title)
            card.set_value(f"↓ {fmt_size(down)}    ↑ {fmt_size(up)}")
            grid.addWidget(card)
        layout.addLayout(grid)
        layout.addWidget(muted_label("Последние 14 дней: бирюзовым — скачано, синим — отдано"))
        chart = BarChart()
        chart.set_data(stats.series(14))
        layout.addWidget(chart, 1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
