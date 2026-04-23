"""
Activity Tracker - タスクトレイ常駐型 PC 操作記録ツール
起動: pythonw tracker.py  または  start.bat
"""

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
import pystray
import win32api
import win32con
import win32gui
import win32process
from PIL import Image, ImageDraw

from database import init_db, insert_activity

POLL_INTERVAL = 5       # 秒ごとに記録
IDLE_THRESHOLD = 60     # 秒以上入力なければアイドル扱い
DASHBOARD_SCRIPT = str(Path(__file__).parent / "dashboard.py")


def get_idle_seconds() -> float:
    """最後のキー/マウス入力からの経過秒数"""
    try:
        info = win32api.GetLastInputInfo()
        tick_now = win32api.GetTickCount()
        return (tick_now - info) / 1000.0
    except Exception:
        return 0.0


def get_active_window() -> tuple[str | None, str | None]:
    """(app_name, window_title) を返す。取得失敗時は (None, None)"""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None

        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid <= 0:
            return None, None

        proc = psutil.Process(pid)
        app_name = proc.name().removesuffix(".exe")
        return app_name, title or "(no title)"
    except Exception:
        return None, None


def tracking_loop(stop_event: threading.Event):
    init_db()
    last_time = time.monotonic()

    while not stop_event.is_set():
        now = time.monotonic()
        elapsed = now - last_time
        last_time = now

        if get_idle_seconds() < IDLE_THRESHOLD:
            app_name, window_title = get_active_window()
            if app_name:
                insert_activity(datetime.now(), app_name, window_title, elapsed)

        stop_event.wait(POLL_INTERVAL)


def make_icon_image() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 青い円
    draw.ellipse([4, 4, 60, 60], fill="#1565C0")
    # 白い時計の針っぽい図形
    draw.rectangle([30, 14, 34, 34], fill="white")
    draw.rectangle([30, 30, 46, 34], fill="white")
    return img


LOG_PATH = Path(__file__).parent / "tracker.log"


def log(msg: str):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


_dashboard_proc: subprocess.Popen | None = None


def open_dashboard():
    import webbrowser

    global _dashboard_proc

    # すでに起動済みならブラウザだけ開く
    if _dashboard_proc is not None and _dashboard_proc.poll() is None:
        webbrowser.open("http://localhost:8501")
        return

    try:
        # pythonw.exe → python.exe に差し替え (streamlit は python.exe が必要)
        python_exe = sys.executable.replace("pythonw.exe", "python.exe").replace("pythonw", "python")

        _dashboard_proc = subprocess.Popen(
            [python_exe, "-m", "streamlit", "run", DASHBOARD_SCRIPT,
             "--server.headless", "true",
             "--server.port", "8501"],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        log(f"Dashboard started (pid={_dashboard_proc.pid})")

        # Streamlit 起動を待ってからブラウザを開く
        threading.Timer(4.0, lambda: webbrowser.open("http://localhost:8501")).start()

    except Exception as e:
        log(f"open_dashboard error: {e}")


def main():
    stop_event = threading.Event()

    tracker_thread = threading.Thread(
        target=tracking_loop, args=(stop_event,), daemon=True
    )
    tracker_thread.start()

    menu = pystray.Menu(
        pystray.MenuItem("ダッシュボードを開く", lambda icon, item: open_dashboard()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("終了", lambda icon, item: (stop_event.set(), icon.stop())),
    )

    icon = pystray.Icon(
        name="ActivityTracker",
        icon=make_icon_image(),
        title="Activity Tracker (記録中)",
        menu=menu,
    )

    icon.run()


if __name__ == "__main__":
    main()
