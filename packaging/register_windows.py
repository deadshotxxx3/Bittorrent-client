import sys
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.autostart import launch_command


def write(path: str, name: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def main() -> None:
    command = " ".join(f'"{part}"' for part in launch_command()) + ' "%1"'
    write(r"Software\Classes\.torrent", "", "BitClient.torrent")
    write(r"Software\Classes\BitClient.torrent", "", "Torrent file")
    write(r"Software\Classes\BitClient.torrent\shell\open\command", "", command)
    write(r"Software\Classes\magnet", "", "URL:Magnet link")
    write(r"Software\Classes\magnet", "URL Protocol", "")
    write(r"Software\Classes\magnet\shell\open\command", "", command)
    print("BitClient registered for .torrent files and magnet links")


if __name__ == "__main__":
    main()
