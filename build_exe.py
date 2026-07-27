#!/usr/bin/env python
"""
Build script to create a standalone executable from main.py.
"""
import subprocess
import sys
import os
import shutil

def main():
    print("=" * 60)
    print("Building Standalone Executable")
    print("=" * 60)
    print()
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print("[OK] PyInstaller is installed")
    except ImportError:
        print("[!] PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller installed")
    
    # Clean previous builds
    print("\nCleaning previous builds...")
    if os.path.exists("build"):
        shutil.rmtree("build")
        print("[OK] Removed build directory")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
        print("[OK] Removed dist directory")
    
    # Build the executable
    print("\nBuilding executable from spec file...")
    print("-" * 60)
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller",
            "smducar_pyqt.spec",
            "--clean"
        ])
        
        print("-" * 60)
        print("\n" + "=" * 60)
        print("[OK] Build completed successfully!")
        print("=" * 60)
        print(f"\nYour executable is located in:")
        print(f"  dist\\SADM Autorouter.exe")
        print(f"\nFile size: {os.path.getsize('dist/SADM Autorouter.exe') / (1024*1024):.2f} MB")
        print()
        
    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 60)
        print("[ERROR] Build failed!")
        print("=" * 60)
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

