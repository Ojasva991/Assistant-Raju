"""
ui/theme.py
Colours, fonts and the Qt stylesheet (QSS) for the light and dark themes.
All colour values come from one place, so the look is easy to change and to explain.
"""

import os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt

ACCENT = "#26A269"        # Raju green
ACCENT_HOVER = "#1F8A59"
DANGER = "#D14343"
WARNING = "#C98A1B"


@dataclass(frozen=True)
class Tokens:
    name: str
    window: str
    panel: str
    raised: str
    border: str
    text: str
    muted: str
    accent: str = ACCENT
    accent_hover: str = ACCENT_HOVER
    danger: str = DANGER
    warning: str = WARNING


DARK = Tokens("dark", window="#14181C", panel="#1B2127", raised="#232B33",
              border="#2C3640", text="#E7ECEF", muted="#8A97A3")
LIGHT = Tokens("light", window="#F4F6F8", panel="#FFFFFF", raised="#EEF1F4",
               border="#DCE2E7", text="#18222B", muted="#667380")


def detect_dark(app) -> bool:
    """True when the system uses a dark theme. RAJU_THEME=dark|light overrides it
    (handy for screenshots)."""
    forced = os.environ.get("RAJU_THEME", "").lower()
    if forced in ("dark", "light"):
        return forced == "dark"
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # older Qt: judge by the window colour instead
        return app.palette().window().color().lightness() < 128


def tokens_for(mode: str, app=None) -> Tokens:
    """mode is 'system', 'light' or 'dark'."""
    if mode == "dark":
        return DARK
    if mode == "light":
        return LIGHT
    return DARK if (app is not None and detect_dark(app)) else LIGHT


def stylesheet(t: Tokens) -> str:
    # No shadows and no gradients (spec). Radii: bubbles 14, inputs and buttons 8, panels 10.
    return f"""
* {{ font-family: "Segoe UI", sans-serif; font-size: 10.5pt; color: {t.text}; }}
QMainWindow, QWidget#root, QWidget#page {{ background: {t.window}; }}
QToolTip {{ background: {t.raised}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}

QFrame#sidebar {{ background: {t.panel}; border-right: 1px solid {t.border}; }}
QLabel#brand {{ font-size: 13pt; font-weight: 600; padding: 4px 8px; }}
QPushButton#nav {{ text-align: left; padding: 8px 12px; border: 2px solid transparent;
    border-radius: 8px; background: transparent; }}
QPushButton#nav:hover {{ background: {t.raised}; }}
QPushButton#nav:checked {{ background: {t.raised}; font-weight: 600; }}
QPushButton#nav:focus {{ border: 2px solid {t.accent}; }}

QLabel#heading {{ font-size: 13pt; font-weight: 600; }}
QLabel#muted {{ color: {t.muted}; font-size: 9pt; }}
QLabel#pill {{ background: {t.raised}; border: 1px solid {t.border}; border-radius: 10px;
    padding: 3px 12px; font-size: 9pt; }}
QLabel#pill[state="listening"] {{ border: 1px solid {t.accent}; }}
QLabel#pill[state="error"] {{ border: 1px solid {t.danger}; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QFrame#bubble {{ border-radius: 14px; }}
QFrame#bubble[role="raju"] {{ background: {t.raised}; border: 1px solid {t.border}; }}
QFrame#bubble[role="user"] {{ background: {t.accent}; }}
QFrame#bubble[role="user"] QLabel {{ color: #FFFFFF; }}
QLabel#sysline {{ color: {t.muted}; font-size: 9pt; }}

QLineEdit {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 8px; padding: 8px 10px;
    selection-background-color: {t.accent}; selection-color: #FFFFFF; }}
QLineEdit:focus {{ border: 2px solid {t.accent}; padding: 7px 9px; }}
QPushButton#primary {{ background: {t.accent}; color: #FFFFFF; border: 2px solid {t.accent};
    border-radius: 8px; padding: 7px 18px; font-weight: 600; }}
QPushButton#primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton#primary:focus {{ border: 2px solid {t.text}; }}

QFrame#row, QFrame#panel {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 10px; }}
QFrame#row QLabel, QFrame#panel QLabel {{ background: transparent; border: none; }}
QFrame#row QLabel#muted, QFrame#panel QLabel#muted {{ color: {t.muted}; }}

QPushButton {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 8px;
    padding: 7px 14px; }}
QPushButton:hover {{ background: {t.raised}; }}
QPushButton:focus {{ border: 2px solid {t.accent}; padding: 6px 13px; }}
QPushButton:disabled {{ color: {t.muted}; background: {t.window}; }}
QPushButton#danger {{ color: {t.danger}; border: 1px solid {t.danger}; }}
QPushButton#danger:hover {{ background: {t.raised}; }}
QPushButton#danger:focus {{ border: 2px solid {t.danger}; padding: 6px 13px; }}
QPushButton#danger:disabled {{ color: {t.muted}; border: 1px solid {t.border}; }}

QComboBox {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 8px;
    padding: 7px 10px; }}
QComboBox:focus {{ border: 2px solid {t.accent}; padding: 6px 9px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {t.panel}; border: 1px solid {t.border};
    selection-background-color: {t.accent}; selection-color: #FFFFFF; }}

QTableWidget {{ background: {t.panel}; border: 1px solid {t.border}; border-radius: 10px;
    selection-background-color: {t.accent}; selection-color: #FFFFFF; }}
QTableWidget::item {{ padding: 6px 8px; border: none; }}
QTableWidget:focus {{ border: 2px solid {t.accent}; }}
QHeaderView::section {{ background: {t.raised}; color: {t.muted}; border: none;
    border-bottom: 1px solid {t.border}; padding: 6px 8px; font-size: 9pt; }}
QTableCornerButton::section {{ background: {t.raised}; border: none; }}

QStatusBar {{ background: {t.panel}; border-top: 1px solid {t.border}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t.muted}; font-size: 9pt; }}
QCheckBox {{ font-size: 9pt; spacing: 6px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.border}; border-radius: 4px;
    background: {t.window}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QCheckBox:focus {{ color: {t.accent}; }}
"""
