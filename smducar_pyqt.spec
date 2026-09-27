# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# IMPORTANT: Python 3.13 has a known compatibility issue with PyInstaller
# If you encounter "AttributeError: class must define a '_type_' attribute",
# please use Python 3.11 or 3.12 instead. See PYTHON_3.13_FIX.md for details.
# The build_exe.bat script uses Python 3.12 to avoid this issue.

# Collect data files (assets, config, etc.)
datas = []
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))
if os.path.exists('config'):
    datas.append(('config', 'config'))
if os.path.exists('silcrow.ico'):
    datas.append(('silcrow.ico', '.'))
if os.path.exists('tetris_highscore.txt'):
    datas.append(('tetris_highscore.txt', '.'))
if os.path.exists('utils'):
    datas.append(('utils', 'utils'))

# Bundle Tesseract itself, not only the pytesseract Python wrapper.  The
# runtime is placed where core.mspb_extractor looks for it in a frozen build:
# sys._MEIPASS/tesseract/tesseract.exe.  This lets OCR work on a recipient's
# computer even when Tesseract is not installed globally.
def find_tesseract_runtime():
    configured_root = os.environ.get('TESSERACT_HOME')
    candidates = [
        Path(configured_root) if configured_root else None,
        Path(r'C:\Program Files\Tesseract-OCR'),
        Path(r'C:\Program Files (x86)\Tesseract-OCR'),
    ]
    for candidate in candidates:
        if candidate and (candidate / 'tesseract.exe').is_file() and (candidate / 'tessdata').is_dir():
            return candidate
    raise SystemExit(
        'Tesseract runtime was not found. Install it on the build computer or set TESSERACT_HOME '
        'to the folder containing tesseract.exe and tessdata before building.'
    )


tesseract_root = find_tesseract_runtime()
datas.append((str(tesseract_root / 'tesseract.exe'), 'tesseract'))
datas.extend((str(runtime_dll), 'tesseract') for runtime_dll in tesseract_root.glob('*.dll'))
datas.append((str(tesseract_root / 'tessdata'), 'tesseract/tessdata'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'win32timezone',  # Required for pywin32
        'win32api',
        'win32con',
        'win32gui',
        'utils.filename_patterns',  # Filename pattern utilities
        'utils.rewards',  # Rewards system
        'smducar',  # Main automation module
        'openpyxl',  # Excel handling
        'selenium',  # Web automation
        'selenium.webdriver.chrome.webdriver',  # Concrete Chrome WebDriver class for frozen builds
        'PyQt5',  # GUI framework
        'pyqt_utils',  # PyQt utility functions
        'pyqt_widgets',  # PyQt custom widgets
        'pyqt_dialogs',  # PyQt dialog classes
        'pypdf',  # MSPB PDF text extraction
        'pdf2image',  # Optional MSPB OCR fallback
        'pytesseract',  # Optional MSPB OCR fallback
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SADM Autorouter',
    icon='silcrow.ico' if os.path.exists('silcrow.ico') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
