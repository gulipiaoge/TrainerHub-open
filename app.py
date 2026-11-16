# -*- coding: utf-8 -*-
"""TrainerHub 桌面端入口 —— pywebview 窗口 + JS 桥接"""
import os
import sys
from pathlib import Path

import webview

from backend import Backend

BASE = Path(__file__).resolve().parent
WEB_DIR = BASE / "web"
INDEX = WEB_DIR / "index.html"
ICON = BASE / "icon.ico"

WINDOW_TITLE = "TrainerHub · 修改器管理器"

# 单实例互斥体句柄，必须全局持有；一旦被 GC 回收，锁会自动释放而失效
_SINGLE_INSTANCE_HANDLE = None


def acquire_single_instance():
    """Windows 命名互斥体实现单实例。返回 True 表示可以启动，False 表示已有实例。
    非 Windows 或任何异常一律放行，避免误伤正常启动。"""
    global _SINGLE_INSTANCE_HANDLE
    if os.name != "nt":
        return True
    try:
        # 跳过 WebView2 派生的子进程（spawn 会重新 import 本模块）
        import multiprocessing
        if multiprocessing.current_process().name != "MainProcess":
            return True
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        h = k32.CreateMutexW(None, True, "Local\\TrainerHub_SingleInstance")
        if not h:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            k32.CloseHandle(h)
            return False
        _SINGLE_INSTANCE_HANDLE = h
        return True
    except Exception:
        return True


def focus_existing_window():
    """已有实例时把它的窗口还原并置前，让用户看到"它其实开着"。
    只用非阻塞的窗口操作，绝不弹模态框（pythonw 下会挂住后台任务）。"""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u.FindWindowW.restype = wintypes.HWND
        hwnd = u.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            u.ShowWindow(hwnd, 9)        # SW_RESTORE
            u.SetForegroundWindow(hwnd)
    except Exception:
        pass


def apply_window_icon():
    """把项目内的紫色 icon.ico 设为窗口/任务栏图标。
    pywebview 的 create_window 没有 icon 参数，故用 Windows API 在窗口显示后设置。
    失败时静默跳过，不影响主程序。"""
    if os.name != "nt" or not ICON.exists():
        return
    try:
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        # FindWindowW(LPCWSTR, LPCWSTR) -> HWND
        u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        u.FindWindowW.restype = wintypes.HWND
        # LoadImageW(HINSTANCE, LPCWSTR, UINT, int, int, UINT) -> HANDLE
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                 wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.LoadImageW.restype = wintypes.HANDLE
        # SendMessageW(HWND, UINT, WPARAM, LPARAM) -> LRESULT
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]
        u.SendMessageW.restype = ctypes.c_ssize_t

        hwnd = u.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return
        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
        WM_SETICON = 0x0080
        ICON_SMALL, ICON_BIG = 0, 1
        # 大图标给任务栏/Alt+Tab，小图标给标题栏
        for which, size in ((ICON_BIG, 64), (ICON_SMALL, 32)):
            hicon = u.LoadImageW(None, str(ICON), IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if hicon:
                u.SendMessageW(hwnd, WM_SETICON, which, hicon)
                # 不 DestroyIcon：窗口仍持有该句柄，退出时由系统回收
    except Exception:
        pass

api = Backend()

# 把常用的文件对话框也桥接给前端
class JsApi(Backend):
    def pick_files(self):
        """打开文件选择对话框，返回选中的文件路径列表"""
        try:
            win = webview.windows[0] if webview.windows else None
            if not win:
                return []
            result = win.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=("可执行文件 (*.exe)", "压缩包 (*.zip)", "所有文件 (*.*)"),
            )
            if not result:
                return []
            return list(result) if isinstance(result, (tuple, list)) else [result]
        except Exception:
            return []

    def pick_mod_files(self):
        """打开 Mod 文件选择对话框（不过滤扩展名，.pak/.lua/.zip 等都能选）"""
        try:
            win = webview.windows[0] if webview.windows else None
            if not win:
                return []
            result = win.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=True,
                file_types=("所有文件 (*.*)",),
            )
            if not result:
                return []
            return list(result) if isinstance(result, (tuple, list)) else [result]
        except Exception:
            return []

    def pick_folder(self):
        """打开文件夹选择对话框，返回选中的目录路径"""
        try:
            win = webview.windows[0] if webview.windows else None
            if not win:
                return ""
            result = win.create_file_dialog(webview.FOLDER_DIALOG)
            if not result:
                return ""
            return result[0] if isinstance(result, (tuple, list)) else result
        except Exception:
            return ""

    def pick_game_exe(self):
        """选择游戏本体 exe（用于启动游戏）"""
        try:
            win = webview.windows[0] if webview.windows else None
            if not win:
                return ""
            result = win.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("可执行文件 (*.exe)", "所有文件 (*.*)"))
            if not result:
                return ""
            return result[0] if isinstance(result, (tuple, list)) else result
        except Exception:
            return ""


js_api = JsApi()


def main():
    if not INDEX.exists():
        print("找不到界面文件:", INDEX)
        sys.exit(1)
    if not acquire_single_instance():
        focus_existing_window()
        sys.exit(0)
    window = webview.create_window(
        title=WINDOW_TITLE,
        url=str(INDEX),
        js_api=js_api,
        width=1120,
        height=760,
        min_size=(880, 600),
        resizable=True,
        background_color="#12141c",
        confirm_close=False,
        text_select=True,
    )
    # 窗口显示后套用自定义图标（任务栏 + 标题栏）
    window.events.shown += apply_window_icon
    # Windows 优先使用 Edge WebView2（系统自带，无需额外安装）
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
