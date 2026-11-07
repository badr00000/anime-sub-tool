"""
Anime Subtitle Automation Tool — Neon theme

Pure black base, neon blue as the main accent, neon red for alerts and the
second accent. Sharp corners, thin glowing borders, monospace labels.
All colours live in `Colors` so widgets never hard-code a hex value.
"""

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

# Icons used by the stylesheet (also bundled inside the .exe with the gui folder)
ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()


class Colors:
    # Surfaces
    bg: str = "#04060a"
    bg_panel: str = "rgba(8, 12, 20, 0.88)"
    bg_card: str = "rgba(10, 15, 24, 0.92)"
    bg_input: str = "#060a11"
    bg_hover: str = "#0e1724"
    bg_row_alt: str = "rgba(14, 22, 34, 0.55)"

    # Lines
    border: str = "#152131"
    border_hover: str = "#24394f"

    # Neon blue (primary)
    blue: str = "#00b7ff"
    blue_bright: str = "#5fd6ff"
    blue_deep: str = "#0077cc"
    blue_glow: str = "rgba(0, 183, 255, 0.16)"

    # Neon red (secondary / alerts)
    red: str = "#ff2b4e"
    red_bright: str = "#ff6680"
    red_deep: str = "#b3122f"
    red_glow: str = "rgba(255, 43, 78, 0.16)"

    # Warnings only (kept rare so blue/red stay the identity)
    amber: str = "#ffb020"

    # Text
    text: str = "#e6f0ff"
    text_secondary: str = "#9db0c6"
    text_muted: str = "#55667c"

    # Fonts
    font_ui: str = "'Segoe UI', 'Inter', sans-serif"
    font_mono: str = "'Cascadia Mono', 'Consolas', monospace"


def add_glow(widget: QWidget, color: str = Colors.blue, radius: int = 22) -> None:
    """Soft neon glow around a widget (use sparingly: each one costs a repaint pass)."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setColor(QColor(color))
    effect.setBlurRadius(radius)
    effect.setOffset(0, 0)
    widget.setGraphicsEffect(effect)


def get_stylesheet() -> str:
    c = Colors
    return f"""
    QWidget {{
        color: {c.text};
        font-family: {c.font_ui};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background: {c.bg};
    }}
    QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QToolTip {{
        background: {c.bg_input};
        color: {c.text};
        border: 1px solid {c.blue};
        padding: 6px;
    }}

    /* ── Text roles (set with setProperty("role", ...)) ── */
    QLabel[role="pageTitle"] {{
        font-size: 26px;
        font-weight: 800;
        letter-spacing: 3px;
        color: {c.text};
        background: transparent;
    }}
    QLabel[role="pageSubtitle"] {{
        font-size: 13px;
        color: {c.text_secondary};
        background: transparent;
    }}
    QLabel[role="fieldLabel"] {{
        font-family: {c.font_mono};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 2px;
        color: {c.blue};
        background: transparent;
    }}
    QLabel[role="hint"] {{
        font-size: 12px;
        color: {c.text_muted};
        background: transparent;
    }}
    QLabel[role="ok"] {{ color: {c.blue_bright}; font-size: 12px; background: transparent; }}
    QLabel[role="bad"] {{ color: {c.red}; font-size: 12px; background: transparent; }}

    /* ── Cards ── */
    QGroupBox {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-left: 2px solid {c.blue};
        border-radius: 2px;
        margin-top: 22px;
        padding: 10px 12px 12px 12px;
        font-family: {c.font_mono};
        font-size: 11px;
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 0px;
        padding: 2px 10px;
        font-family: {c.font_mono};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 2px;
        color: {c.blue};
        background: transparent;
    }}
    QFrame#card {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-radius: 2px;
    }}

    /* ── Inputs ── */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {c.bg_input};
        border: 1px solid {c.border};
        border-radius: 2px;
        padding: 7px 10px;
        min-height: 18px;
        color: {c.text};
        selection-background-color: {c.blue_deep};
    }}
    QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
        border-color: {c.border_hover};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {c.blue};
        background-color: #08101a;
    }}
    QLineEdit[state="ok"] {{ border: 1px solid {c.blue}; }}
    QLineEdit[state="bad"] {{ border: 1px solid {c.red}; }}

    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 18px;
        border: none;
        background: {c.bg_hover};
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {c.blue_glow};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url({ASSETS}/arrow_up.svg); width: 9px; height: 5px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url({ASSETS}/arrow_down.svg); width: 9px; height: 5px;
    }}

    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{
        image: url({ASSETS}/arrow_down.svg); width: 10px; height: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c.bg_input};
        border: 1px solid {c.blue};
        selection-background-color: {c.blue_glow};
        selection-color: {c.blue_bright};
        outline: none;
    }}

    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {c.border_hover};
        background: {c.bg_input};
    }}
    QCheckBox::indicator:hover {{ border-color: {c.blue}; }}
    QCheckBox::indicator:checked {{
        background: {c.blue};
        border: 1px solid {c.blue_bright};
        image: url({ASSETS}/check.svg);
    }}

    /* ── Buttons ── */
    QPushButton {{
        background-color: transparent;
        border: 1px solid {c.border_hover};
        border-radius: 2px;
        padding: 8px 18px;
        color: {c.text_secondary};
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QPushButton:hover {{
        border-color: {c.blue};
        color: {c.blue_bright};
        background-color: {c.blue_glow};
    }}
    QPushButton:pressed {{ background-color: rgba(0, 183, 255, 0.28); }}
    QPushButton:disabled {{ color: {c.text_muted}; border-color: {c.border}; }}

    QPushButton#primaryButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.blue_deep}, stop:1 {c.blue});
        border: 1px solid {c.blue_bright};
        color: #ffffff;
        font-weight: 800;
        letter-spacing: 2px;
    }}
    QPushButton#primaryButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.blue}, stop:1 {c.blue_bright});
        color: #001018;
    }}
    QPushButton#primaryButton:disabled {{
        background: {c.bg_hover};
        border-color: {c.border};
        color: {c.text_muted};
    }}

    QPushButton#dangerButton {{
        border: 1px solid {c.red};
        color: {c.red_bright};
        background: {c.red_glow};
        letter-spacing: 2px;
    }}
    QPushButton#dangerButton:hover {{
        background: {c.red};
        color: #ffffff;
    }}

    /* Sidebar navigation */
    QPushButton#navButton {{
        text-align: left;
        border: none;
        border-left: 3px solid transparent;
        padding: 12px 16px;
        color: {c.text_muted};
        font-family: {c.font_mono};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 2px;
        background: transparent;
    }}
    QPushButton#navButton[state="active"] {{
        border-left: 3px solid {c.blue};
        color: {c.blue_bright};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(0, 183, 255, 0.22), stop:1 rgba(0, 183, 255, 0));
    }}
    QPushButton#navButton[state="done"] {{
        color: {c.text_secondary};
    }}
    QPushButton#linkButton {{
        border: none;
        padding: 6px 4px;
        color: {c.text_muted};
        font-size: 12px;
        text-align: left;
        background: transparent;
    }}
    QPushButton#linkButton:hover {{ color: {c.blue_bright}; background: transparent; }}

    /* ── Sidebar frame ── */
    QFrame#sidebar {{
        background-color: rgba(4, 7, 12, 0.94);
        border: none;
        border-right: 1px solid {c.border};
    }}

    /* ── Scrollbars ── */
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c.border_hover}; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {c.blue}; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c.border_hover}; min-width: 24px; }}
    QScrollBar::handle:horizontal:hover {{ background: {c.blue}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ── Table ── */
    QTableWidget {{
        background-color: {c.bg_card};
        alternate-background-color: {c.bg_row_alt};
        border: 1px solid {c.border};
        gridline-color: transparent;
        outline: none;
        selection-background-color: {c.blue_glow};
        selection-color: {c.text};
    }}
    QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {c.border}; }}
    QTableWidget::item:selected {{ background-color: {c.blue_glow}; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{
        background-color: {c.bg_input};
        color: {c.blue};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {c.blue_deep};
        font-family: {c.font_mono};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QTableCornerButton::section {{ background: {c.bg_input}; border: none; }}

    /* ── Log ── */
    QTextEdit {{
        background-color: {c.bg_input};
        border: 1px solid {c.border};
        border-radius: 2px;
        padding: 8px;
        font-family: {c.font_mono};
        font-size: 12px;
    }}

    /* ── Status bar / menus / dialogs ── */
    QStatusBar {{
        background-color: {c.bg};
        color: {c.text_muted};
        border-top: 1px solid {c.border};
        font-family: {c.font_mono};
        font-size: 11px;
    }}
    QMenu {{ background: {c.bg_input}; border: 1px solid {c.blue}; }}
    QMenu::item:selected {{ background: {c.blue_glow}; color: {c.blue_bright}; }}
    QMessageBox {{ background: {c.bg}; }}
    """
