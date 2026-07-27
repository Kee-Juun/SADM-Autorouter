"""
Dialog classes for PyQt5 application.

This module contains all dialog classes extracted from smducar_pyqt.py,
including message boxes, confirmation dialogs, console windows, and shop/inventory dialogs.
"""

import sys
import logging
import os
import shutil
from pathlib import Path
from collections import defaultdict

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QScrollArea, QFrame, QMessageBox, QApplication, QMainWindow,
    QFileDialog, QSlider
)
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent, QCoreApplication, QProcess, QPoint
)
from PyQt5.QtGui import QPainter, QColor, QPixmap, QFont, QFontDatabase
from PyQt5.QtCore import QRect, QRectF

# Import dependencies
from core.smducar_config import resource_path
from .pyqt_widgets import CustomTooltipWidget, OverlayWidget

# Import from utils.rewards
from utils.rewards import (
    CUSTOM_WALLPAPER_ID,
    INVENTORY_SECTIONS,
    REWARDS,
    SHOP_SECTIONS,
    custom_wallpaper_exists,
    get_custom_wallpaper_dir,
    get_custom_wallpaper_path,
    get_reward_display_name,
    get_reward_icon,
    get_reward_image_filename,
    get_reward_type_label,
    get_visual_settings,
    is_reward_purchasable,
    load_user_rewards,
    save_user_rewards,
    set_custom_wallpaper_data,
    set_visual_setting,
)

# Define asset paths (same as in smducar_pyqt.py)
ASSETS_DIR = Path(resource_path("assets"))
IMAGES_DIR = ASSETS_DIR / "images"


def _resolve_reward_image_path(reward_id, reward):
    """Return an absolute local image path for a reward preview, if available."""
    image_name = get_reward_image_filename(reward_id, reward)
    if not image_name:
        return None
    image_path = Path(image_name)
    if not image_path.is_absolute():
        image_path = IMAGES_DIR / image_name
    return str(image_path) if image_path.exists() else None


def _font_stack(font_family):
    family = str(font_family or "Segoe UI").replace("'", "")
    return f"'{family}', 'Segoe UI', Arial, sans-serif"


def _font_family_qss(font_family):
    family = str(font_family or "Segoe UI").replace('"', "").replace("'", "")
    return f'"{family}"'


def _catalog_font_family(parent=None):
    if parent and hasattr(parent, "active_ui_font_family"):
        return getattr(parent, "active_ui_font_family") or "Segoe UI"
    try:
        data = load_user_rewards()
        font_reward = REWARDS.get(data.get("equipped", {}).get("font"), {})
        return font_reward.get("font_family") or "Segoe UI"
    except Exception:
        return "Segoe UI"


def _reward_font_family(reward, fallback=None):
    reward = reward or {}
    bundled_family = _load_reward_font_family(reward)
    if bundled_family:
        return bundled_family

    candidates = (
        [reward.get("font_family")]
        + list(reward.get("font_fallbacks", []))
        + [fallback, "Segoe UI", "Arial"]
    )
    available = set()
    if QApplication.instance():
        try:
            available = set(QFontDatabase().families())
        except Exception:
            available = set()
    for family in candidates:
        if family and (not available or family in available):
            return family
    return "Segoe UI"


_LOADED_REWARD_FONT_FAMILIES = {}


def _load_reward_font_family(reward):
    """Load a bundled reward font for previews and return its Qt family name."""
    font_path = (reward or {}).get("font_path")
    if not font_path:
        return None

    resolved_path = Path(resource_path(os.path.join("assets", str(font_path))))
    cache_key = str(resolved_path)
    if cache_key in _LOADED_REWARD_FONT_FAMILIES:
        return _LOADED_REWARD_FONT_FAMILIES[cache_key]
    if not resolved_path.exists() or not QApplication.instance():
        _LOADED_REWARD_FONT_FAMILIES[cache_key] = None
        return None

    try:
        font_id = QFontDatabase.addApplicationFont(str(resolved_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        family = families[0] if families else None
    except Exception:
        family = None
    _LOADED_REWARD_FONT_FAMILIES[cache_key] = family
    return family


def _catalog_dialog_style(font_family=None):
    """Shared game-store styling for Shop and Inventory dialogs."""
    font_stack = _font_stack(font_family)
    return """
        QDialog {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #070A16, stop:0.48 #14142B, stop:1 #071A27);
            color: #F7FBFF;
            border: 1px solid rgba(127, 237, 255, 0.38);
            border-radius: 8px;
        }
        QLabel {
            color: #F7FBFF;
            font-family: """ + font_stack + """;
            background: transparent;
            border: none;
        }
        QWidget {
            background: transparent;
        }
        QScrollArea {
            background: transparent;
            border: none;
        }
    """ + _catalog_scrollbar_style()


def _catalog_scroll_area_style():
    """Modern slim scrollbar treatment for Shop and Inventory scroll panes."""
    return """
        QScrollArea {
            border: none;
            background: transparent;
        }
        QScrollArea > QWidget > QWidget {
            background: transparent;
        }
    """ + _catalog_scrollbar_style()


def _catalog_scrollbar_style():
    """Shared rounded scrollbar chrome for game-catalog surfaces."""
    return """
        QScrollBar:vertical {
            background: rgba(5, 11, 20, 0.48);
            border: 1px solid rgba(126, 241, 255, 0.14);
            width: 12px;
            margin: 4px 1px 4px 1px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(194, 151, 255, 0.95),
                stop:0.48 rgba(126, 241, 255, 0.94),
                stop:1 rgba(21, 179, 165, 0.95));
            border: 1px solid rgba(255, 255, 255, 0.30);
            border-radius: 6px;
            min-height: 42px;
        }
        QScrollBar::handle:vertical:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(224, 182, 255, 1.0),
                stop:0.50 rgba(149, 248, 255, 1.0),
                stop:1 rgba(42, 221, 188, 1.0));
            border: 1px solid rgba(255, 255, 255, 0.52);
        }
        QScrollBar:horizontal {
            background: rgba(5, 11, 20, 0.48);
            border: 1px solid rgba(126, 241, 255, 0.14);
            height: 12px;
            margin: 1px 4px 1px 4px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(194, 151, 255, 0.95),
                stop:0.48 rgba(126, 241, 255, 0.94),
                stop:1 rgba(21, 179, 165, 0.95));
            border: 1px solid rgba(255, 255, 255, 0.30);
            border-radius: 6px;
            min-width: 42px;
        }
        QScrollBar::handle:horizontal:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(224, 182, 255, 1.0),
                stop:0.50 rgba(149, 248, 255, 1.0),
                stop:1 rgba(42, 221, 188, 1.0));
            border: 1px solid rgba(255, 255, 255, 0.52);
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            height: 0px;
            background: transparent;
            border: none;
        }
        QScrollBar::up-arrow:vertical,
        QScrollBar::down-arrow:vertical,
        QScrollBar::left-arrow:horizontal,
        QScrollBar::right-arrow:horizontal {
            width: 0px;
            height: 0px;
            background: transparent;
            border: none;
        }
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: rgba(255, 255, 255, 0.025);
            border-radius: 6px;
        }
        QAbstractScrollArea::corner,
        QScrollArea::corner,
        QScrollBar::corner {
            background: transparent;
            border: none;
        }
    """


def _catalog_title_bar_style():
    return """
        QFrame#CatalogTitleBar {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(126, 76, 255, 0.88),
                stop:0.55 rgba(24, 32, 62, 0.94),
                stop:1 rgba(0, 216, 255, 0.62));
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 8px;
        }
    """


def _catalog_window_button_style(kind="neutral"):
    hover_color = "rgba(255, 80, 142, 0.45)" if kind == "close" else "rgba(126, 241, 255, 0.28)"
    hover_border = "rgba(255, 120, 172, 0.75)" if kind == "close" else "rgba(126, 241, 255, 0.65)"
    return f"""
        QPushButton {{
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 8px;
            color: #F7FBFF;
            font-size: 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background: {hover_color};
            border: 1px solid {hover_border};
        }}
        QPushButton:pressed {{
            background: rgba(255, 255, 255, 0.20);
        }}
    """


def _catalog_summary_style():
    return """
        QFrame#CatalogSummary {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(155, 124, 255, 0.22),
                stop:0.55 rgba(20, 28, 54, 0.86),
                stop:1 rgba(126, 241, 255, 0.16));
            border: 1px solid rgba(126, 241, 255, 0.28);
            border-radius: 8px;
            padding: 10px;
        }
    """


def _catalog_section_style():
    return """
        QFrame#CatalogSection {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 rgba(8, 12, 28, 0.70),
                stop:0.52 rgba(3, 8, 18, 0.82),
                stop:1 rgba(3, 24, 33, 0.54));
            border: 1px solid rgba(126, 241, 255, 0.16);
            border-radius: 8px;
            padding: 7px;
        }
    """


CATALOG_CATEGORY_META = {
    "skin": {
        "accent": "#9CF4FF",
        "secondary": "#A981FF",
    },
    "header": {
        "accent": "#FFD36E",
        "secondary": "#FF67B5",
    },
    "font": {
        "accent": "#C9F7A2",
        "secondary": "#7EF1FF",
    },
    "emoji": {
        "accent": "#FF9CCF",
        "secondary": "#FFD36E",
    },
    "badge": {
        "accent": "#D9B8FF",
        "secondary": "#7EF1FF",
    },
    "game": {
        "accent": "#7EF1FF",
        "secondary": "#41FFB8",
    },
}


def _hex_to_rgb(hex_color):
    color = hex_color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _rgba(hex_color, alpha):
    r, g, b = _hex_to_rgb(hex_color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _catalog_category_meta(reward_type):
    return CATALOG_CATEGORY_META.get(
        reward_type,
        {
            "accent": "#9CF4FF",
            "secondary": "#A981FF",
        },
    )


def _catalog_category_header_style(reward_type, expanded=False):
    meta = _catalog_category_meta(reward_type)
    accent = meta["accent"]
    secondary = meta["secondary"]
    border_alpha = 0.70 if expanded else 0.32
    start_alpha = 0.28 if expanded else 0.15
    end_alpha = 0.22 if expanded else 0.11
    return f"""
        QFrame#CatalogCategoryHeader {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_rgba(accent, start_alpha)},
                stop:0.42 rgba(9, 15, 31, 0.96),
                stop:1 {_rgba(secondary, end_alpha)});
            border: 1px solid {_rgba(accent, border_alpha)};
            border-radius: 8px;
        }}
        QFrame#CatalogCategoryHeader:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {_rgba(accent, 0.34)},
                stop:0.44 rgba(16, 22, 43, 0.98),
                stop:1 {_rgba(secondary, 0.27)});
            border: 1px solid {_rgba(accent, 0.86)};
        }}
        QFrame#CatalogCategoryRail {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {_rgba(accent, 0.98)}, stop:1 {_rgba(secondary, 0.92)});
            border: none;
            border-radius: 2px;
        }}
        QLabel#CatalogCategoryTitle {{
            color: #FFFFFF;
            font-size: 15px;
            font-weight: 900;
            letter-spacing: 0px;
        }}
        QLabel#CatalogCategorySubtitle {{
            color: {_rgba(accent, 0.88)};
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0px;
        }}
        QLabel#CatalogCategoryAction {{
            background: {_rgba(accent, 0.12)};
            color: #FFFFFF;
            border: 1px solid {_rgba(accent, 0.46)};
            border-radius: 8px;
            padding: 5px 9px;
            font-size: 10px;
            font-weight: 900;
            letter-spacing: 0px;
        }}
    """


def _catalog_category_item_text(count, inventory=False):
    noun = "OWNED" if inventory else ("UNLOCKABLE" if count == 1 else "UNLOCKABLES")
    return f"{count} {noun}"


def _catalog_category_action_text(expanded=False):
    return "CLOSE" if expanded else "OPEN"


def _is_equipped_reward(user_data, reward_id, reward):
    reward_type = (reward or {}).get("type")
    if not reward_type:
        return False
    return (user_data or {}).get("equipped", {}).get(reward_type) == reward_id


def _equipped_first(entries, user_data):
    """Lift the equipped item while preserving the category's normal order."""
    return [
        entry
        for _, entry in sorted(
            enumerate(entries),
            key=lambda pair: (
                0 if _is_equipped_reward(user_data, pair[1][0], pair[1][1]) else 1,
                pair[0],
            ),
        )
    ]


def _transparent_to_mouse(*widgets):
    for widget in widgets:
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)


def _create_catalog_category_header(reward_type, section_title, item_count, inventory, toggle_callback):
    """Create a clean clickable catalog accordion header."""
    header_frame = QFrame()
    header_frame.setObjectName("CatalogCategoryHeader")
    header_frame.setCursor(Qt.PointingHandCursor)
    header_frame.setFixedHeight(58)
    header_frame.setStyleSheet(_catalog_category_header_style(reward_type, False))
    header_frame.setAttribute(Qt.WA_Hover, True)

    header_layout = QHBoxLayout(header_frame)
    header_layout.setContentsMargins(10, 8, 10, 8)
    header_layout.setSpacing(10)

    rail = QFrame()
    rail.setObjectName("CatalogCategoryRail")
    rail.setFixedSize(4, 34)
    header_layout.addWidget(rail)

    text_layout = QVBoxLayout()
    text_layout.setSpacing(1)
    title_label = QLabel(section_title)
    title_label.setObjectName("CatalogCategoryTitle")
    title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    subtitle_label = QLabel(_catalog_category_item_text(item_count, inventory))
    subtitle_label.setObjectName("CatalogCategorySubtitle")
    subtitle_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    text_layout.addWidget(title_label)
    text_layout.addWidget(subtitle_label)
    header_layout.addLayout(text_layout, 1)

    action_label = QLabel(_catalog_category_action_text(False))
    action_label.setObjectName("CatalogCategoryAction")
    action_label.setAlignment(Qt.AlignCenter)
    action_label.setFixedWidth(58)
    header_layout.addWidget(action_label)

    _transparent_to_mouse(
        rail,
        title_label,
        subtitle_label,
        action_label,
    )

    def mouse_release(event, key=reward_type):
        if event.button() == Qt.LeftButton:
            toggle_callback(key)
            event.accept()

    header_frame.mouseReleaseEvent = mouse_release
    return header_frame, action_label


def _catalog_item_style(focused=False):
    border = "rgba(255, 213, 112, 0.92)" if focused else "rgba(126, 241, 255, 0.22)"
    bg_a = "rgba(255, 213, 112, 0.18)" if focused else "rgba(255, 255, 255, 0.075)"
    bg_b = "rgba(126, 241, 255, 0.10)" if focused else "rgba(126, 241, 255, 0.045)"
    return f"""
        QFrame#CatalogItem {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {bg_a}, stop:1 {bg_b});
            border: 1px solid {border};
            border-radius: 8px;
            padding: 8px;
            margin: 2px;
        }}
        QFrame#CatalogItem:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(155, 124, 255, 0.20), stop:1 rgba(126, 241, 255, 0.12));
            border: 1px solid rgba(156, 244, 255, 0.60);
        }}
    """


def _catalog_icon_slot_style():
    return """
        QFrame#CatalogIconSlot {
            background: qradialgradient(cx:0.50, cy:0.42, radius:0.78,
                stop:0 rgba(255, 255, 255, 0.16),
                stop:0.48 rgba(155, 124, 255, 0.14),
                stop:1 rgba(0, 0, 0, 0.18));
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 8px;
            padding: 0px;
        }
    """


def _catalog_font_preview_style(font_family, inventory=False):
    size = 13 if inventory else 14
    return f"""
        QLabel {{
            color: #F7FBFF;
            font-family: {_font_family_qss(font_family)};
            font-size: {size}px;
            font-weight: 900;
            background: transparent;
            border: none;
            padding: 0px 4px;
        }}
    """


def _catalog_button_style(kind):
    styles = {
        "owned": ("#34D6C5", "#8EFFF1", "#051E24"),
        "buy": ("#FFD36E", "#FF8A3D", "#171009"),
        "equip": ("#C9A7FF", "#7EF1FF", "#07111A"),
        "unequip": ("#FF6D8F", "#FF3D68", "#1E070D"),
        "disabled": ("#4D5261", "#343844", "#A2A7B5"),
        "launch": ("#7EF1A8", "#20D19B", "#06190F"),
    }
    start, end, text = styles.get(kind, styles["buy"])
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {start}, stop:1 {end});
            color: {text};
            border: 1px solid rgba(255, 255, 255, 0.24);
            border-radius: 7px;
            padding: 8px 16px;
            font-weight: 800;
            font-size: 12px;
            min-width: 84px;
        }}
        QPushButton:hover {{
            border: 1px solid rgba(255, 255, 255, 0.62);
        }}
        QPushButton:disabled {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #4D5261, stop:1 #343844);
            color: #A2A7B5;
            border: 1px solid rgba(255, 255, 255, 0.10);
        }}
    """


def _catalog_toggle_button_style(enabled):
    start = "#41FFB8" if enabled else "#343844"
    end = "#7EF1FF" if enabled else "#4D5261"
    text = "#041A18" if enabled else "#D5DAE6"
    border = "rgba(126, 241, 255, 0.68)" if enabled else "rgba(255, 255, 255, 0.18)"
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {start}, stop:1 {end});
            color: {text};
            border: 1px solid {border};
            border-radius: 14px;
            padding: 7px 13px;
            font-weight: 900;
            font-size: 11px;
            min-width: 72px;
        }}
        QPushButton:hover {{
            border: 1px solid rgba(255, 211, 110, 0.76);
        }}
    """


def _catalog_setting_row_style():
    return """
        QFrame#CatalogSettingRow {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(217, 184, 255, 0.15),
                stop:0.52 rgba(9, 15, 31, 0.94),
                stop:1 rgba(126, 241, 255, 0.12));
            border: 1px solid rgba(217, 184, 255, 0.32);
            border-radius: 8px;
            padding: 8px;
            margin: 2px;
        }
        QFrame#CatalogSettingRow:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(217, 184, 255, 0.22),
                stop:0.52 rgba(14, 20, 39, 0.98),
                stop:1 rgba(126, 241, 255, 0.18));
            border: 1px solid rgba(126, 241, 255, 0.58);
        }
    """


def _catalog_icon_size(reward_type, inventory=False):
    """Stable item icon slots prevent emoji and badge previews from clipping."""
    if reward_type == "header":
        return (92, 64) if not inventory else (84, 58)
    if reward_type == "emoji":
        return (76, 76) if not inventory else (70, 70)
    if reward_type == "font":
        return (148, 58) if not inventory else (132, 54)
    return (72, 72) if not inventory else (66, 66)


class CustomWallpaperPreviewWidget(QWidget):
    """Interactive crop preview for user-provided app wallpapers."""

    OUTPUT_WIDTH = 800
    OUTPUT_HEIGHT = 1040

    def __init__(self, source_path, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path)
        self.source_pixmap = QPixmap(str(self.source_path))
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self._drag_start = None
        self._drag_offset_start = (0, 0)
        self.setFixedSize(260, 338)
        self.setCursor(Qt.OpenHandCursor)
        if self.source_pixmap.isNull():
            logging.warning("Custom wallpaper preview could not read image: %s", self.source_path)
        else:
            logging.info(
                "Custom wallpaper preview loaded: source=%s source_size=%sx%s target_size=%sx%s",
                self.source_path,
                self.source_pixmap.width(),
                self.source_pixmap.height(),
                self.OUTPUT_WIDTH,
                self.OUTPUT_HEIGHT,
            )

    def has_valid_image(self):
        return not self.source_pixmap.isNull()

    def set_zoom_percent(self, value):
        self.zoom = max(1.0, min(2.4, value / 100.0))
        self._clamp_offsets()
        logging.debug("Custom wallpaper preview zoom changed to %s%%", value)
        self.update()

    def reset_fit(self):
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        logging.info("Custom wallpaper preview reset to centered fit.")
        self.update()

    def output_offsets(self):
        preview_w = max(1, self.width())
        preview_h = max(1, self.height())
        return (
            int(self.offset_x * (self.OUTPUT_WIDTH / preview_w)),
            int(self.offset_y * (self.OUTPUT_HEIGHT / preview_h)),
        )

    def _scaled_dimensions(self, canvas_w=None, canvas_h=None):
        canvas_w = canvas_w or max(1, self.width())
        canvas_h = canvas_h or max(1, self.height())
        source_w = max(1, self.source_pixmap.width())
        source_h = max(1, self.source_pixmap.height())
        cover_scale = max(canvas_w / source_w, canvas_h / source_h)
        scale = cover_scale * self.zoom
        return int(source_w * scale), int(source_h * scale)

    def _clamp_offsets(self):
        scaled_w, scaled_h = self._scaled_dimensions()
        max_x = max(0, int((scaled_w - self.width()) / 2))
        max_y = max(0, int((scaled_h - self.height()) / 2))
        self.offset_x = max(-max_x, min(max_x, int(self.offset_x)))
        self.offset_y = max(-max_y, min(max_y, int(self.offset_y)))

    def _target_rect(self, canvas_w, canvas_h, output_scale=False):
        scaled_w, scaled_h = self._scaled_dimensions(canvas_w, canvas_h)
        offset_x = self.offset_x
        offset_y = self.offset_y
        if output_scale:
            preview_w = max(1, self.width())
            preview_h = max(1, self.height())
            offset_x = int(self.offset_x * (canvas_w / preview_w))
            offset_y = int(self.offset_y * (canvas_h / preview_h))
        x = int((canvas_w - scaled_w) / 2) + offset_x
        y = int((canvas_h - scaled_h) / 2) + offset_y
        return QRectF(x, y, scaled_w, scaled_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        bounds = QRectF(0, 0, self.width(), self.height())
        painter.fillRect(bounds, QColor(7, 10, 22))

        if self.has_valid_image():
            source_rect = QRectF(0, 0, self.source_pixmap.width(), self.source_pixmap.height())
            painter.drawPixmap(self._target_rect(self.width(), self.height()), self.source_pixmap, source_rect)
        else:
            painter.setPen(QColor(255, 211, 110))
            painter.setFont(QFont(_catalog_font_family(self.parent()), 12, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "IMAGE NOT READABLE")

        painter.setPen(QColor(126, 241, 255, 155))
        painter.drawRoundedRect(bounds.adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
        painter.setPen(QColor(255, 255, 255, 60))
        painter.drawRoundedRect(bounds.adjusted(8, 8, -8, -8), 11, 11)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.has_valid_image():
            self._drag_start = event.pos()
            self._drag_offset_start = (self.offset_x, self.offset_y)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        delta = event.pos() - self._drag_start
        self.offset_x = self._drag_offset_start[0] + delta.x()
        self.offset_y = self._drag_offset_start[1] + delta.y()
        self._clamp_offsets()
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()

    def export(self, output_path):
        if not self.has_valid_image():
            logging.warning("Custom wallpaper export skipped because the source image was unreadable.")
            return False
        output = QPixmap(self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT)
        output.fill(QColor(7, 10, 22))
        painter = QPainter(output)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        source_rect = QRectF(0, 0, self.source_pixmap.width(), self.source_pixmap.height())
        painter.drawPixmap(
            self._target_rect(self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT, output_scale=True),
            self.source_pixmap,
            source_rect,
        )
        painter.end()
        saved = output.save(str(output_path), "PNG")
        logging.info(
            "Custom wallpaper resized/exported: output=%s output_size=%sx%s zoom=%.3f preview_offset=(%s,%s) saved=%s",
            output_path,
            self.OUTPUT_WIDTH,
            self.OUTPUT_HEIGHT,
            self.zoom,
            self.offset_x,
            self.offset_y,
            saved,
        )
        return saved


class CustomWallpaperDialog(QDialog):
    """Compact import/crop dialog for custom user wallpapers."""

    def __init__(self, source_path, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path)
        self.result_data = None
        self.catalog_font_family = _catalog_font_family(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setWindowTitle("Custom Wallpaper")
        self.setFixedWidth(420)
        self.setStyleSheet(_catalog_dialog_style(self.catalog_font_family))
        self.setFont(QFont(self.catalog_font_family, 10))

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        title_bar = QFrame()
        title_bar.setObjectName("CatalogTitleBar")
        title_bar.setFixedHeight(44)
        title_bar.setStyleSheet(_catalog_title_bar_style())
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(14, 7, 14, 7)

        title_label = QLabel("CUSTOM WALLPAPER")
        title_label.setStyleSheet("font-size: 14px; font-weight: 900; color: white;")
        close_button = QPushButton("X")
        close_button.setFixedSize(28, 28)
        close_button.setStyleSheet(_catalog_window_button_style("close"))
        close_button.clicked.connect(self.reject)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_button)
        layout.addWidget(title_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(12)
        body_layout.setContentsMargins(18, 16, 18, 18)

        self.preview = CustomWallpaperPreviewWidget(self.source_path, self)
        body_layout.addWidget(self.preview, alignment=Qt.AlignCenter)

        hint = QLabel("Drag to frame the image. Adjust zoom, then equip.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 12px; color: rgba(247, 251, 255, 0.72);")
        body_layout.addWidget(hint)

        zoom_row = QHBoxLayout()
        zoom_label = QLabel("ZOOM")
        zoom_label.setStyleSheet("font-size: 11px; font-weight: 900; color: #FFD36E;")
        self.zoom_value_label = QLabel("100%")
        self.zoom_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.zoom_value_label.setStyleSheet("font-size: 11px; font-weight: 900; color: #7EF1FF;")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(100, 240)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: rgba(255, 255, 255, 0.12);
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #FFD36E, stop:1 #7EF1FF);
                border: 1px solid rgba(255, 255, 255, 0.65);
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #A981FF, stop:1 #7EF1FF);
                border-radius: 4px;
            }
        """)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        zoom_row.addWidget(zoom_label)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value_label)
        body_layout.addLayout(zoom_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        reset_button = QPushButton("RESET FIT")
        reset_button.setStyleSheet(_catalog_button_style("disabled"))
        reset_button.clicked.connect(self.reset_fit)
        cancel_button = QPushButton("CANCEL")
        cancel_button.setStyleSheet(_catalog_button_style("disabled"))
        cancel_button.clicked.connect(self.reject)
        equip_button = QPushButton("EQUIP")
        equip_button.setStyleSheet(_catalog_button_style("equip"))
        equip_button.clicked.connect(self.save_and_accept)
        action_row.addWidget(reset_button)
        action_row.addStretch()
        action_row.addWidget(cancel_button)
        action_row.addWidget(equip_button)
        body_layout.addLayout(action_row)

        layout.addWidget(body)

        if not self.preview.has_valid_image():
            QTimer.singleShot(0, self.show_unreadable_warning)

        self._drag_position = None
        title_bar.mousePressEvent = self.title_bar_mouse_press
        title_bar.mouseMoveEvent = self.title_bar_mouse_move

    def on_zoom_changed(self, value):
        self.zoom_value_label.setText(f"{value}%")
        self.preview.set_zoom_percent(value)

    def reset_fit(self):
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(100)
        self.zoom_slider.blockSignals(False)
        self.zoom_value_label.setText("100%")
        self.preview.reset_fit()

    def show_unreadable_warning(self):
        ModernMessageBox(
            "Image Not Readable",
            "That image could not be opened. Please choose a PNG, JPG, JPEG, WEBP, or BMP file.",
            "warning",
            self,
        ).exec_()
        self.reject()

    def save_and_accept(self):
        try:
            logging.info("Custom wallpaper crop confirmation started for source=%s", self.source_path)
            wallpaper_dir = get_custom_wallpaper_dir()
            source_suffix = self.source_path.suffix.lower()
            if source_suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                source_suffix = ".png"
            source_copy = wallpaper_dir / f"custom_wallpaper_source{source_suffix}"
            processed_path = wallpaper_dir / "custom_wallpaper.png"

            try:
                if self.source_path.resolve(strict=False) != source_copy.resolve(strict=False):
                    shutil.copy2(str(self.source_path), str(source_copy))
                    logging.info("Custom wallpaper source copied: %s -> %s", self.source_path, source_copy)
            except Exception as exc:
                logging.warning(f"Could not copy custom wallpaper source image: {exc}")
                source_copy = self.source_path

            if not self.preview.export(processed_path):
                raise OSError("Qt could not save the cropped wallpaper preview.")

            offset_x, offset_y = self.preview.output_offsets()
            self.result_data = {
                "source_path": str(source_copy),
                "processed_path": str(processed_path),
                "zoom": round(self.preview.zoom, 3),
                "offset_x": offset_x,
                "offset_y": offset_y,
            }
            logging.info(
                "Custom wallpaper crop accepted: processed=%s zoom=%s output_offset=(%s,%s)",
                processed_path,
                self.result_data["zoom"],
                offset_x,
                offset_y,
            )
            self.accept()
        except Exception as exc:
            logging.error(f"Failed saving custom wallpaper: {exc}")
            ModernMessageBox(
                "Wallpaper Not Saved",
                f"The wallpaper could not be saved:\n{exc}",
                "error",
                self,
            ).exec_()

    def title_bar_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def title_bar_mouse_move(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position:
            self.move(event.globalPos() - self._drag_position)
            event.accept()

# TetrisGame will be imported lazily in launch_game() to avoid circular imports
# (pyqt_tetris imports from pyqt_dialogs, so we can't import it at module level)


class LogConsoleWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 300)
        # Remove title bar completely and keep window on top
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        # Enable window transparency
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Store the initial position flag
        self._position_initialized = False
        
        # Create main layout with larger margins for better shadow visibility
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(0)
        
        # Create a container widget for the frosted glass effect
        container = QWidget(self)
        container.setObjectName("container")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Create custom title bar
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(40)
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(15, 0, 15, 0)
        
        # Add title label
        title_label = QLabel("Console")
        title_label.setObjectName("titleLabel")
        title_bar_layout.addWidget(title_label)
        
        # Add maximize/restore and close buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        max_btn = QPushButton("□")
        max_btn.setObjectName("maxButton")
        max_btn.setFixedSize(16, 16)
        max_btn.clicked.connect(self.toggle_maximize)
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(self.on_close_clicked)
        
        btn_layout.addWidget(max_btn)
        btn_layout.addWidget(close_btn)
        title_bar_layout.addLayout(btn_layout)
        
        # Create text edit
        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        
        # Add shadow effect to the container
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 0)
        container.setGraphicsEffect(shadow)
        
        # Style the text edit and container
        container.setStyleSheet("""
            #container {
                background-color: rgba(28, 28, 35, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
            #titleBar {
                background-color: rgba(20, 20, 25, 0.4);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            #titleLabel {
                color: rgba(255, 255, 255, 0.85);
                font-family: "Segoe UI", sans-serif;
                font-size: 11pt;
                font-weight: 500;
            }
            #maxButton, #closeButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 8px;
                color: rgba(255, 255, 255, 0.8);
                font-family: "Segoe UI", sans-serif;
                font-size: 10pt;
                padding: 0px;
            }
            #maxButton:hover, #closeButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            #maxButton:pressed, #closeButton:pressed {
                background-color: rgba(255, 255, 255, 0.05);
            }
            #closeButton:hover {
                background-color: rgba(255, 100, 100, 0.3);
            }
        """)
        
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(20, 20, 25, 0.4);
                color: rgba(255, 255, 255, 0.95);
                border: none;
                border-radius: 0px 0px 12px 12px;
                padding: 12px;
                selection-background-color: rgba(110, 64, 192, 0.5);
                font-family: "Segoe UI", Consolas, monospace;
                font-size: 10.5pt;
                line-height: 1.5;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.05);
                width: 10px;
                border-radius: 5px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(110, 64, 192, 0.6);
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(110, 64, 192, 0.8);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                height: 0px;
                background: none;
            }
        """)
        
        # Add widgets to layouts
        container_layout.addWidget(title_bar)
        container_layout.addWidget(self.text_edit)
        layout.addWidget(container)
        
        # Style the main window
        self.setStyleSheet("""
            LogConsoleWindow {
                background-color: transparent;
            }
        """)
        
        # Set window opacity for overall translucency
        self.setWindowOpacity(0.98)
        
        # Store initial position for dragging
        self._drag_pos = None

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def on_close_clicked(self):
        """Handle close button click - close console and turn off toggle"""
        # Turn off the console toggle in the parent window
        if self.parent() and hasattr(self.parent(), 'on_console_toggle'):
            # Only call if the toggle is currently ON
            if hasattr(self.parent(), 'console_toggle') and self.parent().console_toggle.state:
                self.parent().on_console_toggle(False)
        # Close the console window
        self.close()

    def closeEvent(self, event):
        """Handle close event - turn off the console toggle"""
        # Turn off the console toggle in the parent window
        if self.parent() and hasattr(self.parent(), 'on_console_toggle'):
            # Only call if the toggle is currently ON
            if hasattr(self.parent(), 'console_toggle') and self.parent().console_toggle.state:
                self.parent().on_console_toggle(False)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if the click is in the title bar area
            if event.pos().y() <= 40:  # Height of title bar
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

    def append_text(self, text):
        self.text_edit.appendPlainText(text)
        self.text_edit.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().maximum())

    def showEvent(self, event):
        super().showEvent(event)
        if not self._position_initialized:
            self.position_window()
            self._position_initialized = True
        
    def position_window(self):
        """Position the console window in a suitable location relative to the main window"""
        if self.parent():
            main_window = self.parent()
            main_geo = main_window.geometry()
            
            # Get the available screen geometry
            screen = QApplication.primaryScreen()
            screen_geo = screen.availableGeometry()
            
            # Calculate the desired position (top right of main window)
            new_x = min(main_geo.right(), screen_geo.width() - self.width())
            new_y = max(0, main_geo.top())
            
            # If this would put us off screen, adjust
            if new_x + self.width() > screen_geo.width():
                new_x = screen_geo.width() - self.width()
            if new_y + self.height() > screen_geo.height():
                new_y = screen_geo.height() - self.height()
            
            self.move(new_x, new_y)
    
    def check_and_reposition(self):
        """Check if console is blocking the center of main window and reposition if needed"""
        if self.parent() and self.isVisible():
            main_window = self.parent()
            main_geo = main_window.geometry()
            console_geo = self.geometry()
            
            # Calculate the center area of the main window (where success message appears)
            center_x = main_geo.x() + main_geo.width() // 2
            center_y = main_geo.y() + main_geo.height() // 2
            
            # Check if console overlaps with the center area
            if (console_geo.contains(center_x, center_y) or
                (abs(console_geo.center().x() - center_x) < 100 and  # Within 100 pixels horizontally
                 abs(console_geo.center().y() - center_y) < 100)):   # Within 100 pixels vertically
                self.position_window()

    def show(self):
        super().show()
        # Small delay to ensure window is fully shown before repositioning
        QTimer.singleShot(100, self.check_and_reposition)


class NotificationPopup(QDialog):
    def __init__(self, parent, text):
        super().__init__(parent)
        font_family = _catalog_font_family(parent)
        self.setFont(QFont(font_family, 10))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setModal(True)

        self.radius = 20
        self.shadow_thickness = 12
        self.bg_color = QColor(128, 0, 200, 200)  # Purple, semi-transparent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self.shadow_thickness, self.shadow_thickness,
                                  self.shadow_thickness, self.shadow_thickness)

        label = QLabel(text, self)
        label.setFont(QFont(font_family, 11, QFont.Bold))
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            color: white;
            font-size: 15px;
            font-weight: bold;
            padding: 24px 36px;
            background: transparent;
        """)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setLayout(layout)
        self.adjustSize()

        self.setWindowOpacity(0.0)

        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade_anim.start()

        # Expand window to include space for shadow
        extra = self.shadow_thickness
        self.resize(self.width() + extra * 2, self.height() + extra * 2)

        # Handle mouse press for congratulations popup
        if 'Congratulations' in text:
            self.mousePressEvent = lambda event: self.handle_congratulations_click()
        else:
            self.mousePressEvent = lambda event: self.accept()
    
    def handle_congratulations_click(self):
        """Handle click on congratulations popup to restart the app"""
        try:
            # Close the popup first
            self.accept()
            
            # Restart the app after a short delay
            QTimer.singleShot(100, lambda: QProcess.startDetached(sys.executable, sys.argv))
            QCoreApplication.quit()
            
        except Exception as e:
            logging.error(f"Error restarting app: {e}")
            # Fallback: just close the popup
            self.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRect(
            self.shadow_thickness,
            self.shadow_thickness,
            self.width() - 2 * self.shadow_thickness,
            self.height() - 2 * self.shadow_thickness
        )

        # Draw soft shadow manually
        shadow_color = QColor(0, 0, 0)  # pure black

        # Draw background rectangle
        painter.setBrush(self.bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.radius, self.radius)


class ModernMessageBox(QDialog):
    """Modern styled message box with frosted glass effect"""
    def __init__(self, title, message, msg_type="info", parent=None):
        super().__init__(parent)
        font_family = _catalog_font_family(parent)
        self.setFont(QFont(font_family, 10))
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 400)  # Increased height to give content and button more room
        
        # Setup layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 15, 25, 35)
        
        # Main container with frosted glass effect
        main_container = QWidget()
        main_container.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(120, 120, 140, 0.85),
                    stop:0.5 rgba(140, 140, 160, 0.8),
                    stop:1 rgba(120, 120, 140, 0.85));
                border-radius: 25px;
                border: 2px solid rgba(255, 255, 255, 0.4);
            }}
        """)
        
        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(36, 24, 36, 44)
        container_layout.setSpacing(20)  # Extra top spacing to avoid content cropping under header
        
        # Title label
        title_label = QLabel(title)
        title_label.setFont(QFont(font_family, 14, QFont.Bold))
        title_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(255, 255, 255, 1.0);
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                background: transparent;
                border: none;
                
                padding: 10px;
            }}
        """)
        title_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title_label)
        
        # Message area with scrolling capability
        message_scroll = QScrollArea()
        message_scroll.setWidgetResizable(True)
        message_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Message label inside scroll area
        message_label = QLabel(message)
        # Dynamically adjust font size based on message length for comfortable readability
        try:
            total_lines = max(1, len(message.splitlines()))
            total_chars = len(message)
        except Exception:
            total_lines = 1
            total_chars = 0
        if total_lines > 30 or total_chars > 1500:
            body_font_px = 11
        elif total_lines > 20 or total_chars > 1000:
            body_font_px = 12
        elif total_lines > 12 or total_chars > 700:
            body_font_px = 13
        else:
            body_font_px = 14
        message_label.setFont(QFont(font_family, max(9, body_font_px - 2), QFont.DemiBold))
        message_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(255, 255, 255, 1.0);
                font-size: {body_font_px}px;
                text-align: center;
                background: transparent;
                border: none;
                font-weight: 600;
                padding: 12px;
                line-height: 1.5;
                min-height: 70px;
            }}
        """)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setMinimumHeight(70)
        # Add a small internal top margin to ensure first line never appears cropped
        message_label.setContentsMargins(0, 6, 0, 0)
        
        # Set the message label as the scroll area widget
        message_scroll.setWidget(message_label)
        message_scroll.setMinimumHeight(70)
        message_scroll.setMaximumHeight(260)
        
        container_layout.addWidget(message_scroll)
        
        # Button container
        button_container = QWidget()
        button_container.setStyleSheet("QWidget { background: transparent; border: none; }")
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(8, 6, 8, 6)  # Slightly tighter outer padding to avoid bottom cropping
        button_layout.setSpacing(10)
        
        # OK button
        ok_button = QPushButton("OK")
        ok_button.setFont(QFont(font_family, 11, QFont.Bold))
        ok_button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(108, 60, 255, 0.9),
                    stop:0.5 rgba(180, 80, 200, 0.9),
                    stop:1 rgba(255, 79, 163, 0.9));
                border-radius: 18px;
                border: 2px solid rgba(255, 255, 255, 0.4);
                color: rgba(255, 255, 255, 1.0);
                font-weight: bold;
                font-size: 14px;
                padding: 10px 25px;
                min-width: 100px;
                min-height: 35px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 79, 163, 0.9),
                    stop:0.5 rgba(200, 100, 255, 0.9),
                    stop:1 rgba(0, 224, 255, 0.9));
                border: 2px solid rgba(255, 255, 255, 0.7);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(80, 40, 200, 0.9),
                    stop:0.5 rgba(150, 60, 180, 0.9),
                    stop:1 rgba(200, 60, 120, 0.9));
            }}
        """)
        
        # Connect button to close dialog
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button, alignment=Qt.AlignCenter)
        
        container_layout.addWidget(button_container)
        layout.addWidget(main_container)
        
        # Center the dialog on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )


class ModernConfirmDialog(QDialog):
    """Modern styled confirmation dialog with Yes/No buttons"""
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        font_family = _catalog_font_family(parent)
        self.setFont(QFont(font_family, 10))
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 380)  # Increased height to give content and buttons more room
        
        # Setup layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 15, 25, 35)
        
        # Main container with frosted glass effect
        main_container = QWidget()
        main_container.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(120, 120, 140, 0.85),
                    stop:0.5 rgba(140, 140, 160, 0.8),
                    stop:1 rgba(120, 120, 140, 0.85));
                border-radius: 25px;
                border: 2px solid rgba(255, 255, 255, 0.4);
            }}
        """)
        
        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(36, 24, 36, 44)
        container_layout.setSpacing(15)  # Comfortable spacing between header and content
        
        # Title label
        title_label = QLabel(title)
        title_label.setFont(QFont(font_family, 14, QFont.Bold))
        title_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(255, 255, 255, 1.0);
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                background: transparent;
                border: none;
                
                padding: 10px;
            }}
        """)
        title_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title_label)
        
        # Compute dynamic font size for message content based on content length/lines
        try:
            num_lines = (message.count("\n") + 1) if isinstance(message, str) else 1
            msg_len = len(message) if isinstance(message, str) else 0
        except Exception:
            num_lines = 1
            msg_len = 0
        content_font_size = 14
        if msg_len > 1400 or num_lines > 28:
            content_font_size = 11
        elif msg_len > 1000 or num_lines > 22:
            content_font_size = 12
        elif msg_len > 700 or num_lines > 16:
            content_font_size = 13

        # Message area with scrolling capability
        message_scroll = QScrollArea()
        message_scroll.setWidgetResizable(True)
        message_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
                border-radius: 10px;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.1);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        # Message label inside scroll area
        message_label = QLabel(message)
        message_label.setFont(QFont(font_family, max(9, content_font_size - 2), QFont.DemiBold))
        message_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(255, 255, 255, 1.0);
                font-size: {content_font_size}px;
                text-align: center;
                background: transparent;
                border: none;
                font-weight: 600;
                padding: 12px;
                line-height: 1.5;
                min-height: 70px;
            }}
        """)
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setMinimumHeight(70)
        
        # Set the message label as the scroll area widget
        message_scroll.setWidget(message_label)
        message_scroll.setMinimumHeight(70)
        message_scroll.setMaximumHeight(240)
        
        container_layout.addWidget(message_scroll)
        
        # Button container
        button_container = QWidget()
        button_container.setStyleSheet("QWidget { background: transparent; border: none; }")
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(12, 8, 12, 12)  # Comfortable margins so the buttons can breathe
        button_layout.setSpacing(10)
        
        # No button (left)
        no_button = QPushButton("No")
        no_button.setFont(QFont(font_family, 11, QFont.Bold))
        no_button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(100, 100, 100, 0.9),
                    stop:0.5 rgba(120, 120, 120, 0.9),
                    stop:1 rgba(100, 100, 100, 0.9));
                border-radius: 18px;
                border: 2px solid rgba(255, 255, 255, 0.4);
                color: rgba(255, 255, 255, 1.0);
                font-weight: bold;
                font-size: 14px;
                padding: 10px 25px;
                min-width: 100px;
                min-height: 35px;
                
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(120, 120, 120, 0.9),
                    stop:0.5 rgba(140, 140, 140, 0.9),
                    stop:1 rgba(120, 120, 120, 0.9));
                border: 2px solid rgba(255, 255, 255, 0.7);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(80, 80, 80, 0.9),
                    stop:0.5 rgba(100, 100, 100, 0.9),
                    stop:1 rgba(80, 80, 80, 0.9));
                
            }}
        """)
        
        # Yes button (right)
        yes_button = QPushButton("Yes")
        yes_button.setFont(QFont(font_family, 11, QFont.Bold))
        yes_button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(108, 60, 255, 0.9),
                    stop:0.5 rgba(180, 80, 200, 0.9),
                    stop:1 rgba(255, 79, 163, 0.9));
                border-radius: 18px;
                border: 2px solid rgba(255, 255, 255, 0.4);
                color: rgba(255, 255, 255, 1.0);
                font-weight: bold;
                font-size: 14px;
                padding: 10px 25px;
                min-width: 100px;
                min-height: 35px;
                
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 79, 163, 0.9),
                    stop:0.5 rgba(200, 100, 255, 0.9),
                    stop:1 rgba(0, 224, 255, 0.9));
                border: 2px solid rgba(255, 255, 255, 0.7);
                
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(80, 40, 200, 0.9),
                    stop:0.5 rgba(150, 60, 180, 0.9),
                    stop:1 rgba(200, 60, 120, 0.9));
                
            }}
        """)
        
        # Connect buttons
        no_button.clicked.connect(self.reject)
        yes_button.clicked.connect(self.accept)
        
        button_layout.addWidget(no_button, alignment=Qt.AlignCenter)
        button_layout.addWidget(yes_button, alignment=Qt.AlignCenter)
        
        container_layout.addWidget(button_container)
        layout.addWidget(main_container)
        
        # Center the dialog on screen
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )






class ShopDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shop_tooltip = None
        self._category_sections = {}
        self._expanded_category = None
        self.catalog_font_family = _catalog_font_family(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.finished.connect(self.deleteLater)
        self.setWindowTitle("Shop")
        self.setMinimumWidth(560)
        self.setMinimumHeight(660)
        
        # Set up frameless window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setStyleSheet(_catalog_dialog_style(self.catalog_font_family))
        self.setFont(QFont(self.catalog_font_family, 10))
        
        self.user_data = load_user_rewards()
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(12)
        self.layout.setContentsMargins(14, 14, 14, 14)
        

        
        # Custom title bar
        title_bar = QFrame()
        title_bar.setObjectName("CatalogTitleBar")
        title_bar.setFixedHeight(44)
        title_bar.setStyleSheet(_catalog_title_bar_style())
        
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(14, 7, 14, 7)
        title_bar_layout.setSpacing(10)
        
        # Title label
        title_label = QLabel("SHOP")
        title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 15px;
                font-weight: 900;
                background: transparent;
                border: none;
            }
        """)
        title_bar_layout.addWidget(title_label)
        
        title_bar_layout.addStretch()
        
        # Window control buttons
        min_btn = QPushButton("─")
        min_btn.setFixedSize(24, 24)
        min_btn.setText("-")
        min_btn.setFixedSize(28, 28)
        min_btn.setStyleSheet(_catalog_window_button_style())
        min_btn.clicked.connect(self.showMinimized)
        
        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setText("X")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(_catalog_window_button_style("close"))
        close_btn.clicked.connect(self.accept)
        
        title_bar_layout.addWidget(min_btn)
        title_bar_layout.addWidget(close_btn)
        
        self.layout.addWidget(title_bar)
        
        # Enable dragging from title bar
        title_bar.mousePressEvent = self.title_bar_mouse_press
        title_bar.mouseMoveEvent = self.title_bar_mouse_move
        
        # Center the dialog on screen
        self.center_on_screen()
        
        # Header with coins display
        header_frame = QFrame()
        header_frame.setObjectName("CatalogSummary")
        header_frame.setStyleSheet(_catalog_summary_style())
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)
        
        # User level display
        user_level = self.user_data.get('level', 0)
        title_label = QLabel(f"LEVEL {user_level}")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 900;
            color: #FFFFFF;
        """)
        
        # Coin display with icon
        self.coin_label = QLabel()
        self.coin_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 900;
            color: #FFD36E;
            padding: 7px 13px;
            background: rgba(0, 0, 0, 0.28);
            border: 1px solid rgba(255, 211, 110, 0.26);
            border-radius: 8px;
        """)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.coin_label)
        
        self.layout.addWidget(header_frame)
        self.update_coin_label()
        
        # Scroll area for rewards
        scroll = QScrollArea()
        self.shop_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_catalog_scroll_area_style())
        
        content = QWidget()
        content.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        self.rewards_layout = QVBoxLayout(content)
        self.rewards_layout.setSpacing(10)
        self.rewards_layout.setContentsMargins(0, 0, 0, 0)
        
        # Group rewards by type and sort by price ascending
        from collections import defaultdict
        rewards_by_type = defaultdict(list)
        for reward_id, reward in REWARDS.items():
            if is_reward_purchasable(reward):
                rewards_by_type[reward['type']].append((reward_id, reward))
        for reward_type, section_title in SHOP_SECTIONS:
            if reward_type in rewards_by_type:
                entries = sorted(rewards_by_type[reward_type], key=lambda x: x[1]['price'])
                self.add_shop_section(reward_type, section_title, entries)
        
        scroll.setWidget(content)
        self.layout.addWidget(scroll)

    def add_shop_section(self, reward_type, section_title, entries):
        """Add one collapsible Shop category section."""
        entries = _equipped_first(entries, self.user_data)
        section_frame = QFrame()
        section_frame.setObjectName("CatalogSection")
        section_frame.setStyleSheet(_catalog_section_style())
        section_layout = QVBoxLayout(section_frame)
        section_layout.setSpacing(8)
        section_layout.setContentsMargins(8, 8, 8, 8)

        header_frame, action_label = _create_catalog_category_header(
            reward_type,
            section_title,
            len(entries),
            False,
            self.toggle_category,
        )
        section_layout.addWidget(header_frame)

        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.setSpacing(8)
        items_layout.setContentsMargins(0, 0, 0, 0)
        for reward_id, reward in entries:
            items_layout.addLayout(self.reward_row(reward_id, reward))
        items_widget.setVisible(False)
        section_layout.addWidget(items_widget)

        self._category_sections[reward_type] = {
            "frame": section_frame,
            "header": header_frame,
            "action": action_label,
            "items": items_widget,
            "title": section_title,
        }
        self.rewards_layout.addWidget(section_frame)

    def toggle_category(self, reward_type):
        """Open one category at a time; clicking the open one closes it."""
        next_category = None if self._expanded_category == reward_type else reward_type
        self.apply_category_expansion(next_category)

    def apply_category_expansion(self, reward_type, scroll=True):
        """Apply the accordion state after a click or content refresh."""
        self._expanded_category = reward_type if reward_type in self._category_sections else None
        for key, section in self._category_sections.items():
            expanded = key == self._expanded_category
            section["items"].setVisible(expanded)
            section["header"].setStyleSheet(_catalog_category_header_style(key, expanded))
            section["action"].setText(_catalog_category_action_text(expanded))
        if scroll and self._expanded_category:
            self.scroll_to_category_first_item(self._expanded_category)

    def scroll_to_category_first_item(self, reward_type):
        """Move the opened Shop category so its first item is visible."""
        def do_scroll():
            section = self._category_sections.get(reward_type)
            scroll = getattr(self, "shop_scroll", None)
            if not section or not scroll or not section["items"].isVisible():
                return
            content = scroll.widget()
            if not content:
                return
            y = section["items"].mapTo(content, QPoint(0, 0)).y()
            scroll.verticalScrollBar().setValue(max(0, y - 8))

        QTimer.singleShot(40, do_scroll)

    def unequip_row(self, reward_type):
        # Create a frame for the unequip section
        unequip_frame = QFrame()
        unequip_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255,255,255,0.03), stop:1 rgba(255,255,255,0.01));
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                padding: 6px;
                margin: 2px;
            }
        """)
        
        row = QHBoxLayout(unequip_frame)
        row.setSpacing(10)
        row.setContentsMargins(8, 6, 8, 6)
        
        # Check if anything is equipped for this type
        currently_equipped = self.user_data['equipped'].get(reward_type)
        
        if currently_equipped:
            # Something is equipped - show what it is and enable unequip
            equipped_reward = REWARDS[currently_equipped]
            
            # Create info layout
            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            
            status_label = QLabel("🔧 CURRENTLY EQUIPPED")
            status_label.setStyleSheet("""
                color: #4CAF50;
                font-weight: bold;
                font-size: 11px;
                background: rgba(76, 175, 80, 0.2);
                padding: 3px 6px;
                border-radius: 3px;
                border: 1px solid #4CAF50;
            """)
            
            name_label = QLabel(f"📦 {equipped_reward['name']}")
            name_label.setStyleSheet("""
                color: #4CAF50;
                font-weight: bold;
                font-size: 13px;
            """)
            
            #info_layout.addWidget(status_label)
            info_layout.addWidget(name_label)
            
            btn = QPushButton("🗑️ UNEQUIP")
            btn.setEnabled(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #F44336, stop:1 #EF5350);
                    color: white;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 11px;
                    min-width: 70px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #D32F2F, stop:1 #E53935);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #C62828, stop:1 #D32F2F);
                }
            """)
            btn.clicked.connect(lambda _, t=reward_type: self.unequip_reward(t))
        else:
            # Nothing equipped - show default state
            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            
            status_label = QLabel("⚙️ DEFAULT SETTING")
            status_label.setStyleSheet("""
                color: #9E9E9E;
                font-weight: bold;
                font-size: 11px;
                background: rgba(158, 158, 158, 0.2);
                padding: 3px 6px;
                border-radius: 3px;
                border: 1px solid #9E9E9E;
            """)
            
            name_label = QLabel("🎯 No custom item equipped")
            name_label.setStyleSheet("""
                color: #9E9E9E;
                font-style: italic;
                font-size: 13px;
            """)
            
            #info_layout.addWidget(status_label)
            info_layout.addWidget(name_label)
            
            btn = QPushButton("🗑️ UNEQUIP")
            btn.setEnabled(False)
            btn.setStyleSheet("""
                QPushButton {
                    background: #9E9E9E;
                    color: #BDBDBD;
                    border: none;
                    padding: 6px 12px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 11px;
                    min-width: 70px;
                }
            """)
        
        row.addLayout(info_layout)
        row.addStretch()
        row.addWidget(btn)
        
        # Create a container layout to hold the frame
        container_layout = QVBoxLayout()
        container_layout.addWidget(unequip_frame)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        return container_layout

    def unequip_reward(self, reward_type):
        self.user_data['equipped'][reward_type] = None
        save_user_rewards(self.user_data)
        if self.parent() and hasattr(self.parent(), 'apply_equipped_rewards'):
            self.parent().apply_equipped_rewards()
        # Show success message
        box = self.create_styled_message_box("Unequipped", f"Unequipped {get_reward_type_label(reward_type).lower()}!")
        box.exec_()
        # Close and reopen the dialog to force a complete refresh
        if self.parent():
            self.accept()  # Close current dialog
            QTimer.singleShot(100, lambda: self.parent().open_shop_dialog())  # Reopen


    def update_coin_label(self):
        self.coin_label.setText(f"COINS {self.user_data.get('coins', 0)}  |  XP {self.user_data.get('xp', 0)}")
    def reward_row(self, reward_id, reward):
        """Create a consistent shop row for any reward catalog item."""
        container_layout = QVBoxLayout()

        reward_frame = QFrame()
        reward_frame.setObjectName("CatalogItem")
        reward_frame.setStyleSheet(_catalog_item_style())
        reward_frame.installEventFilter(self)
        reward_frame._reward_id = reward_id
        reward_frame._reward = reward

        row = QHBoxLayout(reward_frame)
        row.setSpacing(12)
        row.setContentsMargins(10, 8, 10, 8)

        reward_type = reward.get('type', 'item')
        reward_type_label = get_reward_type_label(reward_type)
        display_name = get_reward_display_name(reward_id, reward)
        price = int(reward.get('price', 0) or 0)
        required_xp = int(reward.get('required_xp', 0) or 0)
        user_xp = int(self.user_data.get('xp', 0) or 0)
        meets_xp = user_xp >= required_xp
        unlocked = reward_id in self.user_data.get('unlocked', [])

        image_path = _resolve_reward_image_path(reward_id, reward)
        icon_w, icon_h = _catalog_icon_size(reward_type)
        slot_frame = QFrame()
        slot_frame.setObjectName("CatalogIconSlot")
        slot_frame.setFixedSize(icon_w + 14, icon_h + 14)
        slot_frame.setStyleSheet(_catalog_icon_slot_style())
        slot_layout = QVBoxLayout(slot_frame)
        slot_layout.setContentsMargins(7, 7, 7, 7)
        slot_layout.setSpacing(0)

        if reward_type == "font":
            preview_text = display_name
            preview_family = _reward_font_family(reward, self.catalog_font_family)
            font_label = QLabel(preview_text)
            font_label.setFont(QFont(preview_family, 13, QFont.Bold))
            font_label.setFixedSize(icon_w, icon_h)
            font_label.setAlignment(Qt.AlignCenter)
            font_label.setWordWrap(True)
            font_label.setStyleSheet(_catalog_font_preview_style(preview_family))
            font_label._reward_id = reward_id
            font_label._reward = reward
            font_label.installEventFilter(self)
            slot_layout.addWidget(font_label, alignment=Qt.AlignCenter)
        elif image_path:
            img_label = QLabel()
            pix = QPixmap(image_path)
            img_label.setPixmap(pix.scaled(icon_w, icon_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            img_label.setFixedSize(icon_w, icon_h)
            img_label.setAlignment(Qt.AlignCenter)
            img_label._reward_id = reward_id
            img_label._reward = reward
            img_label.installEventFilter(self)
            slot_layout.addWidget(img_label, alignment=Qt.AlignCenter)
        else:
            icon_text = get_reward_icon(reward_id, reward) or "#"
            icon_label = QLabel(icon_text)
            icon_label.setFont(QFont('Segoe UI Emoji', 28, QFont.Bold))
            icon_label.setFixedSize(icon_w, icon_h)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet("""
                QLabel {
                    color: #FFD36E;
                    background: transparent;
                    border: none;
                }
            """)
            icon_label._reward_id = reward_id
            icon_label._reward = reward
            icon_label.installEventFilter(self)
            slot_layout.addWidget(icon_label, alignment=Qt.AlignCenter)
        row.addWidget(slot_frame)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(display_name)
        if reward_type == "font":
            preview_family = _reward_font_family(reward, self.catalog_font_family)
            name_label.setFont(QFont(preview_family, 13, QFont.Bold))
            name_label.setStyleSheet(f"""
                color: #FFFFFF;
                font-family: {_font_family_qss(preview_family)};
                font-weight: 900;
                font-size: 14px;
            """)
        else:
            name_label.setStyleSheet("""
                color: #FFFFFF;
                font-weight: 900;
                font-size: 15px;
            """)
        name_label._reward_id = reward_id
        name_label._reward = reward
        name_label.installEventFilter(self)

        is_equipped = _is_equipped_reward(self.user_data, reward_id, reward)
        if is_equipped:
            detail_text = f"{reward_type_label.upper()}  |  EQUIPPED"
        elif unlocked:
            detail_text = f"{reward_type_label.upper()}  |  OWNED"
        elif required_xp and not unlocked:
            detail_text = (
                f"{reward_type_label.upper()}  |  {required_xp:,} XP UNLOCKED"
                if meets_xp
                else f"{reward_type_label.upper()}  |  UNLOCKS AT {required_xp:,} XP"
            )
        elif price == 0:
            detail_text = f"{reward_type_label.upper()}  |  FREE CLAIM"
        else:
            detail_text = f"{reward_type_label.upper()}  |  {price} COINS"
        detail_label = QLabel(detail_text)
        detail_label.setStyleSheet("""
            color: #FFD36E;
            font-size: 12px;
            font-weight: 900;
        """)

        desc_label = QLabel(reward.get('description', ''))
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            color: rgba(247, 251, 255, 0.72);
            font-size: 11px;
        """)
        desc_label._reward_id = reward_id
        desc_label._reward = reward
        desc_label.installEventFilter(self)

        info_layout.addWidget(name_label)
        info_layout.addWidget(detail_label)
        info_layout.addWidget(desc_label)
        row.addLayout(info_layout, 1)

        if unlocked:
            btn = QPushButton("EQUIPPED" if is_equipped else "OWNED")
            btn.setEnabled(True)
            btn.setToolTip("Open this item in Inventory.")
            btn.setStyleSheet(_catalog_button_style("owned"))
            btn.clicked.connect(lambda _, rid=reward_id: self.open_inventory_item(rid))
        else:
            can_afford = self.user_data.get('coins', 0) >= price
            can_claim = can_afford and meets_xp
            btn = QPushButton("LOCKED" if not meets_xp else ("CLAIM" if price == 0 else "BUY"))
            btn.setEnabled(can_claim)
            if can_claim:
                btn.setStyleSheet(_catalog_button_style("buy"))
            else:
                btn.setStyleSheet(_catalog_button_style("disabled"))
                if not meets_xp:
                    btn.setToolTip(f"Reach {required_xp:,} XP to claim this free reward.")
                else:
                    btn.setToolTip(f"Need {price - self.user_data.get('coins', 0)} more coins.")
            btn.clicked.connect(lambda _, rid=reward_id: self.claim_reward(rid))

        row.addWidget(btn)
        container_layout.addWidget(reward_frame)
        container_layout.setContentsMargins(0, 0, 0, 0)
        return container_layout

    def mousePressEvent(self, event):
        """Enable dragging the window by clicking and dragging the title bar area"""
        if event.button() == Qt.LeftButton:
            # Only allow dragging from the title bar area (top 40 pixels)
            if event.y() <= 40:
                self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        """Handle window dragging"""
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag_position'):
            self.move(event.globalPos() - self._drag_position)
            event.accept()

    def center_on_screen(self):
        """Center the dialog on the screen"""
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def title_bar_mouse_press(self, event):
        """Handle mouse press on title bar for dragging"""
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def title_bar_mouse_move(self, event):
        """Handle mouse move on title bar for dragging"""
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag_position'):
            self.move(event.globalPos() - self._drag_position)
            event.accept()

    def eventFilter(self, obj, event):
        """Handle hover events for item previews"""
        if hasattr(obj, '_reward_id') and hasattr(obj, '_reward'):
            reward_id = obj._reward_id
            reward = obj._reward
            
            if event.type() == QEvent.HoverEnter:
                # Create tooltip with item details
                if self._shop_tooltip:
                    self._shop_tooltip.hide()
                    self._shop_tooltip.deleteLater()
                
                name = get_reward_display_name(reward_id, reward)
                description = reward.get('description', '')
                price = reward.get('price', 0)
                preview = _resolve_reward_image_path(reward_id, reward)
                is_font_reward = reward.get("type") == "font"
                font_preview_text = name if is_font_reward else None
                font_family = _reward_font_family(reward, self.catalog_font_family) if is_font_reward else None
                emoji = None if (preview or is_font_reward) else (get_reward_icon(reward_id, reward) or "#")
                
                # Create tooltip
                self._shop_tooltip = CustomTooltipWidget(
                    parent=self,
                    preview=preview,
                    emoji=emoji,
                    font_preview_text=font_preview_text,
                    font_family=font_family,
                    reward_id=reward_id,
                    reward_type=reward.get("type"),
                    name=name,
                    description=description,
                    price=price
                )
                
                # Position tooltip in top-right area of window
                window_rect = self.geometry()
                tooltip_width = 300  # Approximate tooltip width
                tooltip_height = 250  # Approximate tooltip height
                
                # Position tooltip just outside the top-right corner of the window
                x = window_rect.x() + window_rect.width() + 10
                y = window_rect.y() + 20  # Small offset from top
                
                # Ensure tooltip doesn't go off-screen
                screen = QApplication.primaryScreen().geometry()
                if x + tooltip_width > screen.width():
                    x = window_rect.x() - tooltip_width - 10  # Show on left side instead
                
                self._shop_tooltip.move(x, y)
                self._shop_tooltip.show()
                
            elif event.type() == QEvent.Leave:
                # Hide tooltip when mouse leaves
                if self._shop_tooltip:
                    self._shop_tooltip.hide()
                    self._shop_tooltip.deleteLater()
                    self._shop_tooltip = None
        
        return super().eventFilter(obj, event)

    def open_inventory_item(self, reward_id):
        """Open Inventory focused on an owned shop item."""
        parent = self.parent()
        self.close()
        if parent and hasattr(parent, 'open_inventory_dialog'):
            QTimer.singleShot(80, lambda rid=reward_id: parent.open_inventory_dialog(rid))
            return

        dialog = InventoryDialog(None, focus_reward_id=reward_id)
        dialog.setModal(False)
        dialog.show()
    
    def claim_reward(self, reward_id):
        """Claim a reward from the shop"""
        try:
            from utils.rewards import load_user_rewards, save_user_rewards, REWARDS
            
            # Load current user data
            user_data = load_user_rewards()
            
            # Check if user has enough coins
            user_coins = user_data.get('coins', 0)
            reward = REWARDS.get(reward_id)
            
            if not reward:
                logging.error(f"Reward {reward_id} not found")
                return

            if not is_reward_purchasable(reward):
                logging.warning(f"Reward {reward_id} is not purchasable from the shop")
                return
            
            reward_price = reward.get('price', 0)
            required_xp = int(reward.get('required_xp', 0) or 0)
            user_xp = int(user_data.get('xp', 0) or 0)

            if required_xp and user_xp < required_xp:
                logging.warning(f"Reward {reward_id} requires {required_xp} XP; user has {user_xp}")
                box = self.create_styled_message_box(
                    "Locked",
                    f"Reach {required_xp:,} XP to claim {reward.get('name', 'this reward')}."
                )
                box.exec_()
                return
            
            if user_coins < reward_price:
                logging.warning(f"Not enough coins. Need {reward_price}, have {user_coins}")
                return
            
            # Deduct coins and unlock reward
            user_data['coins'] = user_coins - reward_price
            
            # Add to unlocked list if not already there
            if 'unlocked' not in user_data:
                user_data['unlocked'] = []
            if reward_id not in user_data['unlocked']:
                user_data['unlocked'].append(reward_id)
            
            # Save updated user data
            save_user_rewards(user_data)
            
            # Update local user_data
            self.user_data = user_data
            
            # Refresh the shop display
            self.refresh_shop()
            
            logging.info(f"Successfully claimed reward {reward_id} for {reward_price} coins")
            
        except Exception as e:
            logging.error(f"Error claiming reward {reward_id}: {e}")
    
    def create_styled_message_box(self, title, message, icon=None):
        """Create a properly styled message box with modern theme"""
        return ModernMessageBox(title, message, "info", self)

    def refresh_shop(self):
        """Refresh the shop display after changes"""
        expanded_category = self._expanded_category
        self.catalog_font_family = _catalog_font_family(self.parent())
        self.setFont(QFont(self.catalog_font_family, 10))
        self.setStyleSheet(_catalog_dialog_style(self.catalog_font_family))
        # Clear existing layout items (excluding title bar)
        while self.layout.count() > 1:
            child = self.layout.takeAt(1)
            if child.widget():
                child.widget().deleteLater()
        
        # Rebuild shop content
        self.build_shop_content(expanded_category=expanded_category)
    
    def build_shop_content(self, expanded_category=None):
        """Build the shop content"""
        self._category_sections = {}
        self._expanded_category = None
        # Clear existing content (excluding title bar)
        while self.layout.count() > 1:
            child = self.layout.takeAt(1)
            if child.widget():
                child.widget().deleteLater()
        
        # Rebuild the shop content
        from PyQt5.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QFrame, QLabel
        from PyQt5.QtCore import Qt
        from collections import defaultdict
        from utils.rewards import REWARDS
        
        # Header frame with coins
        header_frame = QFrame()
        header_frame.setObjectName("CatalogSummary")
        header_frame.setStyleSheet(_catalog_summary_style())
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)
        
        # Coin display
        self.coin_label = QLabel(f"COINS {self.user_data.get('coins', 0)}  |  XP {self.user_data.get('xp', 0)}")
        self.coin_label.setStyleSheet("""
            color: #FFD36E;
            font-size: 14px;
            font-weight: 900;
        """)
        header_layout.addWidget(self.coin_label)
        
        self.layout.addWidget(header_frame)
        
        # Scroll area for rewards
        scroll = QScrollArea()
        self.shop_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_catalog_scroll_area_style())
        
        content = QWidget()
        content.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        self.rewards_layout = QVBoxLayout(content)
        self.rewards_layout.setSpacing(10)
        self.rewards_layout.setContentsMargins(0, 0, 0, 0)
        
        # Group rewards by type and sort by price ascending
        rewards_by_type = defaultdict(list)
        for reward_id, reward in REWARDS.items():
            if is_reward_purchasable(reward):
                rewards_by_type[reward['type']].append((reward_id, reward))
        
        for reward_type, section_title in SHOP_SECTIONS:
            if reward_type in rewards_by_type:
                entries = sorted(rewards_by_type[reward_type], key=lambda x: x[1]['price'])
                self.add_shop_section(reward_type, section_title, entries)
        
        scroll.setWidget(content)
        self.layout.addWidget(scroll)
        if expanded_category:
            self.apply_category_expansion(expanded_category)



class InventoryDialog(QDialog):
    def __init__(self, parent=None, focus_reward_id=None):
        super().__init__(parent)
        self._inventory_tooltip = None
        self.focus_reward_id = focus_reward_id
        self._inventory_rows = {}
        self._category_sections = {}
        self._expanded_category = None
        self.catalog_font_family = _catalog_font_family(parent)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.finished.connect(self.deleteLater)
        
        # Set up frameless window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setWindowTitle("Inventory")
        self.setMinimumWidth(560)
        self.setMinimumHeight(660)
        self.setStyleSheet(_catalog_dialog_style(self.catalog_font_family))
        self.setFont(QFont(self.catalog_font_family, 10))
        
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Custom title bar
        self.title_bar = QFrame()
        self.title_bar.setObjectName("CatalogTitleBar")
        self.title_bar.setFixedHeight(44)
        self.title_bar.setStyleSheet(_catalog_title_bar_style())
        
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(14, 7, 14, 7)
        title_bar_layout.setSpacing(10)
        
        # Title
        title_label = QLabel("INVENTORY")
        title_label.setStyleSheet("""
            font-size: 15px;
            font-weight: 900;
            color: white;
            background: transparent;
            border: none;
        """)
        
        # Window control buttons
        min_button = QPushButton("─")
        min_button.setFixedSize(30, 30)
        min_button.setText("-")
        min_button.setFixedSize(28, 28)
        min_button.setStyleSheet(_catalog_window_button_style())
        min_button.clicked.connect(self.showMinimized)
        
        close_button = QPushButton("×")
        close_button.setFixedSize(30, 30)
        close_button.setText("X")
        close_button.setFixedSize(28, 28)
        close_button.setStyleSheet(_catalog_window_button_style("close"))
        close_button.clicked.connect(self.close)
        
        # Add widgets to title bar
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(min_button)
        title_bar_layout.addWidget(close_button)
        
        # Add title bar to main layout
        self.layout.addWidget(self.title_bar)
        
        # Content area
        content_widget = QWidget()
        content_widget.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(14, 14, 14, 14)
        
        # Load user data first
        self.user_data = load_user_rewards()
        
        # Header with owned items count
        header_frame = QFrame()
        header_frame.setObjectName("CatalogSummary")
        header_frame.setStyleSheet(_catalog_summary_style())
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(10)
        
        # Calculate total owned items
        total_owned = len(self.user_data.get('unlocked', []))
        
        # Owned items count
        owned_label = QLabel(f"🏆 OWNED: {total_owned}")
        owned_label.setText(f"OWNED ITEMS: {total_owned}")
        owned_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 900;
            color: white;
        """)
        owned_label.setAlignment(Qt.AlignCenter)
        
        header_layout.addStretch()
        header_layout.addWidget(owned_label)
        header_layout.addStretch()
        
        content_layout.addWidget(header_frame)
        
        # Scroll area for owned items
        scroll = QScrollArea()
        self.inventory_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_catalog_scroll_area_style())
        
        content = QWidget()
        content.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        self.inventory_layout = QVBoxLayout(content)
        self.inventory_layout.setSpacing(10)
        self.inventory_layout.setContentsMargins(0, 0, 0, 0)
        
        owned_rewards_by_type = self.build_owned_rewards_by_type()
        
        for reward_type, section_title in INVENTORY_SECTIONS:
            if reward_type in owned_rewards_by_type:
                self.add_inventory_section(reward_type, section_title, owned_rewards_by_type[reward_type])
        
        # Show message if no items owned
        if not self._category_sections:
            no_items_label = QLabel("No items in inventory yet.\nVisit the Shop to purchase items!")
            no_items_label.setStyleSheet("""
                font-size: 16px;
                color: #888888;
                text-align: center;
                padding: 40px;
            """)
            no_items_label.setAlignment(Qt.AlignCenter)
            self.inventory_layout.addWidget(no_items_label)
        
        scroll.setWidget(content)
        content_layout.addWidget(scroll)
        
        # Add content widget to main layout
        self.layout.addWidget(content_widget)
        
        # Center dialog on screen
        self.center_on_screen()

        if self.focus_reward_id:
            QTimer.singleShot(160, self.focus_inventory_reward)
        
        # Enable dragging
        self._drag_position = None
        self.title_bar.mousePressEvent = self.title_bar_mouse_press
        self.title_bar.mouseMoveEvent = self.title_bar_mouse_move

    def build_owned_rewards_by_type(self):
        """Group owned rewards for Inventory while keeping custom wallpaper separate."""
        owned_rewards_by_type = defaultdict(list)
        for reward_id in self.user_data.get('unlocked', []):
            if reward_id == CUSTOM_WALLPAPER_ID:
                continue
            if reward_id in REWARDS:
                reward = REWARDS[reward_id]
                owned_rewards_by_type[reward['type']].append((reward_id, reward))
        owned_rewards_by_type.setdefault("header", [])
        owned_rewards_by_type.setdefault("badge", [])
        return owned_rewards_by_type

    def add_inventory_section(self, reward_type, section_title, entries):
        """Add one collapsible Inventory category section."""
        entries = _equipped_first(entries, self.user_data)
        custom_wallpaper_imported = custom_wallpaper_exists(self.user_data)
        custom_wallpaper_equipped = (
            reward_type == "header"
            and self.user_data.get('equipped', {}).get("header") == CUSTOM_WALLPAPER_ID
        )
        item_count = len(entries)
        if reward_type == "header" and custom_wallpaper_imported:
            item_count += 1
        section_frame = QFrame()
        section_frame.setObjectName("CatalogSection")
        section_frame.setStyleSheet(_catalog_section_style())
        section_layout = QVBoxLayout(section_frame)
        section_layout.setSpacing(8)
        section_layout.setContentsMargins(8, 8, 8, 8)

        header_frame, action_label = _create_catalog_category_header(
            reward_type,
            section_title,
            item_count,
            True,
            self.toggle_category,
        )
        section_layout.addWidget(header_frame)

        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.setSpacing(8)
        items_layout.setContentsMargins(0, 0, 0, 0)
        if reward_type == "header" and custom_wallpaper_equipped:
            items_layout.addLayout(self.custom_wallpaper_row())
        if reward_type == "badge":
            items_layout.addLayout(self.visual_setting_row(
                "focus_mode",
                "Focus Mode",
                "Hide the center badge or Silcrow in full view so the wallpaper can take the stage.",
            ))
            items_layout.addLayout(self.visual_setting_row(
                "quiet_run_mode",
                "Quiet Run Mode",
                "Hide the decorative run message and cat animation while automation is active.",
            ))
        for reward_id, reward in entries:
            items_layout.addLayout(self.inventory_item_row(reward_id, reward))
        if reward_type == "header" and not custom_wallpaper_equipped:
            items_layout.addLayout(self.custom_wallpaper_row())
        items_layout.addLayout(self.unequip_row(reward_type))
        items_widget.setVisible(False)
        section_layout.addWidget(items_widget)

        self._category_sections[reward_type] = {
            "frame": section_frame,
            "header": header_frame,
            "action": action_label,
            "items": items_widget,
            "title": section_title,
        }
        self.inventory_layout.addWidget(section_frame)

    def toggle_category(self, reward_type):
        """Open one category at a time; clicking the open one closes it."""
        next_category = None if self._expanded_category == reward_type else reward_type
        self.apply_category_expansion(next_category)

    def apply_category_expansion(self, reward_type, scroll=True):
        """Apply the accordion state after a click or content refresh."""
        self._expanded_category = reward_type if reward_type in self._category_sections else None
        for key, section in self._category_sections.items():
            expanded = key == self._expanded_category
            section["items"].setVisible(expanded)
            section["header"].setStyleSheet(_catalog_category_header_style(key, expanded))
            section["action"].setText(_catalog_category_action_text(expanded))
        if scroll and self._expanded_category:
            self.scroll_to_category_first_item(self._expanded_category)

    def scroll_to_category_first_item(self, reward_type):
        """Move the opened Inventory category so its first item is visible."""
        def do_scroll():
            section = self._category_sections.get(reward_type)
            scroll = getattr(self, "inventory_scroll", None)
            if not section or not scroll or not section["items"].isVisible():
                return
            content = scroll.widget()
            if not content:
                return
            y = section["items"].mapTo(content, QPoint(0, 0)).y()
            scroll.verticalScrollBar().setValue(max(0, y - 8))

        QTimer.singleShot(40, do_scroll)

    def visual_setting_row(self, setting_key, title, description):
        """Create a non-item toggle row for badge/display behavior."""
        settings = get_visual_settings(self.user_data)
        enabled = bool(settings.get(setting_key))

        row_layout = QHBoxLayout()
        frame = QFrame()
        frame.setObjectName("CatalogSettingRow")
        frame.setStyleSheet(_catalog_setting_row_style())
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        name_label = QLabel(title)
        name_label.setStyleSheet("""
            font-weight: 900;
            font-size: 14px;
            color: #D9B8FF;
        """)
        desc_label = QLabel(description)
        desc_label.setStyleSheet("font-size: 12px; color: rgba(247, 251, 255, 0.72);")
        desc_label.setWordWrap(True)
        text_layout.addWidget(name_label)
        text_layout.addWidget(desc_label)
        frame_layout.addLayout(text_layout, 1)

        toggle_button = QPushButton("ON" if enabled else "OFF")
        toggle_button.setCheckable(True)
        toggle_button.setChecked(enabled)
        toggle_button.setStyleSheet(_catalog_toggle_button_style(enabled))
        toggle_button.clicked.connect(lambda checked, key=setting_key: self.toggle_visual_setting(key, checked))
        frame_layout.addWidget(toggle_button)

        row_layout.addWidget(frame)
        container_layout = QVBoxLayout()
        container_layout.addLayout(row_layout)
        container_layout.setContentsMargins(0, 0, 0, 0)
        return container_layout

    def toggle_visual_setting(self, setting_key, enabled):
        """Persist a visual toggle and let the main window react immediately."""
        self.user_data = set_visual_setting(self.user_data, setting_key, enabled)
        logging.info("Inventory visual toggle changed: %s=%s", setting_key, enabled)
        parent = self.parent()
        if parent and hasattr(parent, 'apply_visual_settings_to_current_state'):
            parent.apply_visual_settings_to_current_state()
        elif parent and hasattr(parent, 'apply_equipped_rewards'):
            parent.apply_equipped_rewards()
        self._expanded_category = "badge"
        self.refresh()

    def custom_wallpaper_row(self):
        """Create the Inventory row for importing and equipping a custom wallpaper."""
        reward = REWARDS.get(CUSTOM_WALLPAPER_ID, {})
        imported_path = get_custom_wallpaper_path(self.user_data)
        has_import = imported_path is not None
        is_equipped = self.user_data.get('equipped', {}).get("header") == CUSTOM_WALLPAPER_ID

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        info_frame = QFrame()
        info_frame.setObjectName("CatalogItem")
        info_frame.setStyleSheet(_catalog_item_style(CUSTOM_WALLPAPER_ID == self.focus_reward_id))
        self._inventory_rows[CUSTOM_WALLPAPER_ID] = info_frame
        info_layout = QHBoxLayout(info_frame)
        info_layout.setSpacing(12)

        icon_w, icon_h = _catalog_icon_size("header", inventory=True)
        slot_frame = QFrame()
        slot_frame.setObjectName("CatalogIconSlot")
        slot_frame.setFixedSize(icon_w + 14, icon_h + 14)
        slot_frame.setStyleSheet(_catalog_icon_slot_style())
        slot_layout = QVBoxLayout(slot_frame)
        slot_layout.setContentsMargins(7, 7, 7, 7)
        slot_layout.setSpacing(0)

        icon_label = QLabel()
        icon_label.setFixedSize(icon_w, icon_h)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label._reward_id = CUSTOM_WALLPAPER_ID
        icon_label._reward = reward
        if has_import:
            pix = QPixmap(str(imported_path))
            icon_label.setPixmap(pix.scaled(icon_w, icon_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            icon_label._preview_path = str(imported_path)
            icon_label.installEventFilter(self)
        else:
            icon_label.setText("CUSTOM")
            icon_label.setFont(QFont(self.catalog_font_family, 10, QFont.Bold))
            icon_label.setStyleSheet("""
                QLabel {
                    color: #FFD36E;
                    background: rgba(255, 211, 110, 0.08);
                    border: 1px solid rgba(255, 211, 110, 0.25);
                    border-radius: 7px;
                }
            """)
        slot_layout.addWidget(icon_label, alignment=Qt.AlignCenter)
        info_layout.addWidget(slot_frame)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        name_label = QLabel(get_reward_display_name(CUSTOM_WALLPAPER_ID, reward))
        name_label.setStyleSheet("""
            font-weight: 900;
            font-size: 14px;
            color: #FFD36E;
        """)
        desc_text = (
            "Your imported wallpaper is saved on this device."
            if has_import
            else "Import a personal image, crop it, and use it as your wallpaper."
        )
        desc_label = QLabel(desc_text)
        desc_label.setStyleSheet("font-size: 12px; color: rgba(247, 251, 255, 0.72);")
        desc_label.setWordWrap(True)
        if has_import:
            name_label._preview_path = str(imported_path)
            desc_label._preview_path = str(imported_path)
            name_label._reward_id = CUSTOM_WALLPAPER_ID
            desc_label._reward_id = CUSTOM_WALLPAPER_ID
            name_label._reward = reward
            desc_label._reward = reward
            name_label.installEventFilter(self)
            desc_label.installEventFilter(self)
        text_layout.addWidget(name_label)
        text_layout.addWidget(desc_label)
        info_layout.addLayout(text_layout, 1)

        row_layout.addWidget(info_frame, 1)

        buttons_frame = QFrame()
        buttons_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(5)

        import_button = QPushButton("CHANGE" if has_import else "IMPORT")
        import_button.setStyleSheet(_catalog_button_style("buy"))
        import_button.clicked.connect(self.import_custom_wallpaper)
        buttons_layout.addWidget(import_button)

        if has_import:
            if is_equipped:
                equip_button = QPushButton("UNEQUIP")
                equip_button.setStyleSheet(_catalog_button_style("unequip"))
                equip_button.clicked.connect(lambda: self.unequip_reward("header"))
            else:
                equip_button = QPushButton("EQUIP")
                equip_button.setStyleSheet(_catalog_button_style("equip"))
                equip_button.clicked.connect(self.equip_custom_wallpaper)
            buttons_layout.addWidget(equip_button)

        row_layout.addWidget(buttons_frame)

        container_layout = QVBoxLayout()
        container_layout.addLayout(row_layout)
        container_layout.setContentsMargins(0, 0, 0, 0)
        return container_layout

    def import_custom_wallpaper(self):
        """Open a file picker, crop the selected image, save it, and equip it."""
        logging.info("Custom wallpaper import requested from Inventory.")
        start_dir = Path.home() / "Pictures"
        if not start_dir.exists():
            start_dir = Path.home()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Wallpaper",
            str(start_dir),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not file_path:
            logging.info("Custom wallpaper import canceled before image selection.")
            return
        logging.info("Custom wallpaper image selected: %s", file_path)

        dialog = CustomWallpaperDialog(file_path, self)
        if dialog.exec_() != QDialog.Accepted or not dialog.result_data:
            logging.info("Custom wallpaper import canceled during crop preview.")
            return

        self.user_data = set_custom_wallpaper_data(
            self.user_data,
            dialog.result_data["source_path"],
            dialog.result_data["processed_path"],
            dialog.result_data.get("zoom", 1.0),
            dialog.result_data.get("offset_x", 0),
            dialog.result_data.get("offset_y", 0),
        )
        logging.info(
            "Custom wallpaper import completed. equipped_header=%s processed=%s",
            self.user_data.get('equipped', {}).get("header"),
            dialog.result_data["processed_path"],
        )
        if self.parent() and hasattr(self.parent(), 'apply_equipped_rewards'):
            logging.info("Refreshing main UI after custom wallpaper import.")
            self.parent().apply_equipped_rewards()

        box = self.create_styled_message_box("Wallpaper Equipped", "Custom wallpaper equipped and saved.")
        box.exec_()
        self._expanded_category = "header"
        self.refresh()

    def equip_custom_wallpaper(self):
        """Equip the saved custom wallpaper if it is still available."""
        logging.info("Custom wallpaper equip requested from Inventory.")
        if not custom_wallpaper_exists(self.user_data):
            logging.warning("Custom wallpaper equip failed because the processed image is missing.")
            box = self.create_styled_message_box(
                "Wallpaper Missing",
                "The saved custom wallpaper file could not be found. Import it again to use it.",
                QMessageBox.Warning,
            )
            box.exec_()
            self.refresh()
            return
        self.user_data.setdefault('equipped', {})["header"] = CUSTOM_WALLPAPER_ID
        self.user_data = save_user_rewards(self.user_data)
        logging.info(
            "Custom wallpaper equip saved. equipped_header=%s processed_exists=%s",
            self.user_data.get('equipped', {}).get("header"),
            custom_wallpaper_exists(self.user_data),
        )
        if self.parent() and hasattr(self.parent(), 'apply_equipped_rewards'):
            logging.info("Refreshing main UI after custom wallpaper equip.")
            self.parent().apply_equipped_rewards()
        box = self.create_styled_message_box("Equipped", "Equipped Custom Wallpaper!")
        box.exec_()
        self._expanded_category = "header"
        self.refresh()

    def inventory_item_row(self, reward_id, reward):
        """Create a row for an owned inventory item"""
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        
        # Item info frame
        info_frame = QFrame()
        info_frame.setObjectName("CatalogItem")
        is_focus_item = reward_id == getattr(self, 'focus_reward_id', None)
        info_frame.setStyleSheet(_catalog_item_style(is_focus_item))
        self._inventory_rows[reward_id] = info_frame
        info_layout = QHBoxLayout(info_frame)
        info_layout.setSpacing(12)

        display_name = get_reward_display_name(reward_id, reward)
        icon_path = _resolve_reward_image_path(reward_id, reward)
        icon_w, icon_h = _catalog_icon_size(reward.get('type'), inventory=True)
        slot_frame = QFrame()
        slot_frame.setObjectName("CatalogIconSlot")
        slot_frame.setFixedSize(icon_w + 14, icon_h + 14)
        slot_frame.setStyleSheet(_catalog_icon_slot_style())
        slot_layout = QVBoxLayout(slot_frame)
        slot_layout.setContentsMargins(7, 7, 7, 7)
        slot_layout.setSpacing(0)

        if reward.get('type') == "font":
            preview_text = display_name
            preview_family = _reward_font_family(reward, self.catalog_font_family)
            icon_label = QLabel(preview_text)
            icon_label.setFont(QFont(preview_family, 12, QFont.Bold))
            icon_label.setFixedSize(icon_w, icon_h)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setWordWrap(True)
            icon_label.setStyleSheet(_catalog_font_preview_style(preview_family, inventory=True))
        elif icon_path:
            icon_label = QLabel()
            pix = QPixmap(icon_path)
            icon_label.setPixmap(pix.scaled(icon_w, icon_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_label.setFixedSize(icon_w, icon_h)
            icon_label.setAlignment(Qt.AlignCenter)
        else:
            icon_label = QLabel(get_reward_icon(reward_id, reward) or "#")
            icon_label.setFont(QFont('Segoe UI Emoji', 24, QFont.Bold))
            icon_label.setFixedSize(icon_w, icon_h)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet("""
                QLabel {
                    color: #FFD36E;
                    background: transparent;
                    border: none;
                }
            """)
        icon_label._preview_path = icon_path
        icon_label._reward_id = reward_id
        icon_label._reward = reward
        icon_label.installEventFilter(self)
        slot_layout.addWidget(icon_label, alignment=Qt.AlignCenter)
        info_layout.addWidget(slot_frame)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        name_label = QLabel(display_name)
        if reward.get('type') == "font":
            preview_family = _reward_font_family(reward, self.catalog_font_family)
            name_label.setFont(QFont(preview_family, 12, QFont.Bold))
            name_label.setStyleSheet(f"""
                font-family: {_font_family_qss(preview_family)};
                font-weight: 900;
                font-size: 13px;
                color: #FFD36E;
            """)
        else:
            name_label.setStyleSheet("""
                font-weight: 900;
                font-size: 14px;
                color: #FFD36E;
            """)

        desc_label = QLabel(reward.get('description', ''))
        desc_label.setStyleSheet("font-size: 12px; color: rgba(247, 251, 255, 0.72);")
        desc_label.setWordWrap(True)

        name_label._preview_path = icon_path
        desc_label._preview_path = icon_path
        name_label._reward_id = reward_id
        name_label._reward = reward
        desc_label._reward_id = reward_id
        desc_label._reward = reward
        name_label.installEventFilter(self)
        desc_label.installEventFilter(self)

        text_layout.addWidget(name_label)
        text_layout.addWidget(desc_label)
        info_layout.addLayout(text_layout, 1)

        row_layout.addWidget(info_frame, 1)

        # Action buttons frame
        buttons_frame = QFrame()
        buttons_frame.setStyleSheet("""
            QFrame {
                background: transparent;
                border: none;
            }
        """)
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(5)
        
        # Check if currently equipped
        is_equipped = self.user_data.get('equipped', {}).get(reward['type']) == reward_id
        
        if reward['type'] == 'game':
            # Only Launch button for games (no unequip needed)
            action_btn = QPushButton("🎮 Launch")
            action_btn.setText("LAUNCH")
            action_btn.setStyleSheet(_catalog_button_style("launch"))
            action_btn.clicked.connect(lambda: self.launch_game(reward_id))
            buttons_layout.addWidget(action_btn)
        else:
            # Toggle button for other items (Equip/Unequip)
            if is_equipped:
                action_btn = QPushButton("✗ Unequip")
                action_btn.setText("UNEQUIP")
                action_btn.setStyleSheet(_catalog_button_style("unequip"))
                action_btn.clicked.connect(lambda: self.unequip_reward(reward['type']))
            else:
                action_btn = QPushButton("✓ Equip")
                action_btn.setText("EQUIP")
                action_btn.setStyleSheet(_catalog_button_style("equip"))
                action_btn.clicked.connect(lambda: self.equip_reward(reward_id))
            buttons_layout.addWidget(action_btn)
        
        row_layout.addWidget(buttons_frame)
        
        # Create a container layout to hold the row
        container_layout = QVBoxLayout()
        container_layout.addLayout(row_layout)
        container_layout.setContentsMargins(0, 0, 0, 0)
        
        return container_layout

    def unequip_row(self, reward_type):
        """Create unequip section for a reward type"""
        # No longer needed, return an empty layout
        return QVBoxLayout()

    def equip_reward(self, reward_id):
        """Equip a reward"""
        logging.info(f"Equiped item: {reward_id}")
        reward = REWARDS[reward_id]
        logging.info(f"Reward details: {reward}")
        self.user_data['equipped'][reward['type']] = reward_id
        logging.info(f"Updated equipped item: {self.user_data['equipped']}")
        save_user_rewards(self.user_data)
        logging.info("User rewards saved")
        
        # Apply to main window
        if self.parent() and hasattr(self.parent(), 'apply_equipped_rewards'):
            logging.debug("[DEBUG] Calling parent.apply_equipped_rewards()")
            self.parent().apply_equipped_rewards()
        else:
            logging.debug("[DEBUG] Parent or apply_equipped_rewards method not found")
        
        # Show success message
        box = self.create_styled_message_box("Equipped", f"Equipped {reward['name']}!")
        box.exec_()
        
        # Refresh the dialog
        self.refresh()

    def unequip_reward(self, reward_type):
        """Unequip a reward type"""
        if reward_type in self.user_data.get('equipped', {}):
            del self.user_data['equipped'][reward_type]
            save_user_rewards(self.user_data)
            
            # Apply to main window
            if self.parent() and hasattr(self.parent(), 'apply_equipped_rewards'):
                self.parent().apply_equipped_rewards()
            
            # Show success message
            box = self.create_styled_message_box("Unequipped", f"Removed {get_reward_type_label(reward_type).lower()} item!")
            box.exec_()
            
            # Refresh the dialog
            self.refresh()

    def launch_game(self, reward_id):
        """Launch a game"""
        reward = REWARDS[reward_id]
        if reward_id == 'game_tetris':
            # Import TetrisGame lazily to avoid circular import issues
            # (pyqt_tetris imports from pyqt_dialogs)
            try:
                from .pyqt_tetris import TetrisGame
            except ImportError as e:
                logging.error(f"Failed to import TetrisGame: {e}")
                QMessageBox.warning(self, "Error", "Failed to load Tetris game. Please check the installation.")
                return
            
            # Launch Tetris game
            self.tetris_window = TetrisGame()
            
            # Store reference to the game window for focus management after dialog closes
            game_window = self.tetris_window
            
            # Use QTimer to ensure proper window stacking order
            def bring_game_to_front():
                # Minimize the main GUI window to give focus to the game
                if self.parent():
                    self.parent().showMinimized()
                
                game_window.show()
                game_window.raise_()
                game_window.activateWindow()
                # Ensure the game window gets focus and can receive keyboard events
                game_window.setFocus()
                game_window.setFocusPolicy(Qt.StrongFocus)
                # Force the window to be on top
                game_window.setWindowState(game_window.windowState() & ~Qt.WindowMinimized)
                game_window.showNormal()
                # Additional force to front
                game_window.raise_()
                game_window.activateWindow()
            
            # Use a small delay to ensure proper window management
            QTimer.singleShot(50, bring_game_to_front)
            
            # Close the inventory dialog and then force focus to game after dialog is closed
            def close_and_focus():
                self.accept()
                # Force focus to game window after dialog is completely closed
                QTimer.singleShot(200, lambda: game_window.setFocus())
                QTimer.singleShot(300, lambda: game_window.activateWindow())
                QTimer.singleShot(400, lambda: game_window.setFocus())
            
            QTimer.singleShot(100, close_and_focus)
        else:
            box = self.create_styled_message_box("Game Launch", f"Launching {reward['name']}...")
            box.exec_()

    def create_styled_message_box(self, title, message, icon=QMessageBox.Information):
        """Create a properly styled message box with modern theme"""
        # Map QMessageBox icons to ModernMessageBox msg_type
        msg_type = "info"
        if icon == QMessageBox.Warning:
            msg_type = "warning"
        elif icon == QMessageBox.Critical:
            msg_type = "error"
        
        return ModernMessageBox(title, message, msg_type, self)

    def focus_inventory_reward(self):
        """Scroll Inventory to a specific reward row after the dialog renders."""
        reward_id = getattr(self, 'focus_reward_id', None)
        reward = REWARDS.get(reward_id, {})
        reward_type = reward.get("type")
        if reward_type and self._expanded_category != reward_type:
            self.apply_category_expansion(reward_type)
            QApplication.processEvents()

        target = self._inventory_rows.get(reward_id)
        if not reward_id or not target or not hasattr(self, 'inventory_scroll'):
            return

        QApplication.processEvents()
        content = self.inventory_scroll.widget()
        if not content:
            return

        y = target.mapTo(content, QPoint(0, 0)).y()
        self.inventory_scroll.verticalScrollBar().setValue(max(0, y - 24))

    def clear_layout(self, layout):
        """Clear all widgets and sub-layouts from a layout"""
        if layout is None:
            return
            
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
            else:
                sublayout = item.layout()
                if sublayout is not None:
                    self.clear_layout(sublayout)
        
        # Force layout update
        layout.update()

    def refresh(self):
        """Refresh the inventory display"""
        expanded_category = self._expanded_category
        # Reload user data
        self.user_data = load_user_rewards()
        self.catalog_font_family = _catalog_font_family(self.parent())
        self.setFont(QFont(self.catalog_font_family, 10))
        self.setStyleSheet(_catalog_dialog_style(self.catalog_font_family))
        
        # Remove and rebuild inventory list
        self.clear_layout(self.inventory_layout)
        self._inventory_rows = {}
        self._category_sections = {}
        self._expanded_category = None
        
        owned_rewards_by_type = self.build_owned_rewards_by_type()
        
        for reward_type, section_title in INVENTORY_SECTIONS:
            if reward_type in owned_rewards_by_type:
                self.add_inventory_section(reward_type, section_title, owned_rewards_by_type[reward_type])
        
        # Show message if no items owned
        if not self._category_sections:
            no_items_label = QLabel("No items in inventory yet.\nVisit the Shop to purchase items!")
            no_items_label.setStyleSheet("""
                font-size: 16px;
                color: #888888;
                text-align: center;
                padding: 40px;
            """)
            no_items_label.setAlignment(Qt.AlignCenter)
            self.inventory_layout.addWidget(no_items_label)
        
        # Force the dialog to update and repaint
        self.update()
        self.repaint()
        # Force layout update
        self.inventory_layout.update()
        # Process events to ensure UI updates
        QApplication.processEvents()
        if expanded_category:
            self.apply_category_expansion(expanded_category)
        if self.focus_reward_id:
            QTimer.singleShot(80, self.focus_inventory_reward)

    def eventFilter(self, obj, event):
        if hasattr(obj, '_preview_path') or hasattr(obj, '_reward'):
            reward = getattr(obj, '_reward', None)
            reward_id = getattr(obj, '_reward_id', None)
            preview_path = getattr(obj, '_preview_path', None)
            is_font_reward = bool(reward and reward.get("type") == "font")
            if event.type() == QEvent.Enter and (preview_path or is_font_reward):
                if self._inventory_tooltip:
                    self._inventory_tooltip.hide()
                    self._inventory_tooltip.deleteLater()
                name = get_reward_display_name(reward_id, reward) if reward else ""
                description = reward.get("description", "") if reward else ""
                font_family = _reward_font_family(reward, self.catalog_font_family) if is_font_reward else None
                self._inventory_tooltip = CustomTooltipWidget(
                    None,
                    preview=None if is_font_reward else preview_path,
                    font_preview_text=name if is_font_reward else None,
                    font_family=font_family,
                    reward_id=reward_id,
                    reward_type=reward.get("type") if reward else None,
                    name=name if is_font_reward else "",
                    description=description if is_font_reward else "",
                    margins=(4, 4, 4, 4) if not is_font_reward else (18, 18, 18, 18)
                )
                parent = self.parent() if self.parent() else self
                global_top_right = parent.mapToGlobal(parent.rect().topRight())
                tooltip_width = self._inventory_tooltip.sizeHint().width()
                x = global_top_right.x() - tooltip_width - 24
                y = global_top_right.y() + 24
                self._inventory_tooltip.move(x, y)
                self._inventory_tooltip.show()
            elif event.type() == QEvent.Leave:
                if self._inventory_tooltip:
                    self._inventory_tooltip.hide()
                    self._inventory_tooltip.deleteLater()
                    self._inventory_tooltip = None
        return super().eventFilter(obj, event)    
    
    def center_on_screen(self):
        """Center the dialog on the primary screen"""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
    
    def title_bar_mouse_press(self, event):
        """Handle mouse press on title bar for dragging"""
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def title_bar_mouse_move(self, event):
        """Handle mouse move on title bar for dragging"""
        if event.buttons() == Qt.LeftButton and hasattr(self, '_drag_position'):
            self.move(event.globalPos() - self._drag_position)
            event.accept()

