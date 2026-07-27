# SADM Autorouter v2.1 - Distribution Guide

## 🚀 What's New in Version 2.1

### Enhanced ARC Document Support
- **ARC documents are now treated as counsel files** - any filename containing "arc" (case-insensitive) will be processed as counsel
- **Automatic attachment logic** - ARC documents and CSV counsel files are automatically attached to matching main opinion documents
- **Improved batch processing** - Better filename handling and document grouping by docket number

### Example Usage
For files like:
- Main opinion: `dar_2-24CV249_AZD_61_20250925_141439005.pdf`
- Counsel file: `dar_2-24cv249_AZD_Counsel.csv`
- ARC document: `dar_2-24CV249_ARC_AZD_62_20250925_141439005.pdf`

The system will automatically:
1. ✅ Detect the ARC document as counsel (even though it's a PDF)
2. ✅ Group all files by docket number (24-249)
3. ✅ Attach both counsel CSV and ARC PDF to the main opinion
4. ✅ Process everything in the correct order

---

## 📦 For Coworkers - How to Use the Executable

### System Requirements
- **Windows 10/11** (64-bit recommended)
- **Chrome browser** (latest version recommended)
- **Internet connection** (for Chrome WebDriver auto-download)
- **Administrator privileges** (for first-time setup)

### Installation & Setup
1. **Download** the `SADM Autorouter v2.1.exe` file
2. **Place it** in a folder of your choice (e.g., `C:\SMD_AutoRouter\`)
3. **Double-click** to run - no installation required!

### First-Time Setup
1. **Run as Administrator** (right-click → "Run as administrator")
2. The application will automatically download Chrome WebDriver on first run
3. You may see Windows Defender warnings - click "More info" → "Run anyway"

### Daily Usage
1. **Double-click** the executable to start
2. **Select your mode**: DAR, SMD, or WC
3. **Choose your Excel mapping file**
4. **Start processing** - the application handles everything automatically

---

## 🔧 Technical Details

### What's Included in the Executable
The standalone executable contains **everything** needed to run:

#### Core Components
- ✅ **Python runtime** (embedded)
- ✅ **All Python libraries** (selenium, pandas, openpyxl, etc.)
- ✅ **Chrome WebDriver manager** (auto-downloads driver)
- ✅ **PyQt5 GUI framework**

#### Application Assets
- ✅ **All images, gifs, fonts, and icons**
- ✅ **Configuration files** (config.json, user_rewards.json)
- ✅ **Excel templates** and mapping sheets
- ✅ **Documentation** (README files, guides)

#### New v2.1 Modules
- ✅ **Enhanced ARC document support**
- ✅ **WC Automation modules** (data processing, validation)
- ✅ **Core automation workflow** modules
- ✅ **Batch processing** functionality
- ✅ **Improved attachment logic**

### File Size
- **Expected size**: ~150-200 MB (includes all dependencies)
- **Self-contained**: No additional downloads required after initial setup

---

## 🚨 Troubleshooting

### Common Issues & Solutions

#### "Windows Defender blocked this app"
**Solution**: 
1. Click "More info"
2. Click "Run anyway"
3. Or add to Windows Defender exclusions

#### "Chrome WebDriver not found"
**Solution**:
1. Ensure internet connection
2. Run as Administrator
3. Check Chrome browser is installed

#### "Permission denied" errors
**Solution**:
1. Run as Administrator
2. Move executable to a folder you have write access to
3. Check antivirus isn't blocking the application

#### Application crashes or freezes
**Solution**:
1. Close all Chrome browser windows
2. Restart the application
3. Check system resources (RAM/CPU)

### Getting Help
- **Check the logs**: Look for `debug.log` in the application folder
- **Contact IT support**: Share the log file if issues persist
- **Version info**: Right-click executable → Properties → Details

---

## 📋 Usage Instructions

### Step 1: Prepare Your Files
1. **Create Excel mapping file** with columns:
   - `LNI`, `FileName`, `Comments`, `RecycledCounselLNI`
2. **Place documents** in the same folder as Excel file
3. **Ensure filenames** follow the naming convention

### Step 2: Run the Application
1. **Launch** `SADM Autorouter v2.1.exe`
2. **Select mode** (DAR recommended for new ARC functionality)
3. **Choose Excel file** using the file browser
4. **Click "Start Processing"**

### Step 3: Monitor Progress
- **Real-time progress** shown in the interface
- **Detailed logs** available in the console
- **Status updates** for each document processed

### Step 4: Review Results
- **Check Excel file** for updated status columns
- **Review any error messages** in the logs
- **Verify attachments** were created correctly

---

## 🔄 ARC Document Processing

### How ARC Documents Work
1. **Detection**: Any filename containing "arc" (case-insensitive) is treated as counsel
2. **Grouping**: Files are grouped by docket number extracted from filename
3. **Attachment**: ARC documents are attached to main opinion documents
4. **Processing**: ARC documents are processed with the same logic as counsel files

### Example Filename Patterns
```
✅ Main Opinion: dar_2-24CV249_AZD_61_20250925_141439005.pdf
✅ Counsel CSV:  dar_2-24cv249_AZD_Counsel.csv
✅ ARC Document: dar_2-24CV249_ARC_AZD_62_20250925_141439005.pdf
```

### Comments Field Population
- **Main Opinion**: Only additional comments from Excel (uses Related LNI field for attachments)
- **Counsel Files**: Main opinion LNI + additional comments
- **ARC Documents**: Main opinion LNI + additional comments (same as counsel)

---

## 📞 Support Information

### Version Details
- **Application**: SADM Autorouter v2.1
- **Build Date**: January 2025
- **New Features**: Enhanced ARC support, improved batch processing

### File Locations
- **Executable**: `SADM Autorouter v2.1.exe`
- **Logs**: `debug.log` (in same folder as executable)
- **Configuration**: Embedded in executable

### Performance Notes
- **Memory Usage**: ~200-300 MB during processing
- **Processing Speed**: Varies by document complexity
- **Network**: Requires internet for WebDriver download only

---

## ✅ Quality Assurance

### Tested Scenarios
- ✅ **ARC document detection** and processing
- ✅ **Batch processing** with multiple document types
- ✅ **Attachment logic** for main opinions
- ✅ **Error handling** and recovery
- ✅ **Windows Defender** compatibility
- ✅ **Chrome WebDriver** auto-download

### Known Limitations
- **Windows only** (designed for Windows 10/11)
- **Chrome browser required** (WebDriver dependency)
- **Internet required** for initial WebDriver download
- **Administrator privileges** recommended for first run

---

*This executable is completely self-contained and ready for distribution to coworkers. No Python installation or additional dependencies required!*

