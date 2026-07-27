# Filename Patterns Configuration Guide

## Overview

The `filename_patterns.json` file centralizes all filename pattern matching logic for:
- **SMD USAP Courts Autorouter**
- **DARA Autorouter** (DAR mode)
- **WC Autorouter** (Westclip mode)

This allows you to add new filename patterns without modifying code - just update the config file!

## Quick Start

### Adding a New Filename Pattern

1. **Open** `config/filename_patterns.json`

2. **Find the appropriate section**:
   - `docket_extraction.patterns.smd` - for SMD patterns
   - `docket_extraction.patterns.dar` - for DAR patterns
   - `docket_extraction.patterns.wc` - for WC patterns

3. **Add your pattern**:
```json
{
  "pattern": "your_regex_pattern_here",
  "description": "What this pattern matches",
  "example": "example_filename.pdf",
  "extraction_groups": [1, 2],
  "format": "{group1}-{group2}",
  "priority": 4,
  "court_types": ["cv", "md"]
}
```

4. **Save the file** - changes take effect immediately (no code changes needed!)

### Adding a New Counsel Detection Pattern

1. **Open** `config/filename_patterns.json`

2. **Find** `counsel_detection.mode_specific_patterns.[mode]`

3. **Add your pattern**:
```json
{
  "pattern": "counsel_pattern",
  "type": "substring",
  "case_sensitive": false,
  "description": "What this matches"
}
```

## Pattern Structure

### Docket Extraction Patterns

Each pattern needs:
- **`pattern`**: Regex pattern (use `\\` for backslashes in JSON)
- **`description`**: Human-readable description
- **`example`**: Example filename that matches
- **`extraction_groups`**: Which regex groups to extract (e.g., `[1, 3]`)
- **`format`**: How to format the result (e.g., `"{group1}-{group3}"`)
- **`priority`**: Lower number = higher priority (tried first)
- **`court_types`**: (Optional) List of court type abbreviations

### Format String Options

- `{group1}`, `{group2}`, etc. - Use the value from that regex group
- `{last2ofgroup1}` - Use last 2 characters of group 1 (for year extraction)

### Counsel Detection Patterns

- **`type`**: `"substring"` or `"regex"`
- **`pattern`**: The pattern to match
- **`case_sensitive`**: `true` or `false`

## Examples

### Example 1: Add New SMD Pattern

**Scenario**: Client wants to support `SMD_24-1234.pdf` format (without `LDC_` prefix)

```json
{
  "pattern": "SMD_(\\d+-\\d+)",
  "description": "SMD pattern without LDC_ prefix",
  "example": "SMD_24-1234.pdf",
  "extraction_group": 1,
  "priority": 4
}
```

### Example 2: Add New DAR Court Type

**Scenario**: Client wants to support `tx` court type in DAR mode

Update existing pattern or add new one:
```json
{
  "pattern": "dar_[\\w\\-]*(\\d{2})[-_]?(cv|md|cd|mc|cr|mj|tx)(\\d+)(?:[-_]|(?=[a-zA-Z]))",
  "court_types": ["cv", "md", "cd", "mc", "cr", "mj", "tx"],
  ...
}
```

### Example 3: Add New Counsel Indicator

**Scenario**: Files with `_ATTY_` in name should be treated as counsel

```json
{
  "pattern": "_ATTY_",
  "type": "substring",
  "case_sensitive": false,
  "description": "Attorney indicator in filename"
}
```

## Testing Your Changes

Use the test script:
```python
from utils.filename_patterns import is_counsel, extract_docket_number

# Test docket extraction
filename = "your_test_filename.pdf"
docket = extract_docket_number(filename, dar_mode=False, wc_mode=False)
print(f"Extracted docket: {docket}")

# Test counsel detection
is_counsel_file = is_counsel(filename, dar_mode=False, wc_mode=False)
print(f"Is counsel: {is_counsel_file}")
```

## Priority System

Patterns are tried in **priority order** (lower number = tried first):
- Priority 1 = Highest priority (tried first)
- Priority 2 = Second priority
- etc.

If multiple patterns could match, the first one (lowest priority number) wins.

## Mode Detection

The system automatically detects which mode to use:
- **SMD mode**: Default (when `dar_mode=False` and `wc_mode=False`)
- **DAR mode**: When `dar_mode=True`
- **WC mode**: When `wc_mode=True`

## Reloading Config

If you update the config file while the app is running, you can reload it:

```python
from utils.filename_patterns import get_pattern_config

config = get_pattern_config()
config.reload_config()
```

## Troubleshooting

### Pattern Not Matching

1. Check regex syntax (use `\\` for backslashes in JSON)
2. Verify `extraction_groups` match your regex groups
3. Check `priority` - lower priority patterns are tried first
4. Test with regex tester: https://regex101.com/

### Wrong Docket Extracted

1. Check `extraction_groups` - are you extracting the right groups?
2. Check `format` string - is the format correct?
3. Verify `priority` - a higher priority pattern might be matching first

### Counsel Not Detected

1. Check pattern is in correct mode section
2. Verify `case_sensitive` setting
3. Check pattern type (`substring` vs `regex`)

## File Locations

- **Config file**: `config/filename_patterns.json`
- **Utility module**: `utils/filename_patterns.py`
- **This guide**: `config/FILENAME_PATTERNS_README.md`

## Support

For questions or issues:
1. Check the pattern examples in the config file
2. Review the test cases in `tools/smducar_filename_tester.py`
3. Check logs for pattern matching details
