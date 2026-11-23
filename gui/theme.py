"""
Anime Subtitle Automation Tool — theme

Direction: an editing timeline at night. One graphite ramp tinted slightly
blue, three text roles, one blue accent used rarely, red only for errors.
Depth comes from surface steps and hairlines; nothing glows. All colours live
in `Colors` so widgets never hard-code a hex value.
"""

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

# Icons used by the stylesheet (also bundled inside the .exe with the gui folder)
ASSETS = (Path(__file__).resolve().parent / "assets").as_posix()


class Colors:
    # Surfaces, darkest to lightest (graphite with a faint night-blue tint)
    bg_deep: str = "#0e0f12"     # sidebar, status bar
    bg: str = "#121317"          # page
    surface: str = "#17191e"     # cards, table, panels
    raised: str = "#1d2026"      # buttons, active nav row
    hover: str = "#24272e"
    input: str = "#101115"

    # Lines (hex so QPainter can use them too)
    hairline: str = "#24262c"
    hairline_strong: str = "#30333a"

    # Text roles
    text: str = "#e8eaf0"
    text_secondary: str = "#a2a7b3"
    text_muted: str = "#6b707c"

    # The one accent (the product's blue, calmed down), and text placed on it
    accent: str = "#5aa9f5"
    accent_hover: str = "#7bbcf8"
    accent_text: str = "#0a1320"
    accent_soft: str = "#1b2a3b"

    # Meaning only, toned down
    positive: str = "#4cc38a"
    warning: str = "#d9a43a"
    negative: str = "#e5484d"
    negative_soft: str = "#2a1719"

    # Fonts: one interface family plus mono for numbers and episode chips
    font_ui: str = "'Segoe UI Variable Text', 'Segoe UI', sans-serif"
    font_mono: str = "'Consolas', monospace"

    # Older names still used in a few places
    blue = accent
    blue_bright = accent
    red = negative
    red_bright = negative
    amber = warning
    border = hairline_strong
    border_hover = hairline_strong
    bg_input = input


def plain_tooltip(text: str) -> str:
    """Tooltip text that is never interpreted as markup.

    Qt renders a tooltip as rich text whenever it looks like HTML, and tooltips
    here show file names and messages taken from files.
    """
    import html

    return "<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>"


def apply_palette(app) -> None:
    """Dark base palette so popups, item views and dialogs never fall back to Qt's light defaults."""
    from PySide6.QtGui import QPalette

    c = Colors
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: c.bg,
        QPalette.ColorRole.WindowText: c.text,
        QPalette.ColorRole.Base: c.input,
        QPalette.ColorRole.AlternateBase: c.surface,
        QPalette.ColorRole.Text: c.text,
        QPalette.ColorRole.Button: c.raised,
        QPalette.ColorRole.ButtonText: c.text,
        QPalette.ColorRole.Highlight: c.accent_soft,
        QPalette.ColorRole.HighlightedText: c.text,
        QPalette.ColorRole.ToolTipBase: c.raised,
        QPalette.ColorRole.ToolTipText: c.text,
        QPalette.ColorRole.PlaceholderText: c.text_muted,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    app.setPalette(pal)


def page_header(title: str, subtitle: str) -> QWidget:
    """Page title and one line saying what the page is for."""
    from PySide6.QtWidgets import QLabel, QVBoxLayout

    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    t = QLabel(title)
    t.setProperty("role", "pageTitle")
    st = QLabel(subtitle)
    st.setProperty("role", "pageSubtitle")
    lay.addWidget(t)
    lay.addWidget(st)
    return box


def get_stylesheet() -> str:
    c = Colors
    return f"""
    QWidget {{
        color: {c.text};
        font-family: {c.font_ui};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {c.bg}; }}
    QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QToolTip {{
        background: {c.raised};
        color: {c.text};
        border: 1px solid {c.hairline_strong};
        border-radius: 6px;
        padding: 6px 8px;
    }}

    /* ── Text roles (setProperty("role", ...)) ── */
    QLabel[role="pageTitle"] {{
        font-size: 24px;
        font-weight: 600;
        color: {c.text};
        background: transparent;
    }}
    QLabel[role="pageSubtitle"] {{ font-size: 13px; color: {c.text_secondary}; background: transparent; }}
    QLabel[role="fieldLabel"] {{ font-size: 12px; color: {c.text_secondary}; background: transparent; }}
    QLabel[role="sectionLabel"] {{ font-size: 12px; color: {c.text_muted}; background: transparent; }}
    QLabel[role="hint"] {{ font-size: 12px; color: {c.text_muted}; background: transparent; }}
    QLabel[role="mono"] {{
        font-family: {c.font_mono}; font-size: 12px; color: {c.text_secondary}; background: transparent;
    }}
    QLabel[role="ok"] {{ color: {c.positive}; font-size: 12px; background: transparent; }}
    QLabel[role="bad"] {{ color: {c.negative}; font-size: 12px; background: transparent; }}
    QLabel[role="warn"] {{ color: {c.warning}; font-size: 12px; background: transparent; }}

    /* ── Cards ── */
    QGroupBox {{
        background-color: {c.surface};
        border: 1px solid {c.hairline};
        border-radius: 12px;
        margin-top: 28px;
        padding: 12px 12px 12px 12px;
        font-size: 13px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 4px;
        padding: 0 0 8px 0;
        color: {c.text};
        background: transparent;
    }}
    QFrame#card {{
        background-color: {c.surface};
        border: 1px solid {c.hairline};
        border-radius: 12px;
    }}

    /* ── Inputs ── */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {c.input};
        border: 1px solid {c.hairline_strong};
        border-radius: 8px;
        padding: 6px 10px;
        min-height: 20px;
        color: {c.text};
        selection-background-color: {c.accent_soft};
        selection-color: {c.text};
    }}
    QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: #3b3f48; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {c.accent}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {c.text_muted};
        background-color: {c.bg};
        border-color: {c.hairline};
    }}
    QLineEdit[state="ok"] {{ border: 1px solid {c.hairline_strong}; }}
    QLineEdit[state="bad"] {{ border: 1px solid {c.negative}; }}

    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        width: 20px; border: none; background: transparent;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {c.hover}; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({ASSETS}/arrow_up.svg); width: 10px; height: 6px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({ASSETS}/arrow_down.svg); width: 10px; height: 6px; }}

    /* combobox-popup: 0 = a scrolling list that respects maxVisibleItems */
    QComboBox {{ combobox-popup: 0; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url({ASSETS}/arrow_down.svg); width: 10px; height: 6px; }}
    QComboBox QAbstractItemView {{
        background-color: {c.raised};
        border: 1px solid {c.hairline_strong};
        border-radius: 8px;
        padding: 4px;
        selection-background-color: {c.hover};
        selection-color: {c.text};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 0 8px; border-radius: 6px; }}

    /* Searchable language popup */
    QFrame#langPopup {{
        background: {c.raised};
        border: 1px solid {c.hairline_strong};
        border-radius: 10px;
    }}
    QFrame#langPopup QListView {{ background: transparent; border: none; outline: none; }}
    QFrame#langPopup QListView::item {{ min-height: 28px; padding: 0 8px; color: {c.text}; border-radius: 6px; }}
    QFrame#langPopup QListView::item:hover {{ background: {c.hover}; }}
    QFrame#langPopup QListView::item:selected {{ background: {c.hover}; color: {c.text}; }}
    QFrame#langPopup QListView::indicator {{
        width: 14px; height: 14px; border-radius: 4px;
        border: 1px solid #3b3f48; background: {c.input};
    }}
    QFrame#langPopup QListView::indicator:checked {{
        background: {c.accent}; border: 1px solid {c.accent}; image: url({ASSETS}/check.svg);
    }}

    QCheckBox {{ spacing: 8px; background: transparent; color: {c.text}; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 4px;
        border: 1px solid #3b3f48; background: {c.input};
    }}
    QCheckBox::indicator:hover {{ border-color: #4a4f5a; }}
    QCheckBox::indicator:checked {{
        background: {c.accent}; border: 1px solid {c.accent}; image: url({ASSETS}/check.svg);
    }}
    QCheckBox:focus {{ outline: none; }}

    /* ── Buttons ── */
    QPushButton {{
        background-color: {c.raised};
        border: 1px solid {c.hairline_strong};
        border-radius: 8px;
        padding: 7px 14px;
        color: {c.text};
        font-weight: 500;
    }}
    QPushButton:hover {{ background-color: {c.hover}; }}
    QPushButton:pressed {{ background-color: {c.surface}; }}
    QPushButton:focus {{ border: 1px solid {c.accent}; }}
    QPushButton:disabled {{ color: {c.text_muted}; background-color: {c.surface}; border-color: {c.hairline}; }}

    QPushButton#primaryButton {{
        background-color: {c.accent};
        border: 1px solid {c.accent};
        color: {c.accent_text};
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{ background-color: {c.accent_hover}; border-color: {c.accent_hover}; }}
    QPushButton#primaryButton:pressed {{ background-color: #4a97e0; }}
    QPushButton#primaryButton:focus {{ border: 1px solid {c.text}; }}
    QPushButton#primaryButton:disabled {{
        background-color: {c.raised}; border-color: {c.hairline}; color: {c.text_muted};
    }}

    QPushButton#dangerButton {{ color: {c.negative}; }}
    QPushButton#dangerButton:hover {{ background-color: {c.negative_soft}; }}

    QPushButton#ghostButton {{ background: transparent; border: 1px solid transparent; color: {c.text_secondary}; }}
    QPushButton#ghostButton:hover {{ background: {c.hover}; color: {c.text}; }}

    /* Sidebar: tool rows and the merge steps under them */
    QPushButton#modeButton {{
        text-align: left;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 0 10px;
        min-height: 34px;
        max-height: 34px;
        color: {c.text_secondary};
        font-weight: 500;
        background: transparent;
    }}
    QPushButton#modeButton:hover {{ background: {c.surface}; color: {c.text}; }}
    QPushButton#modeButton[active="true"] {{
        background: {c.raised};
        border: 1px solid {c.hairline};
        color: {c.text};
    }}
    QPushButton#navButton {{
        text-align: left;
        border: none;
        border-radius: 6px;
        padding: 0 10px 0 36px;
        min-height: 28px;
        max-height: 28px;
        color: {c.text_muted};
        font-size: 12px;
        background: transparent;
    }}
    QPushButton#navButton[state="active"] {{ color: {c.text}; }}
    QPushButton#navButton[state="done"], QPushButton#navButton[state="paused"] {{ color: {c.text_secondary}; }}

    QPushButton#linkButton {{
        text-align: left;
        border: none;
        border-radius: 8px;
        padding: 0 10px;
        min-height: 32px;
        color: {c.text_secondary};
        background: transparent;
    }}
    QPushButton#linkButton:hover {{ color: {c.text}; background: {c.surface}; }}

    /* Small nudge buttons on the sync page */
    QPushButton#nudgeButton {{
        padding: 6px 4px;
        font-family: {c.font_mono};
        font-size: 12px;
        color: {c.text_secondary};
    }}
    QPushButton#nudgeButton:hover {{ color: {c.text}; }}

    QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {c.hairline_strong}; }}
    QSlider::sub-page:horizontal {{ border-radius: 2px; background: {c.text_secondary}; }}
    QSlider::handle:horizontal {{
        width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {c.text};
    }}
    QProgressBar {{
        background: {c.hairline_strong}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px;
    }}
    QProgressBar::chunk {{ background: {c.accent}; border-radius: 2px; }}
    QGraphicsView {{ background: #000000; border: 1px solid {c.hairline}; border-radius: 12px; }}

    QFrame#sidebar {{
        background-color: {c.bg_deep};
        border: none;
        border-right: 1px solid {c.hairline};
    }}

    /* ── Scrollbars ── */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c.hairline_strong}; min-height: 24px; border-radius: 3px; }}
    QScrollBar::handle:vertical:hover {{ background: #3b3f48; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {c.hairline_strong}; min-width: 24px; border-radius: 3px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ── Table ── */
    QTableWidget {{
        background-color: {c.surface};
        border: 1px solid {c.hairline};
        border-radius: 12px;
        gridline-color: transparent;
        outline: none;
        selection-background-color: {c.raised};
        selection-color: {c.text};
    }}
    QTableWidget::item {{ padding: 0 8px; border-bottom: 1px solid {c.hairline}; }}
    QTableWidget::item:selected {{ background-color: {c.raised}; color: {c.text}; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{
        background-color: {c.surface};
        color: {c.text_muted};
        padding: 0 8px;
        height: 36px;
        border: none;
        border-bottom: 1px solid {c.hairline};
        font-size: 12px;
        font-weight: 500;
    }}
    QTableCornerButton::section {{ background: {c.surface}; border: none; }}

    /* ── Log ── */
    QTextEdit {{
        background-color: {c.input};
        border: 1px solid {c.hairline};
        border-radius: 12px;
        padding: 12px;
        font-family: {c.font_mono};
        font-size: 12px;
    }}

    /* ── Status bar / menus / dialogs ── */
    QStatusBar {{
        background-color: {c.bg_deep};
        color: {c.text_muted};
        border-top: 1px solid {c.hairline};
        font-size: 12px;
    }}
    QStatusBar::item {{ border: none; }}
    QMenu {{ background: {c.raised}; border: 1px solid {c.hairline_strong}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {c.hover}; }}
    QMessageBox {{ background: {c.bg}; }}
    """
