# SADM Autorouter - Build Instructions

## Prerequisites

1. **Python 3.12 or 3.13** installed on your system
2. **pip** (Python package installer)
3. **Windows OS** (the application is designed for Windows)

## Quick Build (Recommended)

### Option 1: Automated Build Script
1. **Double-click** `build_exe.bat` to run the automated build script
2. Wait for the build to complete
3. The single executable will be created as `dist/SADM Autorouter.exe`.

### Option 2: Python Build Script
1. Run `python build_exe.py` for the existing single-EXE format.
2. Run `python build_exe.py --onedir` for the earlier loading window in a folder build.

Use the same Python installation to install dependencies and run the build.

## Manual Build

If you prefer to build manually, follow these steps:

### 1. Install Dependencies
```bash
python -m pip install -r requirements.txt python-docx
```

### 2. Build with the Earliest Loading Window (Folder Format)
```bash
set "TESSERACT_HOME=C:\Program Files\Tesseract-OCR"
python build_with_loader.py --onedir
```

### 3. Find Your Executable
The executable will be created as:
```
dist/SADM Autorouter/SADM Autorouter.exe
```

## What's Included

The executable includes:
- ✅ **All Python dependencies** (PyQt5 engine, isolated PyQt6 loader, Selenium, etc.)
- ✅ **Chrome WebDriver manager** (automatically downloads ChromeDriver)
- ✅ **All assets** (images, GIFs, fonts, icons)
- ✅ **Configuration files** (config.json)
- ✅ **Application icon** (silcrow.ico)
- ✅ **High score file** (tetris_highscore.txt)
- ✅ **Tesseract OCR runtime and language data** (recipients do not need Tesseract installed)
- ✅ **Movable, minimizable startup window** shown during EXE extraction and app initialization
- ✅ **Version information** (file_version_info.txt)

The build computer must have Tesseract installed. The build searches the standard
Windows install folders or the optional `TESSERACT_HOME` environment variable,
then packages `tesseract.exe`, its required DLLs, and `tessdata` into the EXE.

The PyQt6 startup window is a compact 360 x 144 card with softly rounded dark
glass, the app's Silcrow icon, its full name, and a continuous loading sweep.
There is no secondary background window, decorative frame, or instructional
footer. It uses the bundled Oxanium variable font, with its SIL Open Font License
included in the launcher. A very brief, subtle icon glitch appears after two
seconds, then at random intervals of roughly 7-11 seconds. The whole card also
briefly glitches with separated red/green/blue channels and horizontal fractures
that also deform the native glass outline. Each displaced slice is composited
once with its original opacity, avoiding dark scanline bands:
a 175 ms burst after about three seconds, then a random 9-15 second rest between
bursts. This affects the rendered card and its children, including the title,
percentage and bar, while their actual data and input positions stay unchanged.
Animation pauses while minimized and stops on completion or failure. The glass
also catches an occasional faint cyan-to-violet sheen: a smooth 2.4-second pass
under the content, followed by an 8-13 second rest. It does not animate text or
controls, and it shares the same minimize/completion/failure lifecycle.
The glass uses the console's charcoal palette and translucent surface, with a lighter tint
over native Acrylic so the frost stays visible. A rounded window region keeps
the blur inside the card. Native blur is optional; a translucent painted surface
remains when Windows does not support it.

The window reports real
stages: preparing app files, loading libraries, loading fonts/images, and building
the workspace. A large `70%` display and the filled loading bar show a weighted
estimate based on reported milestones; the percentage tooltip explains this.
They advance only on stage updates,
never move backward, and reach 100% only after the main UI is ready. This is not
an elapsed-time estimate: extraction and some imports can stay on one stage
longer than others. Drag its header/body to move it, use the minimize control, and
restore it from the taskbar. It runs in a separate process, so loading the PyQt5
engine cannot freeze its animation or controls. It hides only after the main
window has painted; startup failures remain visible with a Close control.
The launcher waits for its own first paint before starting the engine. File
access and process creation run in a worker thread, so a slow Windows launch or
security scan cannot hold the splash at an empty glass frame or freeze its controls.

The two Qt bindings are packaged separately to avoid incompatible Qt hooks and
plugin paths. `build_with_loader.py` builds the original `smducar_pyqt.spec` engine
first, then packages it with `startup_launcher.spec`. Each build uses fresh work
directories instead of deleting an existing cache.

The launcher spec also excludes unrelated, unversioned ICU DLLs discovered on
PATH when the Qt wheel expects Windows' ICU implementation. This prevents a
Poppler installation from shadowing Windows ICU and causing a QtCore DLL import
error. Failures occurring before Qt can display a window are recorded in
`%TEMP%/SADM Autorouter/launcher-error.json`.

The folder build displays its loader before the large engine unpacks. To retain
a single distributable EXE (the default), use `python build_with_loader.py --onefile`; output is
`dist/SADM Autorouter.exe`. That version must unpack the launcher and its payload
before PyQt6 can show a window, so it retains an initial blank delay. Neither
option can display a UI before Windows finishes its initial security checks.

For a source preview, run `python startup_launcher.py`. Starting `main.py` directly
continues to work as an engine-only launch.

To verify the UI and a separate test-only Qt5 process without routing or sending
email, run `python tools/verify_startup_loader.py --offscreen`. Omit `--offscreen`
for a brief native Windows preview.
Run `python tools/verify_startup_launch.py` to verify the real first frame and
responsive controls while process creation is deliberately held up. This uses
the test-only Qt5 engine and does not start routing or send email.
Add `--record-preview` to save an animated capture of only the startup widget
in `output/startup-check`. Previews do not create a backdrop. Widget recordings
contain the translucent paint, but Windows' compositor supplies the live frost.
Use `--native-capture` for an optional capture inside the loader's bounds that
also includes that material.

## Distribution

To distribute the application:
1. Copy the entire `dist/SADM Autorouter` folder, including `_internal`.
2. Keep the executable and its supporting folder together.
3. Users run `SADM Autorouter.exe` inside that folder.

For a `--onefile` build, distribute only `dist/SADM Autorouter.exe`.

## Troubleshooting

### Common Issues:

1. **"Missing module" errors**: Run `pip install -r requirements.txt` to ensure all dependencies are installed
2. **Large file size**: This is normal - the executable includes Chrome WebDriver and all dependencies
3. **Antivirus warnings**: Some antivirus software may flag PyInstaller executables - this is a false positive
4. **Chrome not found**: The application will automatically download ChromeDriver when needed

### Build Errors:

If the build fails:
1. Check that all files are present in the project directory
2. Ensure you have sufficient disk space (at least 2GB free)
3. Try running the build script as administrator
4. Check the console output for specific error messages

## File Structure

```
project/
├── main.py                  # Application entrypoint
├── core/smducar.py          # Core automation logic
├── smducar_pyqt.spec        # PyInstaller specification
├── build_exe.bat            # Automated build script
├── requirements.txt         # Python dependencies
├── silcrow.ico             # Application icon
├── file_version_info.txt   # Version information
├── tetris_highscore.txt    # Tetris high scores
├── assets/                 # Application assets
│   ├── images/            # Image files
│   ├── gifs/              # Animated GIFs
│   ├── icons/             # Icon files
│   └── fonts/             # Custom fonts
└── config/                # Configuration files
    └── config.json        # Application settings
```

## Support

If you encounter any issues during the build process, please check:
1. Python version compatibility
2. All required files are present
3. Sufficient disk space
4. Antivirus software interference 
