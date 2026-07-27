"""
Centralized filename pattern utilities for all autorouter modes.
Reads patterns from config/filename_patterns.json for easy maintenance.
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any


class FilenamePatternConfig:
    """Manages filename pattern configuration for all autorouter modes."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the pattern config.
        
        Args:
            config_path: Path to filename_patterns.json. If None, uses default location.
        """
        if config_path is None:
            # Try to find config relative to this file
            base_path = Path(__file__).parent.parent
            config_path = base_path / "config" / "filename_patterns.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._compile_patterns()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load the JSON configuration file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logging.info(f"Loaded filename patterns config from {self.config_path}")
            return config
        except FileNotFoundError:
            logging.error(f"Config file not found: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing config file: {e}")
            return {}
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for better performance."""
        self._compiled_patterns = {}
        
        # Compile docket extraction patterns
        for mode in ['smd', 'dar', 'wc']:
            if mode in self.config.get('docket_extraction', {}).get('patterns', {}):
                patterns = self.config['docket_extraction']['patterns'][mode]
                self._compiled_patterns[mode] = []
                for pattern_def in patterns:
                    try:
                        compiled = re.compile(pattern_def['pattern'], re.IGNORECASE)
                        self._compiled_patterns[mode].append({
                            'compiled': compiled,
                            'definition': pattern_def
                        })
                    except re.error as e:
                        logging.warning(f"Invalid regex pattern for {mode}: {pattern_def.get('pattern')} - {e}")
    
    def is_counsel(self, filename: str, dar_mode: bool = False, wc_mode: bool = False) -> bool:
        """
        Check if a filename indicates a counsel/ARC file.
        
        Args:
            filename: The filename to check
            dar_mode: Whether DAR mode is active
            wc_mode: Whether WC mode is active
            
        Returns:
            True if the file is identified as counsel/ARC
        """
        filename_lower = str(filename).lower()
        config = self.config.get('counsel_detection', {})
        
        # Check global patterns first
        for pattern_def in config.get('global_patterns', []):
            if self._match_pattern(filename_lower, pattern_def):
                return True
        
        # Check mode-specific patterns
        mode_patterns = []
        if dar_mode:
            mode_patterns.extend(config.get('mode_specific_patterns', {}).get('dar', []))
        else:  # SMD mode (WC mode removed)
            mode_patterns.extend(config.get('mode_specific_patterns', {}).get('smd', []))
        
        for pattern_def in mode_patterns:
            if self._match_pattern(filename_lower, pattern_def):
                return True
        
        return False
    
    def _match_pattern(self, text: str, pattern_def: Dict[str, Any]) -> bool:
        """Match a pattern definition against text."""
        pattern = pattern_def.get('pattern', '')
        pattern_type = pattern_def.get('type', 'substring')
        case_sensitive = pattern_def.get('case_sensitive', False)
        
        if pattern_type == 'regex':
            flags = 0 if case_sensitive else re.IGNORECASE
            return bool(re.search(pattern, text, flags))
        elif pattern_type == 'substring':
            if case_sensitive:
                return pattern in text
            else:
                return pattern.lower() in text.lower()
        return False
    
    def extract_docket_number(self, filename: str, dar_mode: bool = False, wc_mode: bool = False) -> Optional[str]:
        """
        Extract docket number from filename based on mode.
        
        Args:
            filename: The filename to extract from
            dar_mode: Whether DAR mode is active
            wc_mode: Whether WC mode is active
            
        Returns:
            Extracted docket number (e.g., "24-7640") or None if not found
        """
        # Normalize filename first
        normalized = self._normalize_filename(filename)
        
        # Determine which mode patterns to use
        mode = 'dar' if dar_mode else 'smd'
        
        # Get patterns for this mode
        patterns = self._compiled_patterns.get(mode, [])
        
        # Try patterns in priority order
        for pattern_item in sorted(patterns, key=lambda x: x['definition'].get('priority', 999)):
            pattern_def = pattern_item['definition']
            compiled = pattern_item['compiled']
            
            match = compiled.search(normalized)
            if match:
                docket = self._extract_from_match(match, pattern_def)
                if docket:
                    logging.info(f"Extracted docket '{docket}' from '{filename}' using {mode} pattern: {pattern_def.get('pattern')}")
                    return docket
        
        logging.warning(f"Could not extract docket from '{filename}' in {mode} mode")
        return None
    
    def _normalize_filename(self, filename: str) -> str:
        """Apply normalization rules to filename before pattern matching."""
        normalized = str(filename)
        rules = self.config.get('normalization_rules', {}).get('preprocessing', [])
        
        for rule in rules:
            pattern = rule.get('pattern', '')
            replacement = rule.get('replacement', '')
            try:
                normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
            except re.error as e:
                logging.warning(f"Invalid normalization pattern: {pattern} - {e}")
        
        return normalized
    
    def _extract_from_match(self, match: re.Match, pattern_def: Dict[str, Any]) -> Optional[str]:
        """Extract docket number from regex match based on pattern definition."""
        format_str = pattern_def.get('format', '')
        extraction_groups = pattern_def.get('extraction_groups', [])
        extraction_group = pattern_def.get('extraction_group')  # Single group (legacy)
        
        # Handle single extraction group (legacy format)
        if extraction_group:
            return match.group(extraction_group)
        
        # Handle multiple extraction groups with format string
        if extraction_groups and format_str:
            try:
                # Extract groups
                groups = [match.group(i) for i in extraction_groups]
                
                # Handle special format: {last2ofgroup1}
                if '{last2ofgroup1}' in format_str:
                    if len(groups) > 0 and len(groups[0]) >= 2:
                        last2 = groups[0][-2:]
                        format_str = format_str.replace('{last2ofgroup1}', last2)
                    else:
                        return None
                
                # Replace {groupN} with actual values
                for i, group in enumerate(groups):
                    format_str = format_str.replace(f'{{group{extraction_groups[i]}}}', group)
                
                return format_str
            except (IndexError, AttributeError) as e:
                logging.warning(f"Error extracting from match: {e}")
                return None
        
        # Fallback: try to extract from first group
        try:
            return match.group(1)
        except (IndexError, AttributeError):
            return None
    
    def get_supported_court_types(self, mode: str) -> List[str]:
        """
        Get list of supported court type abbreviations for a mode.
        
        Args:
            mode: 'smd', 'dar', or 'wc'
            
        Returns:
            List of court type abbreviations
        """
        patterns = self.config.get('docket_extraction', {}).get('patterns', {}).get(mode, [])
        court_types = set()
        
        for pattern_def in patterns:
            if 'court_types' in pattern_def:
                court_types.update(pattern_def['court_types'])
        
        return sorted(list(court_types))
    
    def reload_config(self):
        """Reload the configuration file (useful for testing or updates)."""
        self.config = self._load_config()
        self._compile_patterns()
        logging.info("Filename patterns config reloaded")


# Global instance (singleton pattern)
_pattern_config = None


def get_pattern_config() -> FilenamePatternConfig:
    """Get the global pattern config instance."""
    global _pattern_config
    if _pattern_config is None:
        _pattern_config = FilenamePatternConfig()
    return _pattern_config


# Convenience functions that match existing function signatures
def is_counsel(filename: str, dar_mode: bool = False, wc_mode: bool = False) -> bool:
    """
    Check if a filename indicates a counsel/ARC file.
    This function maintains backward compatibility with existing code.
    """
    return get_pattern_config().is_counsel(filename, dar_mode, wc_mode)


def extract_docket_number(filename: str, dar_mode: bool = False, wc_mode: bool = False) -> Optional[str]:
    """
    Extract docket number from filename.
    This function maintains backward compatibility with existing code.
    """
    return get_pattern_config().extract_docket_number(filename, dar_mode, wc_mode)
