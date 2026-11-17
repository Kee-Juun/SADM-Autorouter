@echo off
cd /d "%~dp0"
echo Building Autorouter with its loading window and bundled Tesseract...
python build_exe.py %*
if errorlevel 1 (
    echo Build failed. Check the output above.
    pause
    exit /b 1
)
pause
