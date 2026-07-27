import os
import datetime
import logging
import platform
import subprocess
from pathlib import Path

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter


def get_source_detail_mapping():
    """Return mapping of abbreviations to full source detail names."""
    return {
        'ao': 'Adopting Order',
        'cs': 'Change Status',
        'cd': 'Concur in Part / Dissent in Part',
        'cop': 'Concurring Opinion, Concur in Part',
        'cc': 'Corrections',
        'ci': 'Counsel Information',
        'dd': 'Disposition Only',
        'dop': 'Dissenting Opinion, Dissent in Part',
        'e': 'Excluded',
        'ex': 'Exhibits, Attachments, Appendix',
        'j': 'Judgement',
        'le': 'Letter',
        'lod': 'List of Documents',
        'm': 'Minutes',
        'op': 'Opinion',
        'or': 'Order',
        'ornol': 'Order (Not Online)',
        'orol': 'Order (Online)',
        'pool': 'Published Opinion (Online)',
        'rl': 'Release',
        'rr': 'Reports and Recommendations/Finding of Facts/Conclusion of Law',
        'r': 'Review/Rehearing/Reconsideration',
        't': 'Table-(5-day spec source)',
        'uonol': 'Unpublished Opinion (Not Online)',
        'uool': 'Unpublished Opinion (Online)',
        'vq': 'Vacate/Quash',
        'wd': 'Withdraw',
        'wr': 'Writ',
    }


def add_source_detail_dropdown_to_excel(file_path: str) -> None:
    """Add data validation dropdown for Source Detail column using a hidden options sheet."""
    try:
        from openpyxl.worksheet.datavalidation import DataValidation

        wb = load_workbook(file_path)
        ws = wb["Mapping Data"]

        source_detail_mapping = get_source_detail_mapping()
        dropdown_options = sorted(set(source_detail_mapping.values()))

        options_sheet_name = "DropdownOptions"
        if options_sheet_name in wb.sheetnames:
            options_ws = wb[options_sheet_name]
        else:
            options_ws = wb.create_sheet(options_sheet_name)

        # Clear existing data in the options sheet
        for row in range(1, 100):
            options_ws[f"A{row}"] = None

        # Write options to column A
        for i, option in enumerate(dropdown_options, start=1):
            options_ws[f"A{i}"] = option

        # Hide the sheet
        options_ws.sheet_state = 'hidden'

        # Find the Source Detail column by looking at the header row
        source_detail_col = None
        for col in range(1, 20):  # Check first 20 columns
            cell_value = ws.cell(row=1, column=col).value
            if cell_value and "Source Detail" in str(cell_value):
                source_detail_col = get_column_letter(col)
                break

        if not source_detail_col:
            source_detail_col = 'G'

        options_range = f"'{options_sheet_name}'!$A$1:$A${len(dropdown_options)}"

        dv = DataValidation(
            type="list",
            formula1=f"={options_range}",
            allow_blank=True,
            showErrorMessage=True,
            errorTitle="Invalid Source Detail",
            error="Please select a valid Source Detail from the dropdown or type a valid abbreviation/full name.",
            showInputMessage=True,
            promptTitle="Source Detail",
            prompt="Select from dropdown or type abbreviation (e.g., AO, OP, RR) or full name.",
        )

        # Apply to the entire Source Detail column (excluding header)
        dv.add(f'{source_detail_col}2:{source_detail_col}1000')
        ws.add_data_validation(dv)

        wb.save(file_path)
    except Exception:
        logging.error("Failed to add Source Detail dropdown to Excel")


def generate_excel(folder_path: str) -> str:
    """Create a new Mapping Data workbook in the given folder."""
    now = datetime.datetime.now()
    time_str = now.strftime("%I%M%S_%p").lstrip("0")
    date_str = now.strftime("%d%m%Y")
    filename = f"Case Law Auto-Routing Data Mapping Sheet - {time_str} - {date_str}.xlsx"
    file_path = os.path.join(folder_path, filename)

    wb = Workbook()
    ws = wb.active
    ws.title = "Mapping Data"

    headers = [
        "Require Cardinal Process", "Court Code", "File Name", "LNI",
        "Tier", "Received Date", "Time Left",
        "Recycled Counsel LNI", "Source Detail", "Comments",
        "Decision Date",  # Optional manual decision date for this row
        "Status"
    ]

    header_font = Font(name="Aptos Display", size=12, bold=True)
    alignment = Alignment(horizontal="center", vertical="center")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    fill = PatternFill(start_color="E7CCFC", end_color="E7CCFC", fill_type="solid")

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.alignment = alignment
        cell.border = border
        cell.fill = fill

    # Format date columns (Received Date and Decision Date) for readability
    for col_letter in ['F', 'K']:
        try:
            ws.column_dimensions[col_letter].number_format = 'MM/DD/YYYY'
        except Exception:
            pass

    # Autofit columns
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    wb.save(file_path)
    logging.info(f"Excel file created: {file_path}")

    # Preserve existing behavior: add Source Detail dropdown
    add_source_detail_dropdown_to_excel(file_path)

    return file_path


def open_excel_file(path: str) -> None:
    """Open an Excel file using the platform default handler."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
        logging.info("Excel file opened for user input.")
    except Exception:
        logging.error("Error opening file")


def get_latest_excel_file(folder_path: str) -> str | None:
    """Return the most recent .xlsx file in the given folder, or None if none exist."""
    files = [f for f in os.listdir(folder_path) if f.endswith(".xlsx")]
    if not files:
        logging.error("No Excel files found in the folder.")
        return None
    files.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)), reverse=True)
    latest_file = os.path.join(folder_path, files[0])
    logging.info(f"Latest Excel file detected: {latest_file}")
    return latest_file


def read_mapping_data(file_path: str) -> pd.DataFrame:
    """Read mapping data from the Mapping Data sheet."""
    try:
        df = pd.read_excel(file_path, sheet_name="Mapping Data", engine="openpyxl")
        selected_columns = df.iloc[:, [0, 1, 2, 3, 5, 7, 8, 9, 10, 11]].copy()
        selected_columns.columns = [
            "RequireCardinal",
            "CourtCode",
            "FileName",
            "LNI",
            "ReceivedDate",
            "RecycledCounselLNI",
            "SourceDetail",
            "Comments",
            "Decision Date",
            "Status",
        ]
        logging.info("Excel data extracted successfully.")
        return selected_columns
    except Exception:
        logging.error("Failed to read Excel")
        return pd.DataFrame()


def _autofit_columns(ws) -> None:
    for col in ws.columns:
        max_length = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass
        adjusted_width = max_length + 2
        ws.column_dimensions[col_letter].width = adjusted_width


def _write_mspb_metadata_sheet(wb, metadata_map: dict[int, dict], status_map: dict[int, str], status_styles: dict) -> None:
    has_non_mspb = any(record.get("Metadata Type") and record.get("Metadata Type") != "MSPB" for record in metadata_map.values())
    sheet_name = "PDF Metadata" if has_non_mspb else "MSPB Metadata"
    for stale_sheet in ("MSPB Metadata", "PDF Metadata"):
        if stale_sheet in wb.sheetnames:
            del wb[stale_sheet]

    ws = wb.create_sheet(sheet_name)
    headers = [
        "Metadata Type",
        "LNI",
        "File Name",
        "Extracted Court Code",
        "Extracted Docket Number",
        "Extracted Decision Date",
        "Extracted Source Detail",
        "Extracted Other Numbers",
        "Prepared Comments",
        "Title Hint",
        "Route",
        "Metadata Status",
        "Final Status",
    ]

    header_font = Font(name="Aptos Display", size=12, bold=True)
    alignment = Alignment(horizontal="center", vertical="center")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    fill = PatternFill(start_color="E7CCFC", end_color="E7CCFC", fill_type="solid")

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = header_font
        cell.alignment = alignment
        cell.border = border
        cell.fill = fill

    for output_row, row_index in enumerate(sorted(metadata_map), 2):
        record = metadata_map.get(row_index, {})
        final_status = status_map.get(row_index, record.get("Final Status", ""))
        values = [
            record.get("Metadata Type", "MSPB"),
            record.get("LNI", ""),
            record.get("File Name", ""),
            record.get("Extracted Court Code", ""),
            record.get("Extracted Docket Number", ""),
            record.get("Extracted Decision Date", ""),
            record.get("Extracted Source Detail", ""),
            record.get("Extracted Other Numbers", ""),
            record.get("Prepared Comments", ""),
            record.get("Title Hint", ""),
            record.get("Route", "Outside Conversion"),
            record.get("Metadata Status", ""),
            final_status,
        ]

        for col_num, value in enumerate(values, 1):
            cell = ws.cell(row=output_row, column=col_num, value=value)
            cell.border = border
            cell.alignment = Alignment(vertical="center")

        status_style = status_styles.get(final_status, {"bold": False, "color": "000000"})
        status_cell = ws.cell(row=output_row, column=len(headers))
        status_cell.font = Font(bold=status_style["bold"], color=status_style["color"])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    _autofit_columns(ws)


def flush_status_updates(file_path: str, status_map: dict[int, str], mspb_metadata_map: dict[int, dict] | None = None) -> None:
    """Write status values back into the Mapping Data sheet (status column)."""
    try:
        wb = load_workbook(file_path)
        ws = wb["Mapping Data"]

        status_styles = {
            "DONE": {"bold": True, "color": "00A86B"},
            "ALREADY PROCESSED": {"bold": True, "color": "4F39BC"},
            "PROCESSING": {"bold": True, "color": "1F4E79"},
            "NEEDS RERUN - SEARCH FAILED": {"bold": True, "color": "C00000"},
            "NEEDS RERUN - INTERRUPTED": {"bold": True, "color": "C65911"},
            "NEEDS RERUN - NOT ATTEMPTED": {"bold": True, "color": "7F6000"},
            "NEEDS RERUN - FAILED": {"bold": True, "color": "C00000"},
            "NEEDS RERUN - COUNSEL FAILED": {"bold": True, "color": "C00000"},
            "ERROR: LNI NOT FOUND": {"bold": True, "color": "E3242B"},
            "ERROR: INVALID LNI FORMAT": {"bold": True, "color": "E3242B"},
            "ERROR: UNABLE TO LOAD IRT FORM WINDOW": {"bold": True, "color": "E3242B"},
            "ERROR": {"bold": True, "color": "E3242B"},
            "RELATED LNI ERROR": {"bold": True, "color": "E3242B"},
            "NO COUNSEL ATTACHED": {"bold": True, "color": "E3242B"},
        }

        for row_index, status in status_map.items():
            cell = ws.cell(row=row_index + 2, column=12)  # Column L = Status
            cell.value = status

            style = status_styles.get(status, {"bold": False, "color": "000000"})
            cell.font = Font(bold=style["bold"], color=style["color"])

        # Autofit all columns
        _autofit_columns(ws)

        if mspb_metadata_map is not None:
            _write_mspb_metadata_sheet(wb, mspb_metadata_map, status_map, status_styles)

        wb.save(file_path)
        logging.info("Buffered status updates written to Excel with formatting and column autofitting.")
    except Exception:
        logging.error("Failed to flush status updates")


