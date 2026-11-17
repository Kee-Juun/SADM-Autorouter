"""Optional native frosted glass for the isolated, layered Qt window."""

import ctypes
import sys


def enable_acrylic(hwnd, *, rounded=True):
    """Request native background blur; callers retain a translucent fallback."""
    if sys.platform != "win32" or sys.getwindowsversion().build < 17763:
        return False
    try:
        from ctypes import wintypes

        class Margins(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int) for name in ("left", "right", "top", "bottom")]

        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(Margins)]
        dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long

        def attribute(key, value):
            data = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, key, ctypes.byref(data), ctypes.sizeof(data))

        attribute(20, 1)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        attribute(33, 2 if rounded else 1)  # DWMWA_WINDOW_CORNER_PREFERENCE
        margins = Margins(-1, -1, -1, -1)
        extended = dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        # Qt's translucent raster windows use WS_EX_LAYERED. Accent Acrylic
        # composes the desktop behind that surface; a system-backdrop request
        # alone can return success yet leave a flat background on these windows.
        class Accent(ctypes.Structure):
            _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int),
                        ("tint", wintypes.DWORD), ("animation", ctypes.c_int)]

        class Composition(ctypes.Structure):
            _fields_ = [("attribute", ctypes.c_int), ("data", ctypes.c_void_p),
                        ("size", ctypes.c_size_t)]

        user = ctypes.WinDLL("user32")
        compose = getattr(user, "SetWindowCompositionAttribute", None)
        if compose is not None:
            compose.argtypes = [wintypes.HWND, ctypes.POINTER(Composition)]
            compose.restype = wintypes.BOOL
            accent = Accent(4, 0, 0x40231C1C, 0)  # Acrylic; a light charcoal ABGR tint.
            data = Composition(19, ctypes.addressof(accent), ctypes.sizeof(accent))
            if compose(hwnd, ctypes.byref(data)):
                return True

        # Supported Windows 11 backdrop as a fallback when Accent is unavailable.
        applied = attribute(38, 3)
        return extended == 0 and applied == 0
    except (AttributeError, OSError):
        return False
