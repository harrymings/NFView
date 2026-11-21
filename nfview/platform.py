"""Platform functionality for NFView."""
from __future__ import annotations
import ctypes
import os
import subprocess
import sys
from pathlib import Path


def native_menu_is_active():
    """Whether this UI thread is inside a Windows native menu tracking loop."""
    if sys.platform != "win32":
        return False

    from ctypes import wintypes

    class GUIThreadInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        ]

    info = GUIThreadInfo(cbSize=ctypes.sizeof(GUIThreadInfo))
    thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
    if not ctypes.windll.user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return False
    # GUI_INMENUMODE | GUI_SYSTEMMENUMODE | GUI_POPUPMENUMODE
    return bool(info.flags & 0x1c)


def configure_display():
    """Prevent Windows from bitmap-stretching the Tk window on scaled displays."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NFView.Desktop.Icon3")
    except (AttributeError,OSError):
        pass
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

def open_in_photoshop(path: Path) -> None:
    candidates = []
    for program_files in filter(None, (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles(x86)"))):
        candidates.extend(
            Path(program_files) / "Adobe" / f"Adobe Photoshop {year}" / "Photoshop.exe"
            for year in ("2026", "2025", "2024", "2023", "2022")
        )
    photoshop = next((candidate for candidate in candidates if candidate.exists()), None)
    if photoshop is not None:
        subprocess.Popen([str(photoshop), str(path)])
        return

    if hasattr(os, "startfile"):
        os.startfile(str(path))
        return

    raise FileNotFoundError("Adobe Photoshop was not found, and this platform has no associated-file opener.")
