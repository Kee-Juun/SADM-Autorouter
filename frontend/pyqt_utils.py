"""
PyQt-specific utility functions for SADM Autorouter GUI.

This module contains utility functions specific to the PyQt GUI application,
including file matching, grouping, and DAR document processing logic.
"""

import re
import logging
from core.smducar_utils import extract_docket_number
from core.smducar import get_source_detail_mapping


def match_counsel_files(main_file, all_files, dar_mode=False):
    """
    Match counsel files to a main document based on docket number.
    
    Args:
        main_file (str): Main document filename
        all_files (list): List of all available files
        dar_mode (bool): Whether to use DAR mode for docket extraction
    
    Returns:
        list: List of counsel files that match the main document's docket number
    """
    base_docket = extract_docket_number(main_file, dar_mode)
    if not base_docket:
        return []
    
    counsel_files = []
    for file in all_files:
        # Check if file contains the base docket number and 'counsel'
        if base_docket in file and 'counsel' in file.lower():
            counsel_files.append(file)
    
    return counsel_files


def group_files_by_docket(files, dar_mode=False):
    """
    Group files by their docket number for processing.
    
    Args:
        files (list): List of filenames
        dar_mode (bool): Whether to use DAR mode for docket extraction
    
    Returns:
        dict: Dictionary with docket numbers as keys and lists of related files as values
    """
    docket_groups = {}
    
    for file in files:
        docket = extract_docket_number(file, dar_mode)
        if docket:
            if docket not in docket_groups:
                docket_groups[docket] = []
            docket_groups[docket].append(file)
    
    return docket_groups


def get_main_and_counsel_files(files, dar_mode=False):
    """
    Separate files into main documents and counsel files, grouped by docket.
    Enhanced with DAR mode logic for non-E2E document processing.
    
    Args:
        files (list): List of filenames
        dar_mode (bool): Whether to use DAR mode for docket extraction
    
    Returns:
        dict: Dictionary with docket numbers as keys and dicts containing 'main', 'counsel', 
              'auto_process', and 'manual_process' file lists
    """
    docket_groups = group_files_by_docket(files, dar_mode)
    organized_files = {}
    
    for docket, file_list in docket_groups.items():
        main_files = []
        counsel_files = []
        auto_process_files = []  # Files that can be processed automatically
        manual_process_files = []  # Files that require manual processing
        
        for file in file_list:
            if 'counsel' in file.lower() or 'arc' in file.lower():
                counsel_files.append(file)
            else:
                main_files.append(file)
                
                # Apply DAR mode logic for non-counsel files
                if dar_mode:
                    # Check if file should be auto-processed or require manual processing
                    processing_category = categorize_dar_document_for_processing(file)
                    if processing_category == 'auto':
                        auto_process_files.append(file)
                    elif processing_category == 'manual':
                        manual_process_files.append(file)
                    else:
                        # Default to auto-process for E2E files
                        auto_process_files.append(file)
                else:
                    # SMD mode: all main files go to auto-process
                    auto_process_files.append(file)
        
        # Counsel files (including ARC documents) are ALWAYS processed (go to auto_process for normal workflow)
        # The new DAR mode logic only affects non-counsel main documents
        for file in counsel_files:
            auto_process_files.append(file)
        
        organized_files[docket] = {
            'main': main_files,
            'counsel': counsel_files,
            'auto_process': auto_process_files,
            'manual_process': manual_process_files,
            'docket_number': docket  # Clean docket number for IRT form
        }
    
    return organized_files


def categorize_dar_document_for_processing(filename):
    """
    Categorize DAR documents for processing based on filename and IRT form field interactability.
    NOTE: This function only applies to NON-COUNSEL main documents in DAR mode.
    Counsel files are handled separately and always processed.
    
    Args:
        filename (str): Filename to categorize (should not be counsel files)
        
    Returns:
        str: 'auto' for automatic processing, 'manual' for manual processing, 'e2e' for E2E files
    """
    filename_lower = filename.lower()
    
    # E2E files are always processed automatically
    if 'e2e' in filename_lower:
        return 'e2e'
    
    # Non-E2E files need field interactability check during IRT form processing
    # For now, we categorize them as needing manual review until we check field interactability
    return 'manual'


def should_process_dar_document_automatically(filename, docket_field_interactable, decision_date_field_interactable):
    """
    Determine if a DAR document should be processed automatically based on field interactability.
    
    Args:
        filename (str): Filename to check
        docket_field_interactable (bool): Whether docket number field is interactable
        decision_date_field_interactable (bool): Whether decision date field is interactable
        
    Returns:
        dict: Processing decision with reason and status
    """
    filename_lower = filename.lower()
    
    # Counsel files are processed normally (not affected by this DAR mode logic)
    # This function is only called for main documents, not counsel files
    # Counsel files are handled separately and always go to auto_process
    if 'counsel' in filename_lower:
        return {
            'process': True,  # Counsel files are processed as usual
            'reason': 'Counsel file - processed normally (not affected by DAR mode logic)',
            'status': 'Ready for Processing',
            'category': 'counsel'
        }
    
    # E2E files are always processed automatically
    if 'e2e' in filename_lower:
        return {
            'process': True,
            'reason': 'E2E file - automatic processing enabled',
            'status': 'Ready for Processing',
            'category': 'e2e'
        }
    
    # Non-E2E files: check field interactability
    if not docket_field_interactable and not decision_date_field_interactable:
        # Both fields are pre-filled (not interactable) - safe to process
        return {
            'process': True,
            'reason': 'Non-E2E file with pre-filled data - safe for automation',
            'status': 'Ready for Processing',
            'category': 'non_e2e_auto'
        }
    else:
        # At least one field is interactable (empty/invalid) - requires manual review
        return {
            'process': False,
            'reason': 'Non-E2E file with empty/invalid fields - requires manual processing',
            'status': 'Requires Manual Processing',
            'category': 'non_e2e_manual'
        }


def extract_decision_date_from_filename(file_name):
    """
    Extract decision date from filename, supporting both MMDDYYYY and YYYYMMDD formats.
    Supports both SMD and DAR filename patterns.
    
    Args:
        file_name (str): Filename to extract date from
        
    Returns:
        str: Date in MM-DD-YYYY format if found, None otherwise
        
    Examples:
        - "LDC_SMD_24-7640a_E2E_PCQ_01012025.pdf" -> "01-01-2025" (MMDDYYYY)
        - "dar_2-23MD3081_01012025_AZD.pdf" -> "01-01-2025" (MMDDYYYY)
        - "DAR_9-24cv80713_01012025-56_E2E.pdf" -> "01-01-2025" (MMDDYYYY)
        - "smd_24-5838_CA6_25_20251112_142485669.pdf" -> "11-12-2025" (YYYYMMDD)
    """
    try:
        # Look for 8-digit date pattern in filename
        # Handle dates separated by underscores, hyphens, or other non-digit characters
        # Also handle dates at the beginning or end of filename
        date_match = re.search(r'[_-](\d{8})(?=[_-]|\.|$)|^(\d{8})[_-]|[_-](\d{8})$', str(file_name))
        if date_match:
            # Get the first non-None group (one of the three patterns matched)
            date_digits = None
            for i in range(1, 4):  # Check groups 1, 2, and 3
                if date_match.group(i):
                    date_digits = date_match.group(i)
                    break
            
            if date_digits and len(date_digits) == 8:
                # Try YYYYMMDD format first (year 1900-2099, month 01-12, day 01-31)
                year = int(date_digits[:4])
                month = int(date_digits[4:6])
                day = int(date_digits[6:8])
                
                if 1900 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
                    # Format as MM-DD-YYYY
                    return f"{month:02d}-{day:02d}-{year}"
                
                # Try MMDDYYYY format as fallback (month 01-12, day 01-31, year 1900-2099)
                month = int(date_digits[:2])
                day = int(date_digits[2:4])
                year = int(date_digits[4:])
                
                if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2099:
                    # Format as MM-DD-YYYY
                    return f"{month:02d}-{day:02d}-{year}"
        
        # If not found or invalid, return None to trigger fallback
        return None
        
    except Exception as e:
        logging.error(f"Error extracting decision date from filename '{file_name}': {e}")
        return None


def extract_source_detail_from_filename(file_name, dar_mode=False):
    """
    Extract source detail from filename, supporting multiple input formats.
    Works with both SMD and DAR filename patterns.
    
    Args:
        file_name (str): Filename to extract source detail from
        dar_mode (bool): Whether to use DAR mode for docket extraction
        
    Returns:
        str: Full source detail name if found, None otherwise
        
    Examples:
        # SMD Mode
        - "LDC_SMD_24-7640_OR_E2E_PCQ.pdf" -> "Order"
        - "LDC_SMD_24-7640_Order_E2E.pdf" -> "Order"
        - "LDC_SMD_24-7640_ao_E2E.pdf" -> "Adopting Order"
        
        # DAR Mode  
        - "dar_223md3081_OR_AZD_4684.pdf" -> "Order"
        - "dar_223md3081_AZD_Order_4684.pdf" -> "Order"
        - "dar_223md3081_AZD_4684_ao.pdf" -> "Adopting Order"
    """
    try:
        # Get the source detail mapping
        source_detail_mapping = get_source_detail_mapping()
        
        # Extract docket number to find where to start looking
        docket = extract_docket_number(file_name, dar_mode)
        if not docket:
            return None
            
        # Find the position after the docket number in the filename
        filename_lower = file_name.lower()
        docket_lower = docket.lower()
        
        # For SMD mode, look after "LDC_SMD_{docket}"
        if dar_mode:
            # DAR mode: look after the docket pattern
            # Find the end of the docket pattern (after the case number)
            docket_pattern = re.search(r'dar_[\w\-]*(\d{2})[-_]?(cv|md|cd|mc|cr|mj)(\d+)', file_name, re.IGNORECASE)
            if docket_pattern:
                # Get the position after the docket pattern
                docket_end_pos = docket_pattern.end()
                search_text = file_name[docket_end_pos:]
            else:
                # Also support LDC_PC / LDC_RR DAR-style patterns
                ldc_pattern = re.search(r'ldc_(pc|rr)_[\w\-]*(\d{2})[-_]?(cv|md|cd|mc|cr|mj)(\d+)', file_name, re.IGNORECASE)
                if ldc_pattern:
                    docket_end_pos = ldc_pattern.end()
                    search_text = file_name[docket_end_pos:]
                else:
                    # Fallback: look after the docket string
                    docket_pos = filename_lower.find(docket_lower)
                    if docket_pos == -1:
                        return None
                    search_text = file_name[docket_pos + len(docket):]
        else:
            # SMD mode: look after "LDC_SMD_{docket}"
            smd_pattern = f"LDC_SMD_{docket}"
            smd_pos = filename_lower.find(smd_pattern.lower())
            if smd_pos == -1:
                return None
            search_text = file_name[smd_pos + len(smd_pattern):]
        
        # Clean up the search text (remove file extension, etc.)
        search_text = re.sub(r'\.[a-zA-Z0-9]+$', '', search_text)  # Remove file extension
        search_text = search_text.strip('_-')  # Remove leading/trailing separators
        
        if not search_text:
            return None
            
        # Split by common separators and search for source detail matches
        parts = re.split(r'[_-]', search_text)
        
        # First, try exact matches (case-insensitive)
        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue
                
            # Check if it's an abbreviation
            if part_clean.lower() in source_detail_mapping:
                return source_detail_mapping[part_clean.lower()]
            
            # Check if it's a full name (case-insensitive)
            for full_name in source_detail_mapping.values():
                if part_clean.lower() == full_name.lower():
                    return full_name
        
        # If no exact matches, try partial matches (case-insensitive)
        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue
            
            # Check if part contains or is contained in any source detail
            for full_name in source_detail_mapping.values():
                full_name_lower = full_name.lower()
                part_lower = part_clean.lower()
                
                # Check if part is contained in full name or vice versa
                if (part_lower in full_name_lower or 
                    full_name_lower in part_lower or
                    part_lower == full_name_lower):
                    return full_name
        
        # If still no match, try fuzzy matching for common variations
        for part in parts:
            part_clean = part.strip()
            if not part_clean:
                continue
            
            # Handle common variations
            variations = {
                'order': 'Order',
                'opinion': 'Opinion', 
                'judgement': 'Judgement',
                'judgment': 'Judgement',  # Common misspelling
                'letter': 'Letter',
                'minutes': 'Minutes',
                'exhibit': 'Exhibits, Attachments, Appendix',
                'exhibits': 'Exhibits, Attachments, Appendix',
                'attachment': 'Exhibits, Attachments, Appendix',
                'appendix': 'Exhibits, Attachments, Appendix',
                'counsel': 'Counsel Information',
                'information': 'Counsel Information',
                'correction': 'Corrections',
                'corrections': 'Corrections',
                'release': 'Release',
                'withdraw': 'Withdraw',
                'writ': 'Writ',
                'vacate': 'Vacate/Quash',
                'quash': 'Vacate/Quash',
                'adopting': 'Adopting Order',
                'adopt': 'Adopting Order',
                'status': 'Change Status',
                'change': 'Change Status',
                'concur': 'Concurring Opinion, Concur in Part',
                'concurring': 'Concurring Opinion, Concur in Part',
                'dissent': 'Dissenting Opinion, Dissent in Part',
                'dissenting': 'Dissenting Opinion, Dissent in Part',
                'disposition': 'Disposition Only',
                'excluded': 'Excluded',
                'recommendation': 'Reports and Recommendations/Finding of Facts/Conclusion of Law',
                'recommendations': 'Reports and Recommendations/Finding of Facts/Conclusion of Law',
                'finding': 'Reports and Recommendations/Finding of Facts/Conclusion of Law',
                'conclusion': 'Reports and Recommendations/Finding of Facts/Conclusion of Law',
                'review': 'Review/Rehearing/Reconsideration',
                'rehearing': 'Review/Rehearing/Reconsideration',
                'reconsideration': 'Review/Rehearing/Reconsideration',
                'table': 'Table-(5-day spec source)',
                'published': 'Published Opinion (Online)',
                'unpublished': 'Unpublished Opinion (Online)',
                'online': 'Order (Online)',  # Default to online order
                'not_online': 'Order (Not Online)',
                'nol': 'Order (Not Online)',
                'ol': 'Order (Online)',
                'pool': 'Published Opinion (Online)',
                'uool': 'Unpublished Opinion (Online)',
                'uonol': 'Unpublished Opinion (Not Online)',
                'ornol': 'Order (Not Online)',
                'orol': 'Order (Online)'
            }
            
            if part_clean.lower() in variations:
                return variations[part_clean.lower()]
        
        # No match found
        return None
        
    except Exception as e:
        logging.error(f"Error extracting source detail from filename '{file_name}': {e}")
        return None

