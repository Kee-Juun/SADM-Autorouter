# Building the Executable

## Quick Start

### Option 1: Automated Build (Recommended)
1. **Double-click `build_exe.bat`**
   - Automatically creates Python 3.12 virtual environment if needed
   - Installs all dependencies
   - Builds the executable
   - Uses clean Python 3.12 environment (avoids Python 3.13 DLL conflicts)

### Option 2: Simple Build
1. **First time**: Run `setup_python312_env.bat` to create the virtual environment
2. **Then**: Double-click `build_exe_simple.bat` for quick builds

## Why Python 3.12?

Your code doesn't require Python 3.13, but if packages were installed with Python 3.13, they reference `python313.dll` which conflicts with Python 3.12. Using a clean Python 3.12 virtual environment ensures all packages are built with Python 3.12 and use `python312.dll` instead.

## Build Process

The `build_exe.bat` script:
1. ✅ Checks for Python 3.12 installation
2. ✅ Creates virtual environment (`venv312`) if it doesn't exist
3. ✅ Installs/upgrades all dependencies in the clean environment
4. ✅ Cleans previous builds
5. ✅ Builds the executable using PyInstaller
6. ✅ Outputs to `dist\SADM Autorouter.exe`

## Troubleshooting

### "Virtual environment not found"
- Run `setup_python312_env.bat` first, or
- Use `build_exe.bat` which creates it automatically

### "Module use of python313.dll conflicts"
- Delete the `venv312` folder
- Run `build_exe.bat` again to recreate with clean Python 3.12

### Build fails
- Check that Python 3.12 is installed at:
  `C:\Users\libunak\AppData\Local\Programs\Python\Python312\python.exe`
- Ensure you have internet connection (for downloading packages)
- Check disk space (build requires ~2GB free)

## Manual Build

If you prefer manual control:

```batch
REM 1. Create virtual environment
C:\Users\libunak\AppData\Local\Programs\Python\Python312\python.exe -m venv venv312

REM 2. Activate it
venv312\Scripts\activate

REM 3. Install dependencies
pip install -r requirements.txt

REM 4. Build
pyinstaller --clean smducar_pyqt.spec
```

## Output

The executable will be created at:
```
dist\SADM Autorouter.exe
```

This is a standalone executable that includes all dependencies and can be distributed without requiring Python installation on the target machine.

