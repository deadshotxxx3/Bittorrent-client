from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)


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


class MagnetDialog(QDialog):
    def __init__(self, default_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить magnet-ссылку")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        title = QLabel("Magnet-ссылки")
        title.setObjectName("pageTitle")
        hint = QLabel("Вставьте одну или несколько ссылок, по одной на строку")
        hint.setObjectName("muted")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("magnet:?xt=urn:btih:…")
        self.text.setMinimumHeight(120)
        self.folder = FolderRow(default_dir, self)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Добавить")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.text)
        layout.addWidget(QLabel("Сохранять в"))
        layout.addLayout(self.folder)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    def links(self) -> list[str]:
        return [line.strip() for line in self.text.toPlainText().splitlines()
                if line.strip().startswith("magnet:")]

    def save_dir(self) -> str:
        return self.folder.path()


class SettingsDialog(QDialog):
    def __init__(self, save_dir: str, down_mb: float, up_mb: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        title = QLabel("Настройки")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.folder = FolderRow(save_dir, self)
        self.down = QDoubleSpinBox()
        self.down.setRange(0, 10000)
        self.down.setDecimals(1)
        self.down.setSuffix(" МБ/с")
        self.down.setSpecialValueText("без лимита")
        self.down.setValue(down_mb)
        self.up = QDoubleSpinBox()
        self.up.setRange(0, 10000)
        self.up.setDecimals(1)
        self.up.setSuffix(" МБ/с")
        self.up.setSpecialValueText("без лимита")
        self.up.setValue(up_mb)
        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Папка по умолчанию", self._wrap(self.folder))
        form.addRow("Лимит скачивания", self.down)
        form.addRow("Лимит отдачи", self.up)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Сохранить")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addSpacing(6)
        layout.addLayout(buttons)

    @staticmethod
    def _wrap(row):
        from PySide6.QtWidgets import QWidget
        holder = QWidget()
        row.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(row)
        return holder

    def values(self) -> tuple[str, float, float]:
        return self.folder.path(), self.down.value(), self.up.value()
