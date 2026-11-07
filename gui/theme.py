"""
Anime Subtitle Automation Tool v3.0 — Glassmorphism Theme

A breathtaking translucent theme that allows animated backgrounds to shine through.
Uses semi-transparent RGBA backgrounds and soft frosty borders.
"""

from dataclasses import dataclass

@dataclass
class Colors:
    """Glassmorphism color palette."""
    # Translucent backgrounds
    bg_window: str = "transparent"
    bg_panel: str = "rgba(15, 23, 42, 0.45)"       # Main panels (semi-transparent dark blue)
    bg_card: str = "rgba(30, 41, 59, 0.55)"        # Cards/Groups
    bg_input: str = "rgba(15, 23, 42, 0.6)"        # Inputs (slightly darker for contrast)
    bg_hover: str = "rgba(51, 65, 85, 0.6)"        # Hover state
    bg_pressed: str = "rgba(15, 23, 42, 0.8)"      # Pressed state
    
    # Frosty Borders
    border_subtle: str = "rgba(255, 255, 255, 0.08)"
    border_focus: str = "rgba(99, 102, 241, 0.8)"  # Indigo border for focus
    
    # Vibrant Accents
    accent: str = "#6366f1"                        # Indigo
    accent_hover: str = "#818cf8"                  # Light Indigo
    success: str = "#10b981"                       # Emerald
    warning: str = "#f59e0b"                       # Amber
    danger: str = "#ef4444"                        # Red
    
    # Text
    text_primary: str = "#f8fafc"
    text_secondary: str = "#cbd5e1"
    text_muted: str = "#94a3b8"


def get_stylesheet() -> str:
    """Returns the main application stylesheet utilizing Glassmorphism."""
    return f"""
    /* Global Settings */
    QWidget {{
        color: {Colors.text_primary};
        font-family: 'Segoe UI', -apple-system, sans-serif;
    }}
    
    QMainWindow {{
        background: {Colors.bg_window};
    }}

    /* Panels and Cards (Glass Effect) */
    QStackedWidget, QDialog {{
        background: transparent;
    }}
    
    QGroupBox {{
        background-color: {Colors.bg_card};
        border: 1px solid {Colors.border_subtle};
        border-radius: 12px;
        margin-top: 24px;
        padding-top: 16px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 4px 12px;
        background-color: {Colors.bg_panel};
        border: 1px solid {Colors.border_subtle};
        border-radius: 8px;
        color: {Colors.text_primary};
        font-weight: 600;
        left: 12px;
    }}

    /* Inputs (Slightly darker glass) */
    QLineEdit, QSpinBox, QComboBox {{
        background-color: {Colors.bg_input};
        border: 1px solid {Colors.border_subtle};
        border-radius: 8px;
        padding: 8px 12px;
        color: {Colors.text_primary};
        selection-background-color: {Colors.accent};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid {Colors.border_focus};
        background-color: {Colors.bg_card};
    }}
    
    /* Dropdown Menus */
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {Colors.bg_card};
        border: 1px solid {Colors.border_subtle};
        border-radius: 8px;
        selection-background-color: {Colors.accent};
        outline: none;
    }}

    /* Buttons (Vibrant & Interactive) */
    QPushButton {{
        background-color: {Colors.bg_card};
        border: 1px solid {Colors.border_subtle};
        border-radius: 8px;
        padding: 8px 16px;
        color: {Colors.text_primary};
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {Colors.bg_hover};
        border: 1px solid rgba(255, 255, 255, 0.2);
    }}
    QPushButton:pressed {{
        background-color: {Colors.bg_pressed};
    }}
    
    /* Primary Accent Button */
    QPushButton#primaryButton {{
        background-color: {Colors.accent};
        border: none;
        color: white;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {Colors.accent_hover};
    }}
    QPushButton#primaryButton:pressed {{
        background-color: #4f46e5;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {Colors.bg_hover};
        min-height: 20px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {Colors.text_muted};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* Tables/Lists (Translucent Rows) */
    QTableWidget, QListView {{
        background-color: {Colors.bg_card};
        border: 1px solid {Colors.border_subtle};
        border-radius: 12px;
        gridline-color: {Colors.border_subtle};
        outline: none;
    }}
    QHeaderView::section {{
        background-color: {Colors.bg_panel};
        color: {Colors.text_muted};
        padding: 8px;
        border: none;
        border-bottom: 1px solid {Colors.border_subtle};
        font-weight: bold;
        text-transform: uppercase;
        font-size: 11px;
    }}
    QTableWidget::item {{
        padding: 8px;
        border-bottom: 1px solid {Colors.border_subtle};
    }}
    QTableWidget::item:selected {{
        background-color: rgba(99, 102, 241, 0.3); /* Translucent Indigo */
        color: white;
    }}

    /* Progress Bar */
    QProgressBar {{
        background-color: {Colors.bg_input};
        border: 1px solid {Colors.border_subtle};
        border-radius: 10px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Colors.accent}, stop:1 #818cf8);
        border-radius: 9px;
    }}
    
    /* Menu Bar */
    QMenuBar {{
        background-color: {Colors.bg_panel};
        color: {Colors.text_primary};
        border-bottom: 1px solid {Colors.border_subtle};
    }}
    QMenuBar::item:selected {{
        background-color: {Colors.bg_hover};
        border-radius: 4px;
    }}
    QMenu {{
        background-color: {Colors.bg_card};
        border: 1px solid {Colors.border_subtle};
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background-color: {Colors.accent};
    }}
    
    /* Status Bar */
    QStatusBar {{
        background-color: {Colors.bg_panel};
        color: {Colors.text_muted};
        border-top: 1px solid {Colors.border_subtle};
    }}
    """
