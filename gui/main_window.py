import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QStackedWidget, QTableView, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from core.lt_engine import Engine
from gui import theme
from gui.dialogs import MagnetDialog, SettingsDialog
from gui.formatting import fmt_eta, fmt_size, fmt_speed
from gui.models import FilterProxy, TorrentModel
from gui.widgets import ProgressDelegate, SpeedGraph, StatCard

FILTERS = [
    ("all", "Все торренты"),
    ("downloading", "Загружаются"),
    ("seeding", "Раздаются"),
    ("completed", "Завершены"),
    ("paused", "На паузе"),
]

MB = 1024 * 1024


class MainWindow(QMainWindow):
    def __init__(self, initial=None):
        super().__init__()
        self.setWindowTitle("BitClient")
        self.resize(1320, 820)
        self.setMinimumSize(1000, 640)
        self.setAcceptDrops(True)

        self.settings = QSettings("deadshot", "BitClient")
        self.engine = Engine(Path.home() / ".bitclient")
        self.apply_limits()

        self.model = TorrentModel(self)
        self.proxy = FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.items = []
        self.files_key = None
        self.nav_buttons = {}

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        layout.addWidget(self.build_content(), 1)
        self.setCentralWidget(root)

        self.status_left = QLabel("")
        self.statusBar().addWidget(self.status_left, 1)
        self.status_right = QLabel("")
        self.statusBar().addPermanentWidget(self.status_right)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.engine.autosave)
        self.autosave_timer.start(30000)

        for source in initial or []:
            self.add_source(source)
        self.refresh()

    @property
    def save_dir(self) -> str:
        return self.settings.value("save_dir", str(Path.home() / "Downloads"))

    def apply_limits(self) -> None:
        down = float(self.settings.value("down_limit", 0))
        up = float(self.settings.value("up_limit", 0))
        self.engine.set_limits(down * MB, up * MB)

    def build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(250)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(4)

        logo = QLabel("◢ BitClient")
        logo.setObjectName("logo")
        sub = QLabel("быстрые торренты без лишнего")
        sub.setObjectName("logoSub")
        layout.addWidget(logo)
        layout.addWidget(sub)
        layout.addSpacing(26)

        section = QLabel("БИБЛИОТЕКА")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)
        layout.addSpacing(6)

        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, title in FILTERS:
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.set_category(k))
            group.addButton(button)
            layout.addWidget(button)
            self.nav_buttons[key] = (button, title)
        self.nav_buttons["all"][0].setChecked(True)

        layout.addStretch(1)

        card = QFrame()
        card.setObjectName("graphCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)
        head = QLabel("ТРАФИК")
        head.setObjectName("sectionLabel")
        self.graph = SpeedGraph()
        speeds = QHBoxLayout()
        self.down_label = QLabel("↓ 0 Б/с")
        self.down_label.setObjectName("speedDown")
        self.up_label = QLabel("↑ 0 Б/с")
        self.up_label.setObjectName("speedUp")
        speeds.addWidget(self.down_label)
        speeds.addStretch(1)
        speeds.addWidget(self.up_label)
        card_layout.addWidget(head)
        card_layout.addWidget(self.graph)
        card_layout.addLayout(speeds)
        layout.addWidget(card)
        return side

    def build_content(self) -> QWidget:
        content = QFrame()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel("Все торренты")
        self.page_title.setObjectName("pageTitle")
        self.page_sub = QLabel("")
        self.page_sub.setObjectName("pageSub")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_sub)
        header.addLayout(titles)
        header.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию…")
        self.search.setFixedWidth(240)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.proxy.set_text)
        header.addWidget(self.search)

        self.add_button = QPushButton("＋  Торрент")
        self.add_button.setObjectName("primary")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self.add_torrent_files)
        self.magnet_button = QPushButton("Magnet")
        self.magnet_button.setCursor(Qt.PointingHandCursor)
        self.magnet_button.clicked.connect(self.add_magnet)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setFixedWidth(44)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.add_button)
        header.addWidget(self.magnet_button)
        header.addWidget(self.settings_button)
        layout.addLayout(header)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.pause_button = QPushButton("⏸  Пауза")
        self.resume_button = QPushButton("▶  Продолжить")
        self.remove_button = QPushButton("✕  Удалить")
        self.remove_button.setObjectName("danger")
        self.pause_button.clicked.connect(self.pause_selected)
        self.resume_button.clicked.connect(self.resume_selected)
        self.remove_button.clicked.connect(lambda: self.remove_selected(False))
        for button in (self.pause_button, self.resume_button, self.remove_button):
            button.setCursor(Qt.PointingHandCursor)
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.build_drop_zone())
        self.stack.addWidget(self.build_table())
        splitter.addWidget(self.stack)
        splitter.addWidget(self.build_details())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 220])
        layout.addWidget(splitter, 1)
        return content

    def build_drop_zone(self) -> QWidget:
        zone = QFrame()
        zone.setObjectName("dropZone")
        layout = QVBoxLayout(zone)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        icon = QLabel("⬇")
        icon.setObjectName("dropIcon")
        icon.setAlignment(Qt.AlignCenter)
        title = QLabel("Перетащите сюда .torrent файл или magnet-ссылку")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("или нажмите «Торрент» в правом верхнем углу")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignCenter)
        button = QPushButton("Выбрать файлы")
        button.setObjectName("primary")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.add_torrent_files)
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(12)
        layout.addWidget(button, 0, Qt.AlignCenter)
        return zone

    def build_table(self) -> QWidget:
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setItemDelegateForColumn(2, ProgressDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setMouseTracking(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_menu)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.on_selection())
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 96), (2, 210), (3, 122), (4, 112), (5, 88), (6, 96), (7, 130)):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        self.table.sortByColumn(0, Qt.AscendingOrder)
        return self.table

    def build_details(self) -> QWidget:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)

        overview = QWidget()
        grid = QGridLayout(overview)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setSpacing(12)
        self.cards = {}
        names = [("down", "Скачано"), ("up", "Отдано"), ("ratio", "Рейтинг"),
                 ("peers", "Пиры (сиды)"), ("eta", "Осталось"), ("path", "Папка")]
        for i, (key, title) in enumerate(names):
            card = StatCard(title)
            self.cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        self.tabs.addTab(overview, "Обзор")

        self.files_table = QTableWidget(0, 3)
        self.files_table.setHorizontalHeaderLabels(["ФАЙЛ", "РАЗМЕР", "ПРОГРЕСС"])
        self.files_table.verticalHeader().setVisible(False)
        self.files_table.setShowGrid(False)
        self.files_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.files_table.setStyleSheet("QTableWidget { border: none; background: transparent; }")
        fh = self.files_table.horizontalHeader()
        fh.setSectionResizeMode(0, QHeaderView.Stretch)
        fh.setSectionResizeMode(1, QHeaderView.Fixed)
        fh.setSectionResizeMode(2, QHeaderView.Fixed)
        self.files_table.setColumnWidth(1, 110)
        self.files_table.setColumnWidth(2, 200)
        self.tabs.addTab(self.files_table, "Файлы")
        self.tabs.currentChanged.connect(lambda *_: self.update_details())
        return self.tabs

    def set_category(self, key: str) -> None:
        self.proxy.set_category(key)
        self.page_title.setText(dict(FILTERS)[key])
        self.update_subtitle()

    def update_subtitle(self) -> None:
        shown = self.proxy.rowCount()
        self.page_sub.setText(f"Показано: {shown} из {len(self.items)}")

    def selected_keys(self) -> list[str]:
        rows = self.table.selectionModel().selectedRows()
        return [self.model.items[self.proxy.mapToSource(i).row()].key for i in rows]

    def on_selection(self) -> None:
        has = bool(self.selected_keys())
        for button in (self.pause_button, self.resume_button, self.remove_button):
            button.setEnabled(has)
        self.files_key = None
        self.update_details()

    def refresh(self) -> None:
        self.items = self.engine.snapshot()
        self.model.update(self.items)
        self.stack.setCurrentIndex(1 if self.items else 0)

        total_down = sum(i.down_rate for i in self.items)
        total_up = sum(i.up_rate for i in self.items)
        self.graph.push(total_down, total_up)
        self.down_label.setText(f"↓ {fmt_speed(total_down)}")
        self.up_label.setText(f"↑ {fmt_speed(total_up)}")

        for key, (button, title) in self.nav_buttons.items():
            count = sum(1 for i in self.items if FilterProxy.matches(key, i))
            button.setText(f"{title}   {count}")

        active = sum(1 for i in self.items if i.state == "downloading")
        self.status_left.setText(f"  Торрентов: {len(self.items)}   •   Активных загрузок: {active}")
        self.status_right.setText(
            f"↓ {fmt_speed(total_down)}    ↑ {fmt_speed(total_up)}    "
            f"Всего скачано: {fmt_size(sum(i.total_down for i in self.items))}  ")

        if self.engine.errors:
            self.statusBar().showMessage(self.engine.errors.pop()[:160], 6000)
            self.engine.errors.clear()

        self.update_subtitle()
        self.update_details()

    def update_details(self) -> None:
        keys = self.selected_keys()
        info = next((i for i in self.items if keys and i.key == keys[0]), None)
        if info is None:
            for card in self.cards.values():
                card.set_value("—")
            self.files_table.setRowCount(0)
            self.files_key = None
            return
        self.cards["down"].set_value(fmt_size(info.total_down))
        self.cards["up"].set_value(fmt_size(info.total_up))
        ratio = info.total_up / info.total_down if info.total_down else 0
        self.cards["ratio"].set_value(f"{ratio:.2f}")
        self.cards["peers"].set_value(f"{info.peers}  ({info.seeds})")
        self.cards["eta"].set_value(
            "—" if info.state in ("completed", "seeding", "paused") else fmt_eta(info.eta))
        self.cards["path"].set_value(info.save_path)
        if self.tabs.currentIndex() == 1:
            self.update_files(info.key)

    def update_files(self, key: str) -> None:
        files = self.engine.files(key)
        if key != self.files_key or self.files_table.rowCount() != len(files):
            self.files_key = key
            self.files_table.setRowCount(len(files))
            for row, entry in enumerate(files):
                self.files_table.setItem(row, 0, QTableWidgetItem(entry.path))
                size_item = QTableWidgetItem(fmt_size(entry.size))
                size_item.setForeground(Qt.gray)
                self.files_table.setItem(row, 1, size_item)
                bar = QProgressBar()
                bar.setRange(0, 1000)
                self.files_table.setCellWidget(row, 2, bar)
                self.files_table.setRowHeight(row, 38)
        for row, entry in enumerate(files):
            bar = self.files_table.cellWidget(row, 2)
            if bar is not None:
                bar.setValue(int(entry.progress * 1000))
                bar.setFormat(f"{entry.progress * 100:.0f}%")

    def add_source(self, source: str, save_dir: str | None = None) -> None:
        try:
            self.engine.add(source, save_dir or self.save_dir)
        except Exception as e:
            QMessageBox.warning(self, "Не удалось добавить", f"{source[:80]}\n\n{e}")

    def add_torrent_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите .torrent файлы", str(Path.home()), "Torrent (*.torrent)")
        for file in files:
            self.add_source(file)
        self.refresh()

    def add_magnet(self) -> None:
        dialog = MagnetDialog(self.save_dir, self)
        clipboard = QGuiApplication.clipboard().text().strip()
        if clipboard.startswith("magnet:"):
            dialog.text.setPlainText(clipboard)
        if dialog.exec():
            for link in dialog.links():
                self.add_source(link, dialog.save_dir())
            self.refresh()

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.save_dir,
            float(self.settings.value("down_limit", 0)),
            float(self.settings.value("up_limit", 0)),
            self,
        )
        if dialog.exec():
            folder, down, up = dialog.values()
            self.settings.setValue("save_dir", folder)
            self.settings.setValue("down_limit", down)
            self.settings.setValue("up_limit", up)
            self.apply_limits()

    def pause_selected(self) -> None:
        for key in self.selected_keys():
            self.engine.pause(key)
        self.refresh()

    def resume_selected(self) -> None:
        for key in self.selected_keys():
            self.engine.resume(key)
        self.refresh()

    def remove_selected(self, delete_files: bool) -> None:
        keys = self.selected_keys()
        if not keys:
            return
        text = "Удалить выбранные торренты вместе с файлами на диске?" if delete_files \
            else "Удалить выбранные торренты из списка? Файлы останутся на диске."
        answer = QMessageBox.question(self, "Подтверждение", text)
        if answer != QMessageBox.Yes:
            return
        for key in keys:
            self.engine.remove(key, delete_files)
        self.refresh()

    def open_folder(self, key: str) -> None:
        info = next((i for i in self.items if i.key == key), None)
        if not info:
            return
        path = info.save_path
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_menu(self, position) -> None:
        keys = self.selected_keys()
        if not keys:
            return
        menu = QMenu(self)
        menu.addAction("▶  Продолжить", self.resume_selected)
        menu.addAction("⏸  Пауза", self.pause_selected)
        menu.addSeparator()
        menu.addAction("Открыть папку", lambda: self.open_folder(keys[0]))
        menu.addAction("Копировать magnet-ссылку",
                       lambda: QGuiApplication.clipboard().setText(self.engine.magnet(keys[0])))
        menu.addSeparator()
        menu.addAction("Удалить из списка", lambda: self.remove_selected(False))
        menu.addAction("Удалить вместе с файлами", lambda: self.remove_selected(True))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() or (mime.hasText() and mime.text().strip().startswith("magnet:")):
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".torrent"):
                    self.add_source(url.toLocalFile())
                elif url.toString().startswith("magnet:"):
                    self.add_source(url.toString())
        elif mime.hasText():
            for line in mime.text().splitlines():
                if line.strip().startswith("magnet:"):
                    self.add_source(line.strip())
        self.refresh()
        event.acceptProposedAction()

    def closeEvent(self, event):
        self.timer.stop()
        self.autosave_timer.stop()
        self.engine.shutdown()
        event.accept()
