# Core Automation Workflow

This folder contains the essential automation workflow extracted from the main application. It focuses solely on the core automation functionality without the GUI and other non-essential features.

## Overview

The core automation workflow automates the process of routing case law documents through the LexisNexis IRT system. It handles:

1. **Excel File Management**: Creates and manages Excel files for data input
2. **Web Automation**: Automates browser interactions with the LexisNexis system
3. **Document Processing**: Processes both counsel and main opinion documents
4. **Error Handling**: Robust error handling and retry mechanisms
5. **Logging**: Comprehensive logging for debugging and monitoring

## Files Structure

- `core_automation.py` - Core utility functions and automation logic
- `case_law_router.py` - Main CaseLawRouter class with browser automation methods
- `form_filling.py` - Form filling methods for IRT forms
- `main_workflow.py` - Main orchestration functions
- `requirements.txt` - Python dependencies
- `README.md` - This documentation file

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have Chrome browser installed (the automation uses Chrome WebDriver)

## Usage

### Method 1: Create New Excel File and Run Automation

```python
from main_workflow import run_automation_with_excel

# Run in normal mode
success = run_automation_with_excel(dar_mode=False)

# Run in DAR mode
success = run_automation_with_excel(dar_mode=True)
```

### Method 2: Use Existing Excel File

```python
from main_workflow import run_automation_with_existing_excel

excel_path = "path/to/your/excel/file.xlsx"
success = run_automation_with_existing_excel(excel_path, dar_mode=False)
```

### Method 3: Direct Workflow Execution

```python
from main_workflow import run_automation_workflow
import pandas as pd

# Load your data
df = pd.read_excel("your_file.xlsx")

# Run automation
counsel_df, main_df = run_automation_workflow(
    latest_excel="path/to/excel/file.xlsx",
    df=df,
    dar_mode=False
)
```

## Excel File Format

The automation expects an Excel file with the following columns:

| Column | Description | Required |
|--------|-------------|----------|
| Require Cardinal Process | Whether cardinal process is required | Yes |
| File Name | Name of the file to process | Yes |
| LNI | Legal Notice Identifier | Yes |
| Received Date | Date the document was received | Yes |
| Recycled Counsel LNI | Previously used counsel LNI | No |
| Source Detail | Source detail abbreviation | No |
| Comments | Additional comments | No |
| Status | Processing status | Auto-filled |

## Configuration

Create a `config/config.json` file in the same directory:

```json
{
    "headless": false,
    "environment": "prod"
}
```

- `headless`: Run browser in headless mode (true/false)
- `environment`: Target environment ("prod" or "staging")

## Key Features

### 1. Robust Error Handling
- Automatic retry mechanisms for failed operations
- Comprehensive error logging
- Graceful handling of network issues

### 2. Session Management
- Automatic browser session validation
- Tab management for multiple windows
- Cleanup of orphaned browser windows

### 3. Progress Tracking
- Real-time progress updates
- Batch processing statistics
- Performance metrics (LNIs per hour)

### 4. Document Type Detection
- Automatic detection of counsel vs main opinion documents
- Support for both SMD and DAR file naming patterns
- Intelligent docket number extraction

### 5. Form Automation
- Automatic form field population
- Dropdown selection handling
- Alert and popup management
- Duplicate document handling

## Logging

The automation creates detailed logs in:
```
~/Downloads/Case Law Auto-Routing Resources/Logs/
```

Logs include:
- Processing timestamps
- Success/failure status
- Error details
- Performance metrics

## Error Reports

Failed operations are logged to error reports in:
```
~/Downloads/Case Law Auto-Routing Resources/Error Reports/
```

## Dependencies

- **selenium**: Web automation
- **webdriver-manager**: Chrome driver management
- **pandas**: Data manipulation
- **openpyxl**: Excel file handling
- **colorama**: Colored console output
- **pathlib2**: Path manipulation

## Troubleshooting

### Common Issues

1. **Chrome Driver Issues**
   - Ensure Chrome browser is installed
   - The automation will automatically download the correct driver version

2. **Excel File Issues**
   - Ensure the Excel file has the correct column structure
   - Check that the file is not open in another application

3. **Network Issues**
   - Check internet connection
   - Verify access to the LexisNexis system

4. **Session Issues**
   - The automation will automatically handle session timeouts
   - Check logs for specific error messages

### Debug Mode

Enable detailed logging by modifying the logging level in `core_automation.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Performance

Typical performance metrics:
- **Processing Speed**: 50-100 LNIs per hour (depending on network and system performance)
- **Success Rate**: 95%+ for properly formatted data
- **Error Recovery**: Automatic retry for most common issues

## Security Notes

- The automation does not store credentials
- All sensitive data is handled in memory only
- Logs do not contain sensitive information
- Browser sessions are cleaned up after completion

## Support

For issues or questions:
1. Check the logs for detailed error information
2. Verify Excel file format and data quality
3. Ensure all dependencies are properly installed
4. Check network connectivity to the target system
