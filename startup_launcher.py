"""Launch the isolated Qt6 loading window before starting the Qt5 engine."""

from pathlib import Path
import sys


def write_startup_failure():
    """Keep diagnostics even if Qt itself cannot load and render an error UI."""
    import ctypes
    import json
    import os
    import tempfile
    import traceback

    details = {"error": traceback.format_exc(), "executable": sys.executable,
               "bundle": str(getattr(sys, "_MEIPASS", "")), "loaded_dlls": {}}
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
        for name in ("Qt6Core.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
                     "msvcp140_atomic_wait.dll", "vcruntime140.dll", "vcruntime140_1.dll", "python313.dll"):
            handle = kernel.GetModuleHandleW(name)
            if handle:
                buffer = ctypes.create_unicode_buffer(32768)
                kernel.GetModuleFileNameW(handle, buffer, len(buffer))
                details["loaded_dlls"][name] = buffer.value
    target = os.environ.get("SADM_STARTUP_DIAGNOSTIC_PATH")
    if not target:
        target = str(Path(tempfile.gettempdir()) / "SADM Autorouter" / "launcher-error.json")
    try:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(details, indent=2), encoding="utf-8")
    except OSError:
        pass


def main():
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication
    from frontend.startup_loader import StartupController, StartupWindow

    app = QApplication(sys.argv)
    app.setApplicationName("SADM Autorouter")
    app.setQuitOnLastWindowClosed(False)
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        command = [str(root / "engine" / "SADM Autorouter.exe"), *sys.argv[1:]]
    else:
        command = [sys.executable, str(root / "main.py"), *sys.argv[1:]]
    # A onefile launcher must retain its extracted engine until that process
    # exits. Folder builds can release the Qt6 launcher as soon as Qt5 is ready.
    keep_alive = frozen and root != Path(sys.executable).resolve().parent / "_internal"
    window = StartupWindow()
    icon = root / "assets" / "icons" / "silcrow.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    controller = StartupController(window, command, keep_alive=keep_alive)
    window.first_painted.connect(controller.start)
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        write_startup_failure()
        import os
        if os.environ.get("SADM_STARTUP_DIAGNOSTIC_PATH"):
            sys.exit(1)
        raise
