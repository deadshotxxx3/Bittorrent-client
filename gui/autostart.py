import os
import sys
from pathlib import Path

APP_NAME = "BitClient"


def launch_command() -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    entry = Path(__file__).resolve().parent.parent / "app.py"
    return [sys.executable, str(entry)]


def is_enabled() -> bool:
    if sys.platform.startswith("win"):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, APP_NAME)
                return True
        except OSError:
            return False
    return desktop_path().exists()


def desktop_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "bitclient.desktop"


def set_enabled(enabled: bool) -> None:
    command = launch_command()
    if sys.platform.startswith("win"):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                line = " ".join(f'"{part}"' for part in command) + " --minimized"
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, line)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except OSError:
                    pass
        return
    path = desktop_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        exec_line = " ".join(f'"{part}"' for part in command) + " --minimized"
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=BitClient\n"
            f"Exec={exec_line}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
            encoding="utf-8")
    elif path.exists():
        path.unlink()
