# SADM Autorouter v2.0 - Distribution Guide

## Overview
This guide explains how to distribute the standalone executable to your coworkers.

## What's Included
The standalone executable (`SADM Autorouter v2.0.exe`) contains:
- ✅ All Python dependencies and libraries
- ✅ Chrome WebDriver manager (auto-downloads driver)
- ✅ All assets (images, gifs, fonts, icons, scores)
- ✅ Configuration files (config.json, user_rewards.json)
- ✅ Utils module (rewards system)
- ✅ Application icon and version info
- ✅ README and requirements files

## System Requirements
- **Operating System**: Windows 10/11 (64-bit)
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Storage**: At least 500MB free space
- **Internet**: Required for Chrome WebDriver download on first run
- **Chrome Browser**: Must be installed (the app will auto-download the appropriate driver)

## Distribution Methods

### Method 1: Direct File Share
1. Copy the executable from `dist\SADM Autorouter v2.0.exe`
2. Share via:
   - Email (if file size allows)
   - File sharing service (OneDrive, Google Drive, Dropbox)
   - Network drive
   - USB drive

### Method 2: Network Installation
1. Place the executable on a shared network drive
2. Create a shortcut on coworkers' desktops
3. Ensure proper network permissions

### Method 3: Company Intranet
1. Upload to company intranet/portal
2. Provide download link to coworkers
3. Include installation instructions

## Installation Instructions for Coworkers

### Step 1: Download
- Download the executable file
- Save to a convenient location (Desktop recommended)

### Step 2: First Run Setup
1. **Double-click** the executable
2. **Allow** Windows Defender/antivirus if prompted
3. **Wait** for initial setup (may take 30-60 seconds on first run)
4. The app will automatically download Chrome WebDriver if needed

### Step 3: Verify Installation
- Application should open with the main interface
- Check that all assets load properly (images, icons)
- Verify Chrome WebDriver download completed

## Troubleshooting

### Common Issues

#### "Windows protected your PC" Message
- Click "More info"
- Click "Run anyway"
- This is normal for unsigned executables

#### Antivirus Blocking
- Add the executable to antivirus exclusions
- Temporarily disable real-time protection during first run
- Contact IT if corporate antivirus blocks it

#### Chrome WebDriver Issues
- Ensure Chrome browser is installed
- Check internet connection
- Try running as administrator

#### Missing Assets
- Ensure the executable is not corrupted during transfer
- Re-download if necessary
- Check file permissions

### Performance Tips
- **First run**: May be slow as it extracts all dependencies
- **Subsequent runs**: Should be much faster
- **Memory usage**: Typically 200-500MB when running
- **Storage**: Creates temporary files during operation

## Security Considerations
- The executable is self-contained and doesn't modify system files
- No registry changes required
- No admin privileges needed for normal operation
- Temporary files are cleaned up automatically

## Support
If coworkers encounter issues:
1. Check this troubleshooting guide
2. Verify system requirements
3. Contact the development team
4. Provide error messages and system information

## Version Information
- **Version**: 2.0
- **Build Date**: [Current Date]
- **File Size**: [Will be shown after build]
- **Compatibility**: Windows 10/11 64-bit

## Updates
- New versions will be distributed as new executables
- No automatic updates - manual replacement required
- Backup any custom configurations before updating

---
*This executable was built with PyInstaller and contains all necessary dependencies for standalone operation.*
