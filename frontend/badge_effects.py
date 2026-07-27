"""Runtime animation helpers for earned achievement badges.

Elemental personality effects stay as transparent overlays. Mechanical badge
idles are different: they play full badge frames on the badge label itself so
moving parts do not ghost over a frozen original.
"""

from __future__ import annotations

import random
from pathlib import Path

from PyQt5.QtCore import QObject, QRectF, Qt, QTimer
from PyQt5.QtGui import QImage, QPainter, QPixmap
from PyQt5.QtWidgets import QWidget

from core.smducar_config import resource_path


VFX_DIR = Path(resource_path("assets")) / "images" / "badge_vfx"
MECH_DIR = Path(resource_path("assets")) / "images" / "badge_mech"
BADGE_VFX_OPACITY = 0.88
COMPACT_BADGE_VFX_OPACITY = 0.76


BADGE_EFFECTS = {
    "achievement_first_route_badge": "first_route_air",
    "achievement_routing_spark_badge": "routing_spark_lightning",
    "title_lni_whisperer": "lni_whisperer_mist",
    "achievement_brief_storm_badge": "brief_storm_lightning",
    "achievement_hundred_club_badge": "hundred_club_fire",
    "achievement_thousand_routes_badge": "thousand_crown_meteor",
    "title_queue_slayer": "queue_slayer_earth",
    "title_final_reviewer": "final_reviewer_solar",
    "achievement_calendar_crusher_badge": "calendar_crusher_water",
    "achievement_docket_warlord_badge": "docket_warlord_magma",
    "achievement_legendary_circuit_badge": "legendary_circuit_electric",
    "achievement_clean_sweep_badge": "clean_sweep_growth",
    "achievement_precision_streak_badge": "precision_streak_frost",
    "title_archive_authority": "archive_authority_stone",
    "achievement_audit_proof_badge": "audit_proof_steel",
    "achievement_immaculate_badge": "immaculate_crystal",
    "achievement_parallel_boss_badge": "parallel_boss_air",
    "achievement_router_captain_badge": "router_captain_beacon",
    "achievement_router_admiral_badge": "router_admiral_network",
    "achievement_full_bench_badge": "full_bench_six_orbit",
    "title_six_router_menace": "six_router_void",
    "achievement_no_misses_badge": "no_misses_impact",
    "achievement_no_misses_50_badge": "no_misses_elite_cracks",
    "achievement_no_misses_100_badge": "no_misses_apex_explosion",
    "title_docket_diva": "docket_diva_prism_water",
    "achievement_court_hopper_badge": "court_hopper_portal",
    "achievement_jurisdiction_juggler_badge": "jurisdiction_juggler_swarm",
    "achievement_full_spectrum_badge": "full_spectrum_elements",
    "achievement_night_shift_badge": "night_shift_moon_vapor",
    "achievement_midnight_operator_badge": "midnight_operator_neon_fumes",
}


BADGE_MECH_EFFECTS = {
    "achievement_first_route_badge": "first_route_gate",
    "achievement_routing_spark_badge": "routing_spark_core_latches",
    "title_lni_whisperer": "title_lni_whisperer_parts",
    "achievement_brief_storm_badge": "brief_storm_paper_shutters",
    "achievement_hundred_club_badge": "hundred_club_heat_vents",
    "achievement_thousand_routes_badge": "thousand_crown_lock",
    "title_queue_slayer": "title_queue_slayer_parts",
    "title_final_reviewer": "title_final_reviewer_parts",
    "achievement_calendar_crusher_badge": "calendar_tick_shutters",
    "achievement_docket_warlord_badge": "docket_warlord_armor_lock",
    "achievement_legendary_circuit_badge": "legendary_circuit_calibration",
    "achievement_clean_sweep_badge": "clean_sweep_guardian_clamps",
    "achievement_precision_streak_badge": "precision_frost_servo",
    "title_archive_authority": "title_archive_authority_parts",
    "achievement_audit_proof_badge": "audit_vault_lock",
    "achievement_immaculate_badge": "immaculate_crystal_prongs",
    "achievement_parallel_boss_badge": "parallel_rail_shift",
    "achievement_router_captain_badge": "captain_beacon_panels",
    "achievement_router_admiral_badge": "admiral_command_ring",
    "achievement_full_bench_badge": "full_bench_docking",
    "title_six_router_menace": "title_six_router_menace_parts",
    "achievement_no_misses_badge": "no_misses_reticle_lock",
    "achievement_no_misses_50_badge": "no_misses_elite_seal",
    "achievement_no_misses_100_badge": "no_misses_apex_unfold",
    "title_docket_diva": "title_docket_diva_parts",
    "achievement_court_hopper_badge": "court_hopper_portal_gate",
    "achievement_jurisdiction_juggler_badge": "jurisdiction_swarm_grid",
    "achievement_full_spectrum_badge": "full_spectrum_segment_ring",
    "achievement_night_shift_badge": "night_shift_moon_panels",
    "achievement_midnight_operator_badge": "midnight_terminal_locks",
}


_FRAME_CACHE: dict[str, list[QPixmap]] = {}
_MECH_FRAME_CACHE: dict[str, list[QPixmap]] = {}


def has_badge_effect(reward_id: str | None) -> bool:
    """Return whether a reward id has a custom elemental overlay."""
    return bool(reward_id in BADGE_EFFECTS)


def has_badge_motion(reward_id: str | None) -> bool:
    """Return whether a reward id has a full-frame mechanical idle."""
    return bool(reward_id in BADGE_MECH_EFFECTS)


def _load_frames(cache: dict[str, list[QPixmap]], root_dir: Path, effect_key: str | None) -> list[QPixmap]:
    if not effect_key:
        return []
    if effect_key in cache:
        return cache[effect_key]

    effect_dir = root_dir / effect_key
    frames = []
    if effect_dir.exists():
        for path in sorted(effect_dir.glob("*.png")):
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                frames.append(pixmap)

    cache[effect_key] = frames
    return frames


def _pixmap_alpha_bounds(pixmap: QPixmap):
    """Return the visible alpha bounds of a pixmap, or None for empty images."""
    if pixmap.isNull():
        return None

    image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    width = image.width()
    height = image.height()
    min_x, min_y = width, height
    max_x, max_y = -1, -1

    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 8:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < min_x or max_y < min_y:
        return None
    return min_x, min_y, max_x + 1, max_y + 1


class BadgeEffectLayer(QWidget):
    """Transparent QWidget that plays elemental badge VFX only."""

    def __init__(self, parent=None, reward_id: str | None = None, compact: bool = False):
        super().__init__(parent)
        self.reward_id = None
        self.effect_key = None
        self.compact = compact
        self._frame = 0
        self._pause_ticks = 0
        self._frames: list[QPixmap] = []
        self._timer = QTimer(self)
        self._timer.setInterval(random.randint(96, 132))
        self._timer.timeout.connect(self._advance)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.hide()
        self.set_badge(reward_id)

    def set_badge(self, reward_id: str | None):
        self.reward_id = reward_id
        self.effect_key = BADGE_EFFECTS.get(reward_id)
        self._frames = _load_frames(_FRAME_CACHE, VFX_DIR, self.effect_key)
        self._frame = random.randrange(len(self._frames)) if self._frames else 0
        self._pause_ticks = random.randint(0, 10) if self._frames else 0
        if self._frames:
            self.start()
        else:
            self.stop()

    def start(self):
        if not self._frames:
            return
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self.hide()

    def _advance(self):
        changed = False

        if self._frames:
            if self._pause_ticks > 0:
                self._pause_ticks -= 1
            else:
                previous_frame = self._frame
                self._frame = (self._frame + 1) % len(self._frames)
                if previous_frame > self._frame:
                    self._pause_ticks = random.randint(8, 24)
                    self._timer.setInterval(random.randint(96, 140))
                changed = True

        if changed:
            self.update()

    def _target_rect(self):
        side = min(self.width(), self.height())
        if side <= 0:
            return QRectF()
        margin = max(0, int(side * (0.02 if self.compact else 0.00)))
        side -= margin * 2
        return QRectF(
            (self.width() - side) / 2,
            (self.height() - side) / 2,
            side,
            side,
        )

    def paintEvent(self, event):
        target_rect = self._target_rect()
        if target_rect.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        if self._frames:
            pixmap = self._frames[self._frame % len(self._frames)]
            if not pixmap.isNull():
                painter.setOpacity(COMPACT_BADGE_VFX_OPACITY if self.compact else BADGE_VFX_OPACITY)
                painter.drawPixmap(target_rect, pixmap, QRectF(pixmap.rect()))


class BadgeMechanicalAnimator(QObject):
    """Play rare full-frame mechanical badge idles on the badge QLabel itself."""

    def __init__(
        self,
        label,
        reward_id: str | None,
        base_pixmap: QPixmap,
        motion_scale: float = 1.0,
        parent=None,
    ):
        super().__init__(parent or label)
        self.label = label
        self.reward_id = reward_id
        self.base_pixmap = QPixmap(base_pixmap)
        self.motion_scale = max(0.25, float(motion_scale or 1.0))
        self.mech_key = BADGE_MECH_EFFECTS.get(reward_id)
        self._frames = _load_frames(_MECH_FRAME_CACHE, MECH_DIR, self.mech_key)
        self.motion_scale = self._resolve_motion_scale()
        self._frame = -1
        self._cooldown = random.randint(70, 170)
        self._timer = QTimer(self)
        self._timer.setInterval(random.randint(92, 132))
        self._timer.timeout.connect(self._advance)

    def has_frames(self) -> bool:
        return bool(self._frames)

    def _resolve_motion_scale(self) -> float:
        """Match animation-frame visible bounds to the idle badge visible bounds."""
        if not self.label or not self._frames or self.base_pixmap.isNull():
            return self.motion_scale

        target_size = self.label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return self.motion_scale

        base_bounds = _pixmap_alpha_bounds(self.base_pixmap)
        frame_bounds = _pixmap_alpha_bounds(self._frames[0])
        if not base_bounds or not frame_bounds:
            return self.motion_scale

        base_w = max(1, base_bounds[2] - base_bounds[0])
        base_h = max(1, base_bounds[3] - base_bounds[1])
        frame_w = max(1, frame_bounds[2] - frame_bounds[0])
        frame_h = max(1, frame_bounds[3] - frame_bounds[1])
        frame_pixmap = self._frames[0]

        scale_w = (base_w / target_size.width()) / (frame_w / frame_pixmap.width())
        scale_h = (base_h / target_size.height()) / (frame_h / frame_pixmap.height())
        scale = max(self.motion_scale, scale_w, scale_h)
        return max(0.25, min(1.24, scale))

    def start(self) -> None:
        if self._frames and not self._timer.isActive():
            self._timer.start()

    def stop(self, restore: bool = True) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self._frame = -1
        if restore:
            self._restore_base()

    def _restore_base(self) -> None:
        if self.label and not self.base_pixmap.isNull():
            self.label.setPixmap(self.base_pixmap)

    def _scaled(self, pixmap: QPixmap) -> QPixmap:
        if not self.label or pixmap.isNull():
            return pixmap
        target_size = self.label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return pixmap
        scaled_width = max(1, round(target_size.width() * self.motion_scale))
        scaled_height = max(1, round(target_size.height() * self.motion_scale))
        return pixmap.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _advance(self) -> None:
        if not self._frames or not self.label:
            return

        if self._frame >= 0:
            pixmap = self._frames[self._frame % len(self._frames)]
            self.label.setPixmap(self._scaled(pixmap))
            self._frame += 1
            if self._frame >= len(self._frames):
                self._frame = -1
                self._cooldown = random.randint(75, 190)
                self._timer.setInterval(random.randint(92, 132))
                self._restore_base()
            return

        self._cooldown -= 1
        if self._cooldown <= 0:
            self._frame = 0
            self._timer.setInterval(random.randint(76, 104))
