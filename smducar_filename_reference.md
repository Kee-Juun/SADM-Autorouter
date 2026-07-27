SMDUCAR Filename Extraction Reference

This file documents the filename patterns and extraction logic used by `smducar.py` (and its helper `smducar_pyqt`). It maps the major regexes/heuristics to example filenames and notes.

Modes
- SMD (LDC_SMD_): primary SMD pattern
  - Regex snippet: `LDC_SMD_([\d\-]+)[a-z]?`
  - Behavior: captures `24-7640` from `LDC_SMD_24-7640a_E2E_PCQ.pdf` and removes trailing letter.
  - Examples:
    - `LDC_SMD_24-7640a_E2E_PCQ.pdf` -> `24-7640`
    - `LDC_SMD_24-7640counsel_E2E.htm` -> `24-7640`

- DAR (dar_ / LDC_PC / LDC_RR treated as DAR): multiple fallback regexes
  - Primary DAR snippet (captures 2-digit year + case token + case number):
    - `dar_[\w\-]*(\d{2})[-_]?(cv|md|cd|mc|cr|mj)(\d+)`
    - Example: `DAR_924cv80713-56_E2E.pdf` -> `24-80713`
  - Simple DAR fallback: `dar_(\d{2})-(\d+)`
    - Example: `dar_24-30184_CA5_10092025.pdf` -> `24-30184`
  - `ldc_pc_` / `ldc_rr_` are handled with similar DAR-style regexes.

- WC (work-comp, `wc_` prefix): many variants handled
  - Regex snippet used in code (simplified): `wc_[a-z]{2}_(\d{1})(\d{2})(cv|cr|md)(\d+)(?:-\d+)?_`
  - Behavior: recomposes pieces into `YY-CASE` (e.g., `23-80992`).
  - Examples:
    - `wc_cl_9-23cv80992_FLSD_200_20250214_140074073.pdf` -> `23-80992`
    - `wc_cl_8-24cv331_NED_Counsel.htm` -> `24-331`

Counsel / ARC detection
- `is_counsel()` returns True if any of these are true:
  - filename contains substring `counsel` (case-insensitive)
  - filename contains substring `arc` (case-insensitive)
  - `wc_mode` and a `wc_..._..._counsel` pattern matches
  - `dar_mode` and `dar...counsel` pattern matches
- Examples:
  - `24-7640_Counsel.htm` -> counsel
  - `24-7640_arc.pdf` -> counsel (ARC treated as counsel)

Preprocessing & normalization steps (applied in places)
- `counsel-\d+` is normalized to `counsel` (e.g., `counsel-1` -> `counsel`).
- Date segments like `_MMDDYYYY` (`_\d{8}`) removed in some cleanups.
- Removes file extensions and known tokens like `_E2E`, `_PCQ`, `.pdf`, `.htm` when cleaning.
- Trailing letters on docket numbers removed (`24-7640a` -> `24-7640`).
- `normalize_docket_number()` removes leading zeroes from the case portion when applicable.

Limitations & edge-cases
- WC regex is somewhat fragile for unusual digit groupings; test with real filenames.
- Files that are counsel but do not contain `counsel` or `arc` in the name may be missed.
- Trailing letter distinction (e.g., `a` vs `b`) is lost by design.
- The code expects 2-digit year formats for many DAR/WC patterns; unusual year encodings can fail.

Usage
- `extract_docket_number(filename, dar_mode=False, wc_mode=False)` returns a normalized docket string or `None`.
- `is_counsel(filename, dar_mode=False, wc_mode=False)` returns boolean.
- `detect_mode(filename)` returns `'smd'`, `'dar'`, `'wc'`, or `'unknown'` (simple heuristic).

If you want, run the tester script `tools/smducar_filename_tester.py` (created next) against a folder of your real filenames to get a CSV report. See the instructions in that script.
