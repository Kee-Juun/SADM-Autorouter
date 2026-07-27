# Filename Patterns Configuration System - Migration Guide

## ✅ What's Been Created

1. **`config/filename_patterns.json`** - Centralized configuration file for all filename patterns
2. **`utils/filename_patterns.py`** - Utility module that reads and uses the patterns
3. **`config/FILENAME_PATTERNS_README.md`** - Complete documentation

## 🎯 Benefits

- ✅ **No code changes needed** - Just update the JSON config file
- ✅ **Centralized** - All patterns in one place
- ✅ **Easy to maintain** - Clear structure and documentation
- ✅ **Backward compatible** - Existing code can be gradually migrated

## 📝 How to Use

### For Adding New Patterns (No Code Changes!)

1. Open `config/filename_patterns.json`
2. Find the appropriate section (smd/dar/wc)
3. Add your new pattern following the existing format
4. Save - that's it! The system will automatically use it

### Example: Adding a New Pattern

**Client Request**: "We need to support `NEW_FORMAT_24-1234.pdf` files"

**Solution**: Just add to `config/filename_patterns.json`:

```json
{
  "pattern": "NEW_FORMAT_(\\d+-\\d+)",
  "description": "New format pattern",
  "example": "NEW_FORMAT_24-1234.pdf",
  "extraction_group": 1,
  "priority": 5
}
```

No Python code changes needed!

## 🔄 Migration Path (Optional)

The new system is ready to use, but existing code still uses the old hardcoded patterns. To fully migrate:

1. **Phase 1** (Current): Config system created, ready for new patterns
2. **Phase 2** (Future): Update existing code to use `utils/filename_patterns.py`
3. **Phase 3** (Future): Remove old hardcoded pattern functions

### Current Status

- ✅ Config system created and tested
- ✅ All existing patterns documented in config
- ⏳ Existing code still uses old functions (backward compatible)
- ✅ New patterns can be added via config immediately

## 📚 Files Reference

| File | Purpose |
|------|---------|
| `config/filename_patterns.json` | **Main config file** - Edit this to add patterns |
| `utils/filename_patterns.py` | Utility module - reads config and provides functions |
| `config/FILENAME_PATTERNS_README.md` | Complete documentation |
| `FILENAME_PATTERNS_MIGRATION.md` | This file - migration guide |

## 🧪 Testing

Test your patterns:

```python
from utils.filename_patterns import is_counsel, extract_docket_number

# Test docket extraction
docket = extract_docket_number("your_filename.pdf", dar_mode=False, wc_mode=False)
print(f"Extracted: {docket}")

# Test counsel detection
is_counsel_file = is_counsel("your_filename.pdf", dar_mode=False, wc_mode=False)
print(f"Is counsel: {is_counsel_file}")
```

## 🎓 Quick Reference

### Adding a Docket Pattern

```json
{
  "pattern": "your_regex",
  "description": "What it matches",
  "example": "example.pdf",
  "extraction_groups": [1, 2],
  "format": "{group1}-{group2}",
  "priority": 10
}
```

### Adding a Counsel Pattern

```json
{
  "pattern": "counsel_indicator",
  "type": "substring",
  "case_sensitive": false,
  "description": "What it matches"
}
```

## 📞 Support

- See `config/FILENAME_PATTERNS_README.md` for detailed documentation
- Check `config/filename_patterns.json` for pattern examples
- Review test output for pattern matching details

---

**Created**: 2025-01-15  
**Status**: ✅ Ready for use - Add new patterns via config file!
