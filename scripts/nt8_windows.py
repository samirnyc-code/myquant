"""nt8_windows.py — show / hide / toggle ALL NinjaTrader windows together.

NT8 puts the Control Center, each chart and each SuperDOM in its own top-level window, so
Windows treats them as unrelated and you end up restoring them one at a time. This finds
every visible window owned by NinjaTrader.exe and acts on the whole set.

    python scripts/nt8_windows.py            # toggle (any minimised -> show all, else hide)
    python scripts/nt8_windows.py show
    python scripts/nt8_windows.py hide
    python scripts/nt8_windows.py list

Assign a hotkey: make a shortcut to this script, right-click -> Properties -> Shortcut key.
Also wired into the status-light right-click menu.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import sys

user32 = ctypes.windll.user32
SW_MINIMIZE, SW_RESTORE, SW_SHOW = 6, 9, 5

EnumWindowsProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)


def _nt8_windows() -> list[tuple[int, str]]:
    """Visible, titled top-level windows belonging to NinjaTrader.exe."""
    import subprocess

    # PID list for NinjaTrader.exe (CREATE_NO_WINDOW: never flash a console)
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq NinjaTrader.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15, creationflags=0x08000000).stdout
        pids = {int(line.split('","')[1]) for line in out.splitlines() if '","' in line}
    except Exception:
        pids = set()
    if not pids:
        return []

    found: list[tuple[int, str]] = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def show_all() -> int:
    wins = _nt8_windows()
    for hwnd, _ in wins:
        user32.ShowWindow(hwnd, SW_RESTORE)
    # raise the Control Center last so it ends up in front
    for hwnd, title in wins:
        if "Control Center" in title:
            user32.SetForegroundWindow(hwnd)
    return len(wins)


def hide_all() -> int:
    wins = _nt8_windows()
    for hwnd, _ in wins:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
    return len(wins)


def toggle() -> str:
    wins = _nt8_windows()
    if not wins:
        return "no NinjaTrader windows"
    minimised = sum(1 for hwnd, _ in wins if user32.IsIconic(hwnd))
    if minimised:                      # anything hidden -> bring the whole set up
        show_all()
        return f"showed {len(wins)}"
    hide_all()
    return f"hid {len(wins)}"


def main() -> None:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "toggle").lower()
    if cmd == "list":
        for hwnd, title in _nt8_windows():
            state = "min" if user32.IsIconic(hwnd) else "up "
            print(f"  [{state}] {title}")
        return
    print({"show": lambda: f"showed {show_all()}",
           "hide": lambda: f"hid {hide_all()}",
           "toggle": toggle}.get(cmd, toggle)())


if __name__ == "__main__":
    main()
