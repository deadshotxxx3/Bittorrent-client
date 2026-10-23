import subprocess
import sys


def run_power_action(name: str) -> None:
    if name == "shutdown":
        if sys.platform.startswith("win"):
            subprocess.Popen(["shutdown", "/s", "/t", "0"])
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
        else:
            subprocess.Popen(["systemctl", "poweroff"])
    elif name == "sleep":
        if sys.platform.startswith("win"):
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif sys.platform == "darwin":
            subprocess.Popen(["pmset", "sleepnow"])
        else:
            subprocess.Popen(["systemctl", "suspend"])
