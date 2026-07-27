# SADM Autorouter - Build Instructions

## Prerequisites

1. **Python 3.8 or higher** installed on your system
2. **pip** (Python package installer)
3. **Windows OS** (the application is designed for Windows)

## Quick Build (Recommended)

### Option 1: Automated Build Script
1. **Double-click** `build_exe.bat` to run the automated build script
2. Wait for the build to complete
3. The executable will be created in the `dist` folder

### Option 2: Simple Build Script
1. **Double-click** `build_exe_simple.bat` for a quick build
2. This uses Python 3.12 directly (recommended to avoid Python 3.13 compatibility issues)

**Note**: The build scripts are configured to use Python 3.12 to avoid compatibility issues with PyInstaller. If you need to use a different Python version, edit the batch file.

## Manual Build

If you prefer to build manually, follow these steps:

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Build the Executable
```bash
pyinstaller --clean smducar_pyqt.spec
```

### 3. Find Your Executable
The executable will be created as:
```
dist/SADM Autorouter.exe
```

## What's Included

The executable includes:
- ✅ **All Python dependencies** (PyQt5, Selenium, etc.)
- ✅ **Chrome WebDriver manager** (automatically downloads ChromeDriver)
- ✅ **All assets** (images, GIFs, fonts, icons)
- ✅ **Configuration files** (config.json)
- ✅ **Application icon** (silcrow.ico)
- ✅ **High score file** (tetris_highscore.txt)
- ✅ **Version information** (file_version_info.txt)

## Distribution

To distribute the application:
1. Copy the entire `dist` folder
2. The folder contains everything needed to run the application
3. Users can run `SADM Autorouter.exe` directly

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
