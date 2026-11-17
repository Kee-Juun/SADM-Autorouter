"""Build the Qt5 routing engine and isolated Qt6 launcher with Tesseract."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    layout = parser.add_mutually_exclusive_group()
    layout.add_argument('--onefile', dest='layout', action='store_const', const='onefile', help='Single EXE (default); must unpack before the Qt6 loader appears.')
    layout.add_argument('--onedir', dest='layout', action='store_const', const='onedir', help='Folder build with the earliest Qt6 loading window.')
    parser.set_defaults(layout='onefile')
    parser.add_argument('--distpath', default='dist')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    work = Path(tempfile.mkdtemp(prefix='SADM-package-'))
    dist = Path(args.distpath).resolve()
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm']
    print('Building the routing engine with bundled Tesseract...', flush=True)
    subprocess.run(command + [
        '--workpath', str(work / 'engine-work'), '--distpath', str(work / 'engine-dist'),
        str(root / 'smducar_pyqt.spec'),
    ], cwd=root, check=True)
    env = dict(os.environ)
    env['SADM_ENGINE_EXE'] = str(work / 'engine-dist' / 'SADM Autorouter.exe')
    env['SADM_LAUNCHER_LAYOUT'] = args.layout
    print('Building the separate PyQt6 loading window...', flush=True)
    subprocess.run(command + [
        '--workpath', str(work / 'launcher-work'), '--distpath', str(dist),
        str(root / 'startup_launcher.spec'),
    ], cwd=root, env=env, check=True)
    result = dist / ('SADM Autorouter.exe' if args.layout == 'onefile' else 'SADM Autorouter/SADM Autorouter.exe')
    print(f'Build complete: {result}', flush=True)
    if args.layout == 'onedir':
        print('Distribute the entire SADM Autorouter folder, including _internal.', flush=True)


if __name__ == '__main__':
    main()
