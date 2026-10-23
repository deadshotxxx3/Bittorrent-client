import dataclasses
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSplitter, QStackedWidget,
    QSystemTrayIcon, QTableView, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from core.lt_engine import EXTRA_TRACKERS, Engine
from core.rss import RssStore, run_check
from core.stats import Stats
from core.schedule import Schedule, effective_limits, is_active
from gui import autostart, theme
from gui.animations import GlowButton, crossfade, fade_in, pulse, window_fade
from gui.dialogs import (
    DEFAULTS, CategoriesDialog, CreateTorrentDialog, FilesDialog, LimitsDialog, MagnetDialog,
    RssDialog, ScheduleDialog, SettingsDialog, StatsDialog,
)
from gui.formatting import fmt_eta, fmt_size, fmt_speed
from gui.icons import app_icon
from gui.models import HEADERS, FilterProxy, TorrentModel
from gui.power import run_power_action
from gui.widgets import ProgressDelegate, SpeedGraph, StatCard

FILTERS = [
    ("all", "Все торренты"),
    ("downloading", "Загружаются"),
    ("seeding", "Раздаются"),
    ("completed", "Завершены"),
    ("paused", "На паузе"),
]

MB = 1024 * 1024
STATE_DIR = Path.home() / ".bitclient"
log = logging.getLogger("bitclient")


class RssSignals(QObject):
    done = Signal(object)


class MainWindow(QMainWindow):
    def __init__(self, initial=None):
        super().__init__()
        self.setWindowTitle("BitClient")
        self.resize(1360, 840)
        self.setMinimumSize(1040, 660)
        self.setAcceptDrops(True)

        self.settings = QSettings("deadshot", "BitClient")
        self.engine = Engine(STATE_DIR)
        self.rss = RssStore(STATE_DIR / "rss.json")
        self.stats = Stats(STATE_DIR / "stats.json")
        self.last_tick = time.monotonic()
        self.rss_signals = RssSignals()
        self.rss_signals.done.connect(self.on_rss_done)
        self.rss_running = False
        self.last_limits = None
        self.really_quit = False
        self.engine_down = False
        self.tray_hint_shown = False
        self.after_action = "none"
        self.after_seen_busy = False
        self.after_pending = False
        self.after_actions = {}
        self.setWindowIcon(app_icon())

        self.model = TorrentModel(self)
        self.proxy = FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.items = []
        self.files_key = None
        self.nav_buttons = {}
        self.dynamic_buttons = {}
        self.dynamic_signature = None
        self.current_filter = "all"
        self.page_titles = dict(FILTERS)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.build_sidebar())
        layout.addWidget(self.build_content(), 1)
        self.setCentralWidget(root)

        self.status_left = QLabel("")
        self.statusBar().addWidget(self.status_left, 1)
        self.status_schedule = QLabel("")
        self.statusBar().addPermanentWidget(self.status_schedule)
        self.status_right = QLabel("")
        self.statusBar().addPermanentWidget(self.status_right)

        self.engine.apply_config(self.config())
        self.apply_limits()
        self.build_tray()
        self.build_shortcuts()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start(30000)
        self.schedule_timer = QTimer(self)
        self.schedule_timer.timeout.connect(self.apply_limits)
        self.schedule_timer.start(30000)
        self.rss_timer = QTimer(self)
        self.rss_timer.timeout.connect(lambda: self.check_rss(False))
        self.rss_timer.start(60000)
        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(self.scan_watch_folder)
        self.watch_timer.start(10000)

        for source in initial or []:
            self.add_source(source)
        self.refresh()
        QTimer.singleShot(5000, lambda: self.check_rss(False))

    def config(self) -> dict:
        result = {}
        for key, default in DEFAULTS.items():
            value = self.settings.value(key, default)
            try:
                if isinstance(default, bool):
                    value = value in (True, "true", "True", "1", 1)
                elif isinstance(default, int):
                    value = int(float(value))
                elif isinstance(default, float):
                    value = float(value)
                else:
                    value = str(value)
            except (TypeError, ValueError):
                value = default
            result[key] = value
        return result

    @property
    def save_dir(self) -> str:
        return self.config()["save_dir"]

    @property
    def theme_name(self) -> str:
        return self.settings.value("theme", "dark")

    def load_schedule(self) -> Schedule:
        return Schedule.from_json(self.settings.value("schedule", ""))

    def apply_limits(self) -> None:
        cfg = self.config()
        base_down = cfg["down_limit"]
        base_up = cfg["up_limit"]
        schedule = self.load_schedule()
        now = datetime.now()
        alt = cfg["alt_active"]
        if alt:
            down, up = cfg["alt_down"], cfg["alt_up"]
        else:
            down, up = effective_limits(schedule, base_down, base_up, now)
        if (down, up) != self.last_limits:
            self.last_limits = (down, up)
            self.engine.set_limits(down * MB, up * MB)
        if alt:
            self.status_schedule.setText("🐢 режим ограничения скорости    ")
        elif is_active(schedule, now):
            self.status_schedule.setText("⏱ расписание активно    ")
        else:
            self.status_schedule.setText("")

    def autosave(self) -> None:
        self.engine.autosave()
        try:
            self.stats.save()
        except OSError as e:
            log.warning("stats save failed: %s", e)

    def build_shortcuts(self) -> None:
        def bind(sequence: str, handler) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)

        bind("Ctrl+O", self.add_torrent_files)
        bind("Ctrl+N", self.create_torrent)
        bind("Ctrl+F", self.focus_search)
        bind("Ctrl+V", self.paste_magnet)
        bind("Delete", lambda: self.remove_selected(False))
        bind("Shift+Delete", lambda: self.remove_selected(True))
        bind("Space", self.toggle_pause_selected)
        bind("Ctrl+,", self.open_settings)
        bind("Ctrl+Q", self.quit_app)

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def paste_magnet(self) -> None:
        links = [line.strip() for line in QGuiApplication.clipboard().text().splitlines()
                 if line.strip().startswith("magnet:")]
        for link in links:
            self.add_source(link, category=self.current_category())
        if links:
            self.refresh()

    def toggle_pause_selected(self) -> None:
        infos = self.selected_infos()
        if not infos:
            return
        if all(i.paused for i in infos):
            self.resume_selected()
        else:
            self.pause_selected()

    def scan_watch_folder(self) -> None:
        folder = self.config()["watch_dir"]
        if not folder or not Path(folder).is_dir():
            return
        added = False
        for file in sorted(Path(folder).glob("*.torrent")):
            try:
                ok = self.add_source(str(file), category=self.current_category(), ask=False)
                file.rename(file.with_name(file.name + (".added" if ok else ".failed")))
                added = added or ok
            except OSError as e:
                log.warning("watch folder: %s", e)
        if added:
            self.refresh()

    def toggle_alt_speed(self, enabled: bool) -> None:
        self.settings.setValue("alt_active", enabled)
        self.last_limits = None
        self.apply_limits()

    def open_stats(self) -> None:
        self.stats.save()
        StatsDialog(self.stats, self).exec()

    def open_log(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(STATE_DIR / "log.txt")))

    def has_space(self, category: str, needed: int) -> bool:
        target = self.engine.categories.get(category) or self.save_dir
        try:
            Path(target).mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(target).free
        except OSError:
            return True
        if needed <= free:
            return True
        answer = QMessageBox.question(
            self, "Мало места",
            f"Нужно {fmt_size(needed)}, свободно {fmt_size(free)}.\nВсё равно добавить?")
        return answer == QMessageBox.Yes

    def show_header_menu(self, position) -> None:
        header = self.table.horizontalHeader()
        menu = QMenu(self)
        for column in range(1, len(HEADERS)):
            action = menu.addAction(HEADERS[column].title())
            action.setCheckable(True)
            action.setChecked(not header.isSectionHidden(column))
            action.triggered.connect(
                lambda checked=False, c=column: header.setSectionHidden(c, not checked))
        menu.exec(header.mapToGlobal(position))

    def build_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Открыть BitClient", self.show_window)
        self.tray_menu.addAction("Приостановить все", self.pause_all)
        self.tray_menu.addAction("Продолжить все", self.resume_all)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Выход", self.quit_app)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.setToolTip("BitClient")
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self.really_quit = True
        self.close()

    def notify(self, title: str, message: str) -> None:
        if not self.config()["notify"]:
            return
        if self.tray is not None:
            self.tray.showMessage(title, message, QSystemTrayIcon.Information, 6000)
        else:
            self.statusBar().showMessage(f"{title}: {message}", 8000)

    def handle_events(self) -> None:
        events = list(self.engine.events)
        del self.engine.events[:]
        for kind, name, *_ in events:
            if kind == "finished":
                self.notify("Загрузка завершена", name)
            elif kind == "stopped":
                self.notify("Раздача остановлена", name)

    def set_after_action(self, name: str) -> None:
        self.after_action = name
        self.after_seen_busy = False
        self.after_pending = False
        action = self.after_actions.get(name)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def check_after_action(self) -> None:
        if self.after_action == "none" or self.after_pending:
            return
        busy = any(i.progress < 1.0 and not i.paused and i.state != "error" for i in self.items)
        if busy:
            self.after_seen_busy = True
        elif self.after_seen_busy:
            self.after_pending = True
            QTimer.singleShot(0, self.run_after_action)

    def run_after_action(self) -> None:
        name = self.after_action
        titles = {"sleep": "Компьютер уйдёт в сон", "shutdown": "Компьютер будет выключен",
                  "exit": "BitClient закроется"}
        remaining = {"value": 30}
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Загрузки завершены")
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        def update_text():
            box.setText(f"Все загрузки завершены.\n{titles[name]} через {remaining['value']} с.")

        def tick():
            remaining["value"] -= 1
            if remaining["value"] <= 0:
                box.accept()
            else:
                update_text()

        update_text()
        countdown = QTimer(box)
        countdown.timeout.connect(tick)
        countdown.start(1000)
        accepted = box.exec() == QMessageBox.Ok
        countdown.stop()
        self.set_after_action("none")
        if not accepted:
            return
        if name == "exit":
            self.quit_app()
            return
        self.shutdown_engine()
        run_power_action(name)
        self.quit_app()

    def shutdown_engine(self) -> None:
        if not self.engine_down:
            self.engine_down = True
            self.engine.shutdown()

    def pause_all(self) -> None:
        self.engine.pause_all()
        self.refresh()

    def resume_all(self) -> None:
        self.engine.resume_all()
        self.refresh()

    def handle_arguments(self, arguments: list) -> None:
        for argument in arguments:
            if argument.startswith("magnet:") or argument.lower().endswith(".torrent"):
                self.add_source(argument, category=self.current_category())
        self.show_window()
        self.refresh()

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
        layout.addSpacing(22)

        section = QLabel("БИБЛИОТЕКА")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)
        layout.addSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for key, title in FILTERS:
            button = self.make_nav_button(title, key)
            layout.addWidget(button)
            self.nav_buttons[key] = (button, title)
        self.nav_buttons["all"][0].setChecked(True)

        layout.addSpacing(12)
        self.dynamic_host = QWidget()
        self.dynamic_layout = QVBoxLayout(self.dynamic_host)
        self.dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self.dynamic_layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.dynamic_host)
        layout.addWidget(scroll, 1)

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

    def make_nav_button(self, title: str, key: str) -> QPushButton:
        button = QPushButton(title)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _=False, k=key: self.set_category(k))
        self.nav_group.addButton(button)
        return button

    def rebuild_dynamic(self) -> None:
        categories = sorted(self.engine.categories)
        tags = sorted({tag for item in self.items for tag in item.tags})
        trackers = sorted({item.tracker for item in self.items if item.tracker})
        signature = (tuple(categories), tuple(tags), tuple(trackers))
        if signature != self.dynamic_signature:
            self.dynamic_signature = signature
            while self.dynamic_layout.count():
                child = self.dynamic_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    if isinstance(widget, QPushButton):
                        self.nav_group.removeButton(widget)
                    widget.deleteLater()
            self.dynamic_buttons = {}
            self.page_titles = dict(FILTERS)
            if categories:
                self.dynamic_layout.addWidget(self.section_label("КАТЕГОРИИ"))
                for name in categories:
                    self.add_dynamic_button(f"cat:{name}", name, f"▪  {name}")
            if tags:
                self.dynamic_layout.addSpacing(8)
                self.dynamic_layout.addWidget(self.section_label("МЕТКИ"))
                for name in tags:
                    self.add_dynamic_button(f"tag:{name}", name, f"#  {name}")
            if trackers:
                self.dynamic_layout.addSpacing(8)
                self.dynamic_layout.addWidget(self.section_label("ТРЕКЕРЫ"))
                for name in trackers:
                    self.add_dynamic_button(f"trk:{name}", name, f"⌁  {name}")
            self.dynamic_layout.addStretch(1)
            if self.current_filter not in self.page_titles and self.current_filter not in self.dynamic_buttons:
                self.set_category("all")
                self.nav_buttons["all"][0].setChecked(True)
            elif self.current_filter in self.dynamic_buttons:
                self.dynamic_buttons[self.current_filter][0].setChecked(True)
        for key, (button, title) in self.dynamic_buttons.items():
            count = sum(1 for i in self.items if FilterProxy.matches(key, i))
            button.setText(f"{title}   {count}")

    def section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def add_dynamic_button(self, key: str, name: str, title: str) -> None:
        button = self.make_nav_button(title, key)
        self.dynamic_layout.addWidget(button)
        self.dynamic_buttons[key] = (button, title)
        self.page_titles[key] = name

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
        self.search.setPlaceholderText("Поиск по названию, категории, метке…")
        self.search.setFixedWidth(280)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.proxy.set_text)
        header.addWidget(self.search)

        self.add_button = GlowButton("＋  Торрент")
        self.add_button.setObjectName("primary")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self.add_torrent_files)
        self.magnet_button = QPushButton("Magnet")
        self.magnet_button.setCursor(Qt.PointingHandCursor)
        self.magnet_button.clicked.connect(self.add_magnet)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setFixedWidth(44)
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.setToolTip("Светлая / тёмная тема")
        self.theme_button.clicked.connect(self.toggle_theme)
        self.update_theme_button()

        self.menu_button = QPushButton("⚙")
        self.menu_button.setObjectName("menuButton")
        self.menu_button.setFixedWidth(44)
        self.menu_button.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self.menu_button)
        menu.addAction("Настройки", self.open_settings)
        menu.addAction("Расписание скоростей", self.open_schedule)
        menu.addAction("Категории", self.open_categories)
        menu.addAction("RSS-автозагрузка", self.open_rss)
        menu.addSeparator()
        menu.addAction("Создать торрент…", self.create_torrent)
        self.alt_action = menu.addAction("Режим ограничения скорости")
        self.alt_action.setCheckable(True)
        self.alt_action.setChecked(self.config()["alt_active"])
        self.alt_action.triggered.connect(self.toggle_alt_speed)
        menu.addAction("Статистика", self.open_stats)
        menu.addAction("Открыть лог", self.open_log)
        menu.addAction("Приостановить все", self.pause_all)
        menu.addAction("Продолжить все", self.resume_all)
        menu.addSeparator()
        after_menu = menu.addMenu("После завершения загрузок")
        group = QActionGroup(after_menu)
        group.setExclusive(True)
        for key, title in (("none", "Ничего"), ("sleep", "Спящий режим"),
                           ("shutdown", "Выключить компьютер"), ("exit", "Закрыть BitClient")):
            action = QAction(title, after_menu)
            action.setCheckable(True)
            action.setChecked(key == "none")
            action.triggered.connect(lambda _=False, k=key: self.set_after_action(k))
            group.addAction(action)
            after_menu.addAction(action)
            self.after_actions[key] = action
        self.menu_button.setMenu(menu)

        header.addWidget(self.add_button)
        header.addWidget(self.magnet_button)
        header.addWidget(self.theme_button)
        header.addWidget(self.menu_button)
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
        splitter.setSizes([500, 260])
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
        button = GlowButton("Выбрать файлы")
        button.setObjectName("primary")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.add_torrent_files)
        pulse(icon)
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
        widths = ((1, 92), (2, 190), (3, 116), (4, 104), (5, 84), (6, 92), (7, 120), (8, 150),
                  (9, 140), (10, 84))
        for column, width in widths:
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            self.table.setColumnWidth(column, width)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_header_menu)
        saved = self.settings.value("header_state")
        if saved:
            header.restoreState(saved)
        else:
            header.hideSection(9)
            header.hideSection(10)
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
        grid.setRowStretch(2, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(overview)
        self.tabs.addTab(scroll, "Обзор")

        self.files_table = self.make_table(
            ["ФАЙЛ", "РАЗМЕР", "ПРОГРЕСС", "ПРИОРИТЕТ"], ((1, 110), (2, 200), (3, 110)))
        self.tabs.addTab(self.files_table, "Файлы")

        self.peers_table = self.make_table(
            ["АДРЕС", "КЛИЕНТ", "СКАЧИВАНИЕ", "ОТДАЧА", "ПРОГРЕСС"], ((1, 190), (2, 120), (3, 110), (4, 90)))
        self.tabs.addTab(self.peers_table, "Пиры")

        self.trackers_table = self.make_table(
            ["ТРЕКЕР", "СТАТУС", "СООБЩЕНИЕ", "ТИР"], ((1, 120), (2, 260), (3, 60)))
        self.trackers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.trackers_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tabs.addTab(self.trackers_table, "Трекеры")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        return self.tabs

    def on_tab_changed(self, index: int) -> None:
        fade_in(self.tabs.widget(index), 220, 0.2)
        self.update_details()

    def make_table(self, headers: list, widths) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setStyleSheet("QTableWidget { border: none; background: transparent; }")
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in widths:
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            table.setColumnWidth(column, width)
        return table

    def update_theme_button(self) -> None:
        self.theme_button.setText("☀" if self.theme_name == "dark" else "☾")

    def toggle_theme(self) -> None:
        name = "light" if self.theme_name == "dark" else "dark"
        self.settings.setValue("theme", name)

        def apply():
            QApplication.instance().setStyleSheet(theme.set_theme(name))
            self.update_theme_button()
            self.graph.update()
            self.table.viewport().update()

        crossfade(self, apply)

    def set_category(self, key: str) -> None:
        changed = key != self.current_filter
        self.current_filter = key
        self.proxy.set_category(key)
        if changed:
            fade_in(self.table, 240, 0.25)
        self.page_title.setText(self.page_titles.get(key, key))
        self.update_subtitle()

    def update_subtitle(self) -> None:
        shown = self.proxy.rowCount()
        self.page_sub.setText(f"Показано: {shown} из {len(self.items)}")

    def selected_keys(self) -> list[str]:
        rows = self.table.selectionModel().selectedRows()
        return [self.model.items[self.proxy.mapToSource(i).row()].key for i in rows]

    def selected_infos(self) -> list:
        keys = set(self.selected_keys())
        return [i for i in self.items if i.key in keys]

    def on_selection(self) -> None:
        has = bool(self.selected_keys())
        for button in (self.pause_button, self.resume_button, self.remove_button):
            button.setEnabled(has)
        self.files_key = None
        self.update_details()

    def refresh(self) -> None:
        self.items = self.engine.snapshot()
        self.model.update(self.items)
        target = 1 if self.items else 0
        if self.stack.currentIndex() != target:
            self.stack.setCurrentIndex(target)
            fade_in(self.stack.currentWidget(), 350)

        total_down = sum(i.down_rate for i in self.items)
        total_up = sum(i.up_rate for i in self.items)
        now = time.monotonic()
        elapsed = min(now - self.last_tick, 5.0)
        self.last_tick = now
        self.stats.add(total_down * elapsed, total_up * elapsed)
        self.setWindowTitle(
            f"↓ {fmt_speed(total_down)}  ↑ {fmt_speed(total_up)} — BitClient"
            if (total_down or total_up) else "BitClient")
        self.graph.push(total_down, total_up)
        self.down_label.setText(f"↓ {fmt_speed(total_down)}")
        self.up_label.setText(f"↑ {fmt_speed(total_up)}")

        for key, (button, title) in self.nav_buttons.items():
            count = sum(1 for i in self.items if FilterProxy.matches(key, i))
            button.setText(f"{title}   {count}")
        self.rebuild_dynamic()

        active = sum(1 for i in self.items if i.state == "downloading")
        self.status_left.setText(f"  Торрентов: {len(self.items)}   •   Активных загрузок: {active}")
        self.status_right.setText(
            f"↓ {fmt_speed(total_down)}    ↑ {fmt_speed(total_up)}    "
            f"Всего скачано: {fmt_size(sum(i.total_down for i in self.items))}  ")

        if self.engine.errors:
            for message in self.engine.errors:
                log.warning("%s", message)
            self.statusBar().showMessage(self.engine.errors[-1][:160], 6000)
            self.engine.errors.clear()

        if self.tray is not None:
            self.tray.setToolTip(f"BitClient\n↓ {fmt_speed(total_down)}   ↑ {fmt_speed(total_up)}")
        self.handle_events()
        self.check_after_action()
        self.update_subtitle()
        self.update_details()

    def update_details(self) -> None:
        keys = self.selected_keys()
        info = next((i for i in self.items if keys and i.key == keys[0]), None)
        if info is None:
            for card in self.cards.values():
                card.set_value("—")
            for table in (self.files_table, self.peers_table, self.trackers_table):
                table.setRowCount(0)
            self.files_key = None
            return
        self.cards["down"].set_value(fmt_size(info.total_down))
        self.cards["up"].set_value(fmt_size(info.total_up))
        ratio = info.total_up / info.total_down if info.total_down else 0
        self.cards["ratio"].set_value(f"{ratio:.2f}")
        self.cards["peers"].set_value(f"{info.peers}  ({info.seeds})")
        self.cards["eta"].set_value(
            "—" if info.state in ("completed", "seeding", "paused", "queued") else fmt_eta(info.eta))
        self.cards["path"].set_value(info.save_path)
        index = self.tabs.currentIndex()
        if index == 1:
            self.update_files(info.key)
        elif index == 2:
            self.update_peers(info.key)
        elif index == 3:
            self.update_trackers(info.key)

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
            priority = "Пропуск" if entry.priority == 0 else ("Высокий" if entry.priority >= 7 else "Обычный")
            self.set_cell(self.files_table, row, 3, priority)
            bar = self.files_table.cellWidget(row, 2)
            if bar is not None:
                bar.setValue(int(entry.progress * 1000))
                bar.setFormat(f"{entry.progress * 100:.0f}%")

    def set_cell(self, table: QTableWidget, row: int, column: int, text: str) -> None:
        item = table.item(row, column)
        if item is None:
            table.setItem(row, column, QTableWidgetItem(text))
        elif item.text() != text:
            item.setText(text)

    def update_peers(self, key: str) -> None:
        peers = self.engine.peers(key)
        table = self.peers_table
        if table.rowCount() != len(peers):
            table.setRowCount(len(peers))
            for row in range(len(peers)):
                table.setRowHeight(row, 34)
        for row, peer in enumerate(peers):
            self.set_cell(table, row, 0, peer.address)
            self.set_cell(table, row, 1, peer.client or "—")
            self.set_cell(table, row, 2, fmt_speed(peer.down) if peer.down else "—")
            self.set_cell(table, row, 3, fmt_speed(peer.up) if peer.up else "—")
            self.set_cell(table, row, 4, f"{peer.progress * 100:.0f}%")

    def update_trackers(self, key: str) -> None:
        trackers = self.engine.trackers(key)
        table = self.trackers_table
        if table.rowCount() != len(trackers):
            table.setRowCount(len(trackers))
            for row in range(len(trackers)):
                table.setRowHeight(row, 34)
        for row, tracker in enumerate(trackers):
            self.set_cell(table, row, 0, tracker.url)
            self.set_cell(table, row, 1, tracker.status)
            self.set_cell(table, row, 2, tracker.message or "—")
            self.set_cell(table, row, 3, str(tracker.tier))

    def add_source(self, source: str, save_dir: str | None = None, category: str = "",
                   ask: bool = True) -> bool:
        priorities = None
        try:
            if not source.startswith("magnet:"):
                name, files = self.engine.inspect(source)
                needed = sum(size for _, size in files)
                if ask and len(files) > 1:
                    dialog = FilesDialog(name, [(p, s, 4) for p, s in files], self)
                    if not dialog.exec():
                        return False
                    priorities = dialog.priorities()
                    needed = sum(size for (_, size), pr in zip(files, priorities) if pr > 0)
                if ask and not self.has_space(category, needed):
                    return False
            self.engine.add(source, save_dir or self.save_dir, category, priorities)
            return True
        except Exception as e:
            log.exception("add failed: %s", source[:120])
            QMessageBox.warning(self, "Не удалось добавить", f"{source[:80]}\n\n{e}")
            return False

    def current_category(self) -> str:
        if self.current_filter.startswith("cat:"):
            return self.current_filter[4:]
        return ""

    def add_torrent_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите .torrent файлы", str(Path.home()), "Torrent (*.torrent)")
        for file in files:
            self.add_source(file, category=self.current_category())
        self.refresh()

    def add_magnet(self) -> None:
        dialog = MagnetDialog(self.save_dir, sorted(self.engine.categories),
                              self.current_category(), self)
        clipboard = QGuiApplication.clipboard().text().strip()
        if clipboard.startswith("magnet:"):
            dialog.text.setPlainText(clipboard)
        if dialog.exec():
            for link in dialog.links():
                self.add_source(link, dialog.save_dir(), dialog.category())
            self.refresh()

    def open_settings(self) -> None:
        values = self.config()
        try:
            values["autostart"] = autostart.is_enabled()
        except Exception:
            pass
        dialog = SettingsDialog(values, self)
        if dialog.exec():
            new = dialog.values()
            for key, value in new.items():
                self.settings.setValue(key, value)
            if new["autostart"] != values["autostart"]:
                try:
                    autostart.set_enabled(new["autostart"])
                except Exception as e:
                    self.statusBar().showMessage(f"Автозапуск: {e}", 6000)
            self.engine.apply_config(self.config())
            self.last_limits = None
            self.apply_limits()

    def create_torrent(self) -> None:
        dialog = CreateTorrentDialog(EXTRA_TRACKERS, self)
        if dialog.exec() and dialog.start_seeding():
            parent = str(Path(dialog.source_path()).parent)
            try:
                self.engine.add(dialog.result_path, parent)
            except Exception as e:
                QMessageBox.warning(self, "Не удалось начать раздачу", str(e))
            self.refresh()

    def choose_files(self) -> None:
        infos = self.selected_infos()
        if not infos:
            return
        info = infos[0]
        files = self.engine.files(info.key)
        if not files:
            QMessageBox.information(self, "Файлы", "Метаданные ещё не получены, попробуйте чуть позже.")
            return
        dialog = FilesDialog(info.name, [(f.path, f.size, f.priority) for f in files], self)
        if dialog.exec():
            self.engine.set_file_priorities(info.key, dialog.priorities())
            self.files_key = None
            self.refresh()

    def edit_limits(self) -> None:
        keys = self.selected_keys()
        if not keys:
            return
        down, up = self.engine.torrent_limits(keys[0])
        dialog = LimitsDialog(down / MB, up / MB, self)
        if dialog.exec():
            new_down, new_up = dialog.values()
            for key in keys:
                self.engine.set_torrent_limits(key, int(new_down * MB), int(new_up * MB))

    def recheck_selected(self) -> None:
        for key in self.selected_keys():
            self.engine.recheck(key)
        self.refresh()

    def reannounce_selected(self) -> None:
        for key in self.selected_keys():
            self.engine.reannounce(key)

    def move_in_queue(self, where: str) -> None:
        keys = self.selected_keys()
        for key in (reversed(keys) if where in ("top", "down") else keys):
            self.engine.queue_move(key, where)
        self.refresh()

    def open_schedule(self) -> None:
        dialog = ScheduleDialog(self.load_schedule(), self)
        if dialog.exec():
            self.settings.setValue("schedule", dialog.schedule().to_json())
            self.last_limits = None
            self.apply_limits()

    def open_categories(self) -> None:
        dialog = CategoriesDialog(self.engine.categories, self.save_dir, self)
        if dialog.exec():
            self.engine.set_categories(dialog.categories())
            self.dynamic_signature = None
            self.refresh()

    def open_rss(self) -> None:
        feeds = [dataclasses.replace(f) for f in self.rss.feeds]
        dialog = RssDialog(feeds, sorted(self.engine.categories), self)
        if dialog.exec():
            self.rss.feeds = dialog.feeds()
            self.rss.save()
            self.check_rss(True)

    def check_rss(self, force: bool) -> None:
        if self.rss_running or not self.rss.feeds:
            return
        self.rss_running = True
        feeds = [dataclasses.replace(f) for f in self.rss.feeds]
        seen = list(self.rss.seen)
        directory = STATE_DIR / "rss_torrents"

        def work():
            try:
                result = run_check(feeds, seen, directory, force)
            except Exception as e:
                result = ([], [], {}, [str(e)])
            self.rss_signals.done.emit(result)

        threading.Thread(target=work, daemon=True).start()

    def on_rss_done(self, result) -> None:
        self.rss_running = False
        found, new_seen, states, errors = result
        for guid in new_seen:
            self.rss.seen[guid] = None
        for feed in self.rss.feeds:
            if feed.url in states:
                feed.last_check, feed.primed = states[feed.url]
        self.rss.save()
        for item in found:
            self.add_source(item.source, self.save_dir, item.category, ask=False)
        if found:
            self.statusBar().showMessage(f"RSS: добавлено торрентов — {len(found)}", 8000)
            self.refresh()
        elif errors:
            self.statusBar().showMessage(f"RSS: {errors[0][:140]}", 8000)

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

    def set_sequential_selected(self, enabled: bool) -> None:
        for key in self.selected_keys():
            self.engine.set_sequential(key, enabled)
        self.refresh()

    def set_category_selected(self, category: str) -> None:
        for key in self.selected_keys():
            self.engine.set_category(key, category)
        self.refresh()

    def edit_tags(self) -> None:
        infos = self.selected_infos()
        if not infos:
            return
        current = ", ".join(infos[0].tags)
        text, ok = QInputDialog.getText(
            self, "Метки", "Метки через запятую:", QLineEdit.Normal, current)
        if not ok:
            return
        tags = [t.strip().lstrip("#") for t in text.split(",")]
        for info in infos:
            self.engine.set_tags(info.key, tags)
        self.refresh()

    def show_menu(self, position) -> None:
        infos = self.selected_infos()
        if not infos:
            return
        keys = [i.key for i in infos]
        menu = QMenu(self)
        menu.addAction("▶  Продолжить", self.resume_selected)
        menu.addAction("⏸  Пауза", self.pause_selected)
        menu.addSeparator()
        sequential = menu.addAction("Последовательная загрузка")
        sequential.setCheckable(True)
        sequential.setChecked(all(i.sequential for i in infos))
        sequential.triggered.connect(lambda checked=False: self.set_sequential_selected(checked))
        category_menu = menu.addMenu("Категория")
        category_menu.addAction("— без категории —", lambda: self.set_category_selected(""))
        for name in sorted(self.engine.categories):
            category_menu.addAction(name, lambda _=False, n=name: self.set_category_selected(n))
        menu.addAction("Метки…", self.edit_tags)
        menu.addAction("Выбрать файлы…", self.choose_files)
        menu.addAction("Лимиты скорости…", self.edit_limits)
        queue_menu = menu.addMenu("Очередь")
        queue_menu.addAction("В начало", lambda: self.move_in_queue("top"))
        queue_menu.addAction("Выше", lambda: self.move_in_queue("up"))
        queue_menu.addAction("Ниже", lambda: self.move_in_queue("down"))
        queue_menu.addAction("В конец", lambda: self.move_in_queue("bottom"))
        menu.addAction("Перепроверить файлы", self.recheck_selected)
        menu.addAction("Обновить анонс трекеров", self.reannounce_selected)
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
        category = self.current_category()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith(".torrent"):
                    self.add_source(url.toLocalFile(), category=category)
                elif url.toString().startswith("magnet:"):
                    self.add_source(url.toString(), category=category)
        elif mime.hasText():
            for line in mime.text().splitlines():
                if line.strip().startswith("magnet:"):
                    self.add_source(line.strip(), category=category)
        self.refresh()
        event.acceptProposedAction()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_appeared", False):
            self._appeared = True
            window_fade(self)

    def closeEvent(self, event):
        if not self.really_quit and self.tray is not None and self.config()["tray_close"]:
            event.ignore()
            self.hide()
            if not self.tray_hint_shown:
                self.tray_hint_shown = True
                self.tray.showMessage("BitClient", "Приложение продолжает работать в трее",
                                      QSystemTrayIcon.Information, 4000)
            return
        self.timer.stop()
        self.autosave_timer.stop()
        self.schedule_timer.stop()
        self.rss_timer.stop()
        self.watch_timer.stop()
        self.settings.setValue("header_state", self.table.horizontalHeader().saveState())
        try:
            self.stats.save()
        except OSError:
            pass
        self.shutdown_engine()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
        QApplication.quit()
