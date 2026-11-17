"""Keep unrelated tools' ICU DLLs out of the isolated Windows Qt6 loader."""

import ntpath
import re


def filter_foreign_windows_icu(binaries, *, use_windows_icu):
    """Qt wheels using Windows ICU must not load a PATH-discovered Poppler ICU.

    PyInstaller can collect an unrelated icuuc.dll from PATH even though the
    working source application loads Windows/System32/icuuc.dll. Those DLLs
    expose different symbol names. Only remove the flat unversioned overrides
    and their same-directory data DLLs; keep wheel-supplied/versioned Qt ICU.
    """
    if not use_windows_icu:
        return list(binaries)

    def is_flat_icu(destination):
        normalized = destination.replace("\\", "/")
        return "/" not in normalized and normalized.lower() in {"icu.dll", "icuuc.dll", "icuin.dll"}

    source_dirs = {
        ntpath.normcase(ntpath.dirname(source))
        for destination, source, kind in binaries if is_flat_icu(destination)
    }
    if not source_dirs:
        return list(binaries)
    return [
        (destination, source, kind) for destination, source, kind in binaries
        if not is_flat_icu(destination) and not (
            re.fullmatch(r"icudt\d+\.dll", destination, re.IGNORECASE)
            and ntpath.normcase(ntpath.dirname(source)) in source_dirs
        )
    ]
