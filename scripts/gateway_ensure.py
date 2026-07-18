"""Ensure IB Gateway is logged in (paper, port 4002) — launch IBC if it's down
and wait for the API port. Idempotent: safe to call any time a script (or a
session) needs Gateway. Uses the credentials already in C:\\IBC\\config.ini
(never in the repo or chat).

  .venv/Scripts/python.exe scripts/gateway_ensure.py
Exit 0 = Gateway up and reachable; 1 = failed to come up.
"""
import socket
import subprocess
import sys
import time


def port_up(host="127.0.0.1", port=4002, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def main():
    if port_up():
        print("gateway already up (paper 4002)")
        return 0
    print("gateway down — launching IBC auto-login (C:\\IBC\\StartGateway.bat)...")
    try:
        subprocess.Popen(["cmd", "/c", r"C:\IBC\StartGateway.bat", "/INLINE"],
                         creationflags=0x08000000)  # CREATE_NO_WINDOW, detached
    except Exception as e:
        print(f"could not launch IBC: {e}")
        return 1
    for i in range(60):  # up to ~120s (JVM + login + connect)
        time.sleep(2)
        if port_up():
            print(f"gateway UP after ~{(i + 1) * 2}s (paper 4002)")
            return 0
    print("gateway did NOT come up within ~120s — check C:\\IBC\\Logs and credentials.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
