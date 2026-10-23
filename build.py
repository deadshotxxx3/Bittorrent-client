import os
import subprocess
import sys


def main() -> None:
    separator = os.pathsep
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", "BitClient",
        "--add-data", f"assets{separator}assets",
        "--collect-all", "libtorrent",
        "app.py",
    ]
    subprocess.check_call(command)


if __name__ == "__main__":
    main()
