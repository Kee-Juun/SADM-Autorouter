"""
Tester for `smducar.py` filename extraction and classification helpers.

Usage:
    - Demo run (built-in sample list):
        python tools/smducar_filename_tester.py --demo

    - Run against a directory of real files and write CSV results:
        python tools/smducar_filename_tester.py --dir "C:\\path\\to\\your\\files" --out report.csv

The script loads `core/smducar.py` from this project folder.
It reports columns: Filename, Mode, IsCounsel, ExtractedDocket, NormalizedDocket, Notes

"""
import argparse
import csv
import importlib.util
import os
import sys
from pathlib import Path

# Resolve smducar.py from this project so the copy stays self-contained
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMDUCAR_PATH = PROJECT_ROOT / "core" / "smducar.py"

# Load module by file path
try:
    spec = importlib.util.spec_from_file_location("smducar", SMDUCAR_PATH)
    smducar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smducar)

    # Functions we expect
    extract_docket_number = getattr(smducar, "extract_docket_number")
    is_counsel = getattr(smducar, "is_counsel")
    detect_mode = getattr(smducar, "detect_mode")
    normalize_docket_number = getattr(smducar, "normalize_docket_number")
    IMPORTED_FROM_SMDUCAR = True
except Exception as ex:
    # Fall back to simplified, local implementations of the filename helpers.
    IMPORTED_FROM_SMDUCAR = False
    import re

    def detect_mode(filename):
        s = str(filename).lower()
        if s.startswith('wc_cl_') or s.startswith('wc_'):
            return 'wc'
        if s.startswith('dar_') or s.startswith('ldc_pc_') or s.startswith('ldc_rr_'):
            return 'dar'
        if 'ldc_smd_' in s:
            return 'smd'
        return 'unknown'

    def is_counsel(filename, dar_mode=False, wc_mode=False):
        s = str(filename).lower()
        if 'counsel' in s or 'arc' in s:
            return True
        if wc_mode and re.search(r'wc_[a-z]{2}.*_counsel', s):
            return True
        if dar_mode and 'dar' in s and 'counsel' in s:
            return True
        return False

    def normalize_docket_number(docket):
        # Basic passthrough + attempt to remove leading zeroes in second part
        if not docket or not isinstance(docket, str):
            return docket
        if '-' in docket:
            parts = docket.split('-', 1)
            left = parts[0]
            right = parts[1].lstrip('0') or '0'
            return f"{left}-{right}"
        return docket

    def extract_docket_number(file_name, dar_mode=False, wc_mode=False):
        s = str(file_name)
        # WC pattern
        m = re.search(r'wc_[a-z]{2}_(\d{1})-(\d{2})(?:cv|cr|md)(\d+)', s, re.IGNORECASE)
        if m:
            yy = m.group(2)
            case = m.group(3)
            return f"{yy}-{case}"
        # DAR primary
        m = re.search(r'dar_[\w\-]*(\d{2})[-_]?(?:cv|md|cd|mc|cr|mj)(\d+)', s, re.IGNORECASE)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        # DAR simple fallback
        m = re.search(r'dar_(\d{2})-(\d+)', s, re.IGNORECASE)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        # SMD
        m = re.search(r'LDC_SMD_([\d\-]+)[a-z]?', s, re.IGNORECASE)
        if m:
            return m.group(1)
        # ldc_pc/rr fallback
        m = re.search(r'ldc_(?:pc|rr)_[\w\-]*(\d{2})[-_]?(?:cv|md|cd|mc|cr|mj)(\d+)', s, re.IGNORECASE)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        return None

SAMPLE_FILENAMES = [
    "LDC_SMD_24-7640a_E2E_PCQ.pdf",
    "LDC_SMD_24-7640counsel_E2E.htm",
    "DAR_924cv80713-56_E2E.pdf",
    "dar_2-23CV2039_PAWD_55_20250804_140135898.pdf",
    "wc_cl_9-23cv80992_FLSD_200_20250214_140074073.pdf",
    "wc_cl_8-24cv331_NED_Counsel.htm",
    "24-7640_Counsel.htm",
    "24-7640_arc.pdf",
    "randomfile_20250301.txt",
    "dar_24-30184_CA5_10092025.pdf",
    "ldc_pc_719cv02870-61_example.pdf",
    "wc_xy_123cv456_ABC_Counsel.htm",
    "counsel-1_24-1234.csv",
    "LDC_SMD_07-0123a_extra.PDF",
    "dar_99cv00001.pdf",
]


def classify_list(filenames, dar_mode=False, wc_mode=False):
    rows = []
    for fn in filenames:
        mode = detect_mode(fn)
        try:
            docket = extract_docket_number(fn, dar_mode=dar_mode, wc_mode=wc_mode)
        except Exception as e:
            docket = f"ERROR: {e}"
        try:
            norm = normalize_docket_number(docket) if docket else None
        except Exception:
            norm = None
        try:
            counsel = is_counsel(fn, dar_mode=dar_mode, wc_mode=wc_mode)
        except Exception:
            counsel = False
        notes = []
        if docket is None:
            notes.append("no-docket")
        if counsel:
            notes.append("counsel-flagged")
        rows.append({
            "Filename": fn,
            "Mode": mode,
            "IsCounsel": counsel,
            "ExtractedDocket": docket,
            "NormalizedDocket": norm,
            "Notes": ";".join(notes) if notes else ""
        })
    return rows


def run_demo(out=None):
    print("Running demo classification on built-in sample filenames:\n")
    rows = classify_list(SAMPLE_FILENAMES)
    for r in rows:
        print(f"{r['Filename']}: mode={r['Mode']}, counsel={r['IsCounsel']}, docket={r['ExtractedDocket']}, normalized={r['NormalizedDocket']}, notes={r['Notes']}")
    if out:
        with open(out, "w", newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV written to: {out}")


def run_directory_scan(dirpath, out):
    p = Path(dirpath)
    files = [str(x.name) for x in p.iterdir() if x.is_file()]
    print(f"Found {len(files)} files in {dirpath} — classifying...")
    rows = classify_list(files)
    if out:
        with open(out, "w", newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV written to: {out}")
    else:
        for r in rows:
            print(f"{r['Filename']}: mode={r['Mode']}, counsel={r['IsCounsel']}, docket={r['ExtractedDocket']}, normalized={r['NormalizedDocket']}, notes={r['Notes']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Run demo sample list')
    parser.add_argument('--dir', help='Directory to scan for filenames')
    parser.add_argument('--out', help='CSV output path')
    args = parser.parse_args()

    if args.demo:
        run_demo(out=args.out)
    elif args.dir:
        run_directory_scan(args.dir, args.out)
    else:
        parser.print_help()
