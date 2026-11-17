# Build separately from the Qt5 engine: PyInstaller supports one Qt binding
# per executable. build_with_loader.py supplies the packaged engine path.
import os
import sys
from importlib.util import find_spec
from pathlib import Path

root = Path(SPECPATH)
sys.path.insert(0, str(root))
from tools.startup_packaging import filter_foreign_windows_icu
engine = Path(os.environ['SADM_ENGINE_EXE']).resolve()
if not engine.is_file():
    raise SystemExit('Build the routing engine first with build_with_loader.py.')
layout = os.environ.get('SADM_LAUNCHER_LAYOUT', 'onedir')
datas = [(str(engine), 'engine')]
icon = root / 'assets' / 'icons' / 'silcrow.ico'
if icon.is_file():
    datas.append((str(icon), 'assets/icons'))
for filename in ('Oxanium-Variable.ttf', 'Oxanium-OFL.txt'):
    datas.append((str(root / 'assets' / 'fonts' / filename), 'assets/fonts'))

a = Analysis(
    [str(root / 'startup_launcher.py')], pathex=[str(root)],
    binaries=[], datas=datas, hiddenimports=[], hookspath=[], runtime_hooks=[],
    excludes=['PyQt5', 'PySide6', 'PySide2', 'PyQt4', 'PySide'],
)
qt_bin = Path(next(iter(find_spec('PyQt6').submodule_search_locations))) / 'Qt6' / 'bin'
a.binaries = filter_foreign_windows_icu(
    a.binaries,
    use_windows_icu=sys.platform == 'win32' and not (qt_bin / 'icuuc.dll').is_file(),
)
pyz = PYZ(a.pure)
options = dict(name='SADM Autorouter', console=False, upx=False,
               icon=str(icon) if icon.is_file() else None)
if layout == 'onefile':
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)
    bundle = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                     name='SADM Autorouter')
