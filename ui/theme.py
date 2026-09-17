"""
ui/theme.py
The single source of truth for every colour, size and spacing value in the app.

Nothing else should contain a hex code. Widgets pick up their look from the
application-wide stylesheet built here, selected on objectName or on a dynamic
property, e.g.:

    btn.setProperty("variant", "primary")
    panel.setObjectName("Card")

Design rules encoded below:
  * Chrome is near-neutral, biased slightly cool. Images are the brightest
    thing on screen; class colours are the most saturated.
  * ACCENT means "you can interact with this". Nothing decorative uses it.
  * WARN means "this needs a look". DANGER means "this destroys something".
    OK means "verified". None of them are ever used as decoration.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication


# ══════════════════════════════════════════════════════════════ tokens ══

class Tokens:
    # -- surfaces (cool-biased neutrals) --------------------------------
    INK_950 = "#08090C"     # deepest: canvas void, image letterbox
    INK_900 = "#0B0D11"     # app base / work surface
    INK_850 = "#101318"     # panels, rails, bars
    INK_800 = "#14171D"     # inputs
    INK_750 = "#191D24"     # hover on panel
    INK_700 = "#1F242C"     # raised controls
    INK_650 = "#262C35"     # hover on control

    LINE = "#232830"        # hairline
    LINE_2 = "#2E3540"      # control border
    LINE_3 = "#3A424F"      # emphasised border

    # -- text -----------------------------------------------------------
    TX_1 = "#E8EAEF"        # primary
    TX_2 = "#98A0AD"        # secondary
    TX_3 = "#646C7A"        # muted / captions
    TX_4 = "#474E5A"        # disabled, decorative labels

    # -- meaning: one hue, one job ---------------------------------------
    ACCENT = "#4C8DFF"
    ACCENT_HOVER = "#6BA0FF"
    ACCENT_DIM = "#2C5AA8"
    ACCENT_WASH = "#16233A"     # solid equivalent of accent @ 13% on INK_900
    ON_ACCENT = "#04070D"

    OK = "#3FB950"
    OK_WASH = "#12251A"
    WARN = "#E3A008"
    WARN_WASH = "#2A2312"
    WARN_TEXT = "#F5D28A"
    DANGER = "#F0524E"
    DANGER_HOVER = "#FF6B67"
    DANGER_TEXT = "#FF8A87"
    DANGER_WASH = "#2A1618"

    # -- shape ------------------------------------------------------------
    R_SM = 5
    R = 7
    R_LG = 10

    # -- spacing (4px base) ------------------------------------------------
    S1, S2, S3, S4, S5, S6, S7 = 4, 8, 12, 16, 24, 32, 48

    # -- control metrics ---------------------------------------------------
    CTRL_H = 30
    CTRL_H_SM = 26
    RAIL_W = 248
    RAIL_W_COLLAPSED = 56
    TOOLBAR_H = 46

    # -- type ---------------------------------------------------------------
    FONT_UI = "IBM Plex Sans"
    FONT_UI_FALLBACK = "Segoe UI"
    FONT_MONO = "IBM Plex Mono"
    FONT_MONO_FALLBACK = "Consolas"

    FS_DISPLAY = 20
    FS_TITLE = 15
    FS_BODY = 13
    FS_CONTROL = 12
    FS_SMALL = 11
    FS_MICRO = 10

    # -- class palette (unchanged: existing label files depend on the order) -
    CLASS_COLORS = [
        "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
        "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
        "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000",
        "#a78bfa", "#38bdf8", "#4ade80", "#fb923c", "#f43f5e",
    ]


T = Tokens


def class_color(class_id: int) -> str:
    return T.CLASS_COLORS[class_id % len(T.CLASS_COLORS)]


def ui_font(size: int = T.FS_BODY, weight: int = QFont.Normal) -> QFont:
    f = QFont(T.FONT_UI, size, weight)
    f.setStyleHint(QFont.SansSerif)
    if not _has_family(T.FONT_UI):
        f.setFamily(T.FONT_UI_FALLBACK)
    return f


def mono_font(size: int = T.FS_SMALL, weight: int = QFont.Normal) -> QFont:
    f = QFont(T.FONT_MONO, size, weight)
    f.setStyleHint(QFont.Monospace)
    if not _has_family(T.FONT_MONO):
        f.setFamily(T.FONT_MONO_FALLBACK)
    f.setFixedPitch(True)
    return f


_family_cache: dict = {}


def _has_family(name: str) -> bool:
    if name not in _family_cache:
        _family_cache[name] = name in QFontDatabase.families()
    return _family_cache[name]


def alpha(hex_color: str, a: float) -> str:
    """rgba() string for use in a stylesheet."""
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a:.3f})"


# ══════════════════════════════════════════════════════ global stylesheet ══

def build_stylesheet() -> str:
    return f"""
/* ─────────────────────────────── base ─────────────────────────────── */
QWidget {{
    background: transparent;
    color: {T.TX_1};
    font-family: "{T.FONT_UI}", "{T.FONT_UI_FALLBACK}", sans-serif;
    font-size: {T.FS_BODY}px;
}}
QMainWindow, QDialog {{ background: {T.INK_900}; }}
QToolTip {{
    background: {T.INK_700}; color: {T.TX_1};
    border: 1px solid {T.LINE_2}; border-radius: {T.R_SM}px;
    padding: 5px 8px; font-size: {T.FS_CONTROL}px;
}}

/* ─────────────────────────── structural ───────────────────────────── */
QWidget#Page      {{ background: {T.INK_900}; }}
QWidget#Rail      {{ background: {T.INK_850}; border-right: 1px solid {T.LINE}; }}
QWidget#Toolbar   {{ background: {T.INK_850}; border-bottom: 1px solid {T.LINE}; }}
QWidget#StatusBar {{ background: {T.INK_850}; border-top: 1px solid {T.LINE}; }}
QWidget#Panel     {{ background: {T.INK_850}; border-left: 1px solid {T.LINE}; }}
QWidget#Canvas    {{ background: {T.INK_950}; }}

QFrame#Card {{
    background: {T.INK_850};
    border: 1px solid {T.LINE};
    border-radius: {T.R}px;
}}
QFrame#Divider {{ background: {T.LINE}; border: none; max-height: 1px; }}
QFrame#VDivider {{ background: {T.LINE_2}; border: none; max-width: 1px; }}

/* ───────────────────────────── labels ─────────────────────────────── */
QLabel {{ background: transparent; }}
QLabel#Display  {{ font-size: {T.FS_DISPLAY}px; font-weight: 600; color: {T.TX_1}; }}
QLabel#Title    {{ font-size: {T.FS_TITLE}px;   font-weight: 600; color: {T.TX_1}; }}
QLabel#Body     {{ font-size: {T.FS_BODY}px;    color: {T.TX_2}; }}
QLabel#Muted    {{ font-size: {T.FS_CONTROL}px; color: {T.TX_3}; }}
QLabel#Caption  {{ font-size: {T.FS_SMALL}px;   color: {T.TX_3};
                   font-family: "{T.FONT_MONO}", "{T.FONT_MONO_FALLBACK}", monospace; }}
QLabel#SectionLabel {{
    font-family: "{T.FONT_MONO}", "{T.FONT_MONO_FALLBACK}", monospace;
    font-size: {T.FS_MICRO}px; font-weight: 500;
    color: {T.TX_3}; letter-spacing: 1.4px;
}}
QLabel#GroupLabel {{
    font-family: "{T.FONT_MONO}", "{T.FONT_MONO_FALLBACK}", monospace;
    font-size: {T.FS_MICRO}px; color: {T.TX_4}; letter-spacing: 1.6px;
    padding: 12px 16px 6px;
}}
QLabel#Mono {{
    font-family: "{T.FONT_MONO}", "{T.FONT_MONO_FALLBACK}", monospace;
    font-size: {T.FS_SMALL}px; color: {T.TX_2};
}}
QLabel[tone="warn"]   {{ color: {T.WARN}; }}
QLabel[tone="danger"] {{ color: {T.DANGER_TEXT}; }}
QLabel[tone="ok"]     {{ color: {T.OK}; }}
QLabel[tone="accent"] {{ color: {T.ACCENT}; }}

/* ──────────────────────────── buttons ─────────────────────────────── */
QPushButton {{
    background: {T.INK_700};
    color: {T.TX_1};
    border: 1px solid {T.LINE_2};
    border-radius: {T.R_SM}px;
    padding: 0 12px;
    min-height: {T.CTRL_H}px;
    font-size: {T.FS_CONTROL}px;
    font-weight: 500;
}}
QPushButton:hover    {{ background: {T.INK_650}; border-color: {T.LINE_3}; }}
QPushButton:pressed  {{ background: {T.INK_750}; }}
QPushButton:disabled {{ background: {T.INK_800}; color: {T.TX_4}; border-color: {T.LINE}; }}
QPushButton:focus    {{ border-color: {T.ACCENT}; }}

QPushButton[variant="primary"] {{
    background: {T.ACCENT}; color: {T.ON_ACCENT};
    border-color: {T.ACCENT}; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background: {T.ACCENT_HOVER}; border-color: {T.ACCENT_HOVER};
}}
QPushButton[variant="primary"]:disabled {{
    background: {T.INK_800}; color: {T.TX_4}; border-color: {T.LINE};
}}

QPushButton[variant="danger"] {{
    background: transparent; color: {T.DANGER_TEXT};
    border-color: {alpha(T.DANGER, 0.42)};
}}
QPushButton[variant="danger"]:hover {{
    background: {T.DANGER_WASH}; border-color: {T.DANGER};
}}
QPushButton[variant="danger"]:disabled {{
    color: {T.TX_4}; border-color: {T.LINE}; background: transparent;
}}

QPushButton[variant="quiet"] {{
    background: transparent; border-color: transparent; color: {T.TX_2};
}}
QPushButton[variant="quiet"]:hover {{ background: {T.INK_750}; color: {T.TX_1}; }}
QPushButton[variant="quiet"]:disabled {{ color: {T.TX_4}; background: transparent; }}

QPushButton[size="sm"] {{ min-height: {T.CTRL_H_SM}px; padding: 0 9px; }}

/* segmented control: checkable buttons in a row */
QPushButton[variant="segment"] {{
    background: transparent; border: none; color: {T.TX_2};
    border-radius: 4px; padding: 0 11px; min-height: {T.CTRL_H_SM - 4}px;
}}
QPushButton[variant="segment"]:hover   {{ color: {T.TX_1}; }}
QPushButton[variant="segment"]:checked {{ background: {T.INK_650}; color: {T.TX_1}; }}
QWidget#Segment {{
    background: {T.INK_800}; border: 1px solid {T.LINE_2};
    border-radius: {T.R_SM}px;
}}

/* underlined tab, as used for split and Classes/Tags tab bars */
QPushButton[variant="tab"] {{
    background: transparent; border: none; color: {T.TX_3};
    border-bottom: 2px solid transparent;
    padding: 0 14px; min-height: 36px;
    font-size: {T.FS_CONTROL}px; font-weight: 500;
}}
QPushButton[variant="tab"]:hover   {{ color: {T.TX_1}; }}
QPushButton[variant="tab"]:checked {{
    color: {T.TX_1}; border-bottom-color: {T.ACCENT}; font-weight: 600;
}}
QPushButton[variant="tab"]:disabled {{ color: {T.TX_4}; }}

/* filter chip */
QPushButton[variant="chip"] {{
    background: {T.INK_750}; border: 1px solid {T.LINE_2}; color: {T.TX_2};
    border-radius: 13px; padding: 0 12px; min-height: 25px;
    font-size: {T.FS_CONTROL}px; font-weight: 500;
}}
QPushButton[variant="chip"]:hover   {{ color: {T.TX_1}; border-color: {T.LINE_3}; }}
QPushButton[variant="chip"]:checked {{
    background: {T.ACCENT_WASH}; border-color: {T.ACCENT_DIM}; color: #BFD6FF;
}}

/* nav item in the sidebar */
QPushButton[variant="nav"] {{
    background: transparent; border: none; color: {T.TX_2};
    border-radius: {T.R_SM}px; padding: 0 12px; min-height: 32px;
    font-size: {T.FS_BODY}px; font-weight: 450; text-align: left;
}}
QPushButton[variant="nav"]:hover   {{ background: {T.INK_750}; color: {T.TX_1}; }}
QPushButton[variant="nav"]:checked {{
    background: {T.ACCENT_WASH}; color: #FFFFFF; font-weight: 600;
}}

/* ───────────────────────────── inputs ─────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {T.INK_800};
    border: 1px solid {T.LINE_2};
    border-radius: {T.R_SM}px;
    padding: 0 10px;
    min-height: {T.CTRL_H}px;
    color: {T.TX_1};
    font-size: {T.FS_CONTROL}px;
    selection-background-color: {T.ACCENT_DIM};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QPlainTextEdit:focus {{ border-color: {T.ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {T.INK_850}; color: {T.TX_4}; border-color: {T.LINE};
}}
QLineEdit::placeholder {{ color: {T.TX_3}; }}

QPlainTextEdit, QTextEdit {{
    font-family: "{T.FONT_MONO}", "{T.FONT_MONO_FALLBACK}", monospace;
    font-size: {T.FS_SMALL}px; color: {T.TX_2};
    background: {T.INK_950}; border-color: {T.LINE};
    padding: 10px;
}}

QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {T.TX_3}; margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {T.INK_800}; color: {T.TX_1};
    border: 1px solid {T.LINE_2}; border-radius: {T.R_SM}px;
    selection-background-color: {T.ACCENT_WASH}; selection-color: #FFFFFF;
    outline: none; padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ color: {T.TX_2}; font-size: {T.FS_CONTROL}px; spacing: 8px; background: transparent; }}
QCheckBox:disabled {{ color: {T.TX_4}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1.5px solid {T.LINE_3}; background: {T.INK_800};
}}
QCheckBox::indicator:hover {{ border-color: {T.ACCENT_DIM}; }}
QCheckBox::indicator:checked {{ background: {T.ACCENT}; border-color: {T.ACCENT}; }}
QCheckBox::indicator:disabled {{ border-color: {T.LINE}; background: {T.INK_850}; }}

QRadioButton {{ color: {T.TX_2}; font-size: {T.FS_CONTROL}px; spacing: 8px; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 7px;
    border: 1.5px solid {T.LINE_3}; background: {T.INK_800};
}}
QRadioButton::indicator:checked {{ background: {T.ACCENT}; border-color: {T.ACCENT}; }}

QGroupBox {{
    border: 1px solid {T.LINE}; border-radius: {T.R}px;
    margin-top: 18px; padding: 12px; background: {T.INK_850};
    font-size: {T.FS_CONTROL}px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 4px;
    color: {T.TX_3}; font-family: "{T.FONT_MONO}", monospace;
    font-size: {T.FS_MICRO}px; letter-spacing: 1.4px;
}}

/* ───────────────────────── lists & tables ─────────────────────────── */
QListWidget, QTreeWidget, QTableWidget {{
    background: transparent; border: none; outline: none;
    color: {T.TX_1}; font-size: {T.FS_CONTROL}px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: {T.R_SM}px; color: {T.TX_2}; }}
QListWidget::item:hover    {{ background: {T.INK_750}; color: {T.TX_1}; }}
QListWidget::item:selected {{ background: {T.INK_700}; color: {T.TX_1}; }}

QTableWidget {{ gridline-color: transparent; }}
QTableWidget::item {{ padding: 8px 12px; border-bottom: 1px solid {T.LINE}; }}
QTableWidget::item:selected {{ background: {T.ACCENT_WASH}; color: #FFFFFF; }}
QHeaderView::section {{
    background: {T.INK_850}; color: {T.TX_3};
    font-family: "{T.FONT_MONO}", "{T.FONT_MONO_FALLBACK}", monospace;
    font-size: {T.FS_MICRO}px; font-weight: 500; letter-spacing: 1.2px;
    padding: 8px 12px; border: none; border-bottom: 1px solid {T.LINE_2};
}}
QHeaderView {{ background: transparent; }}
QTableCornerButton::section {{ background: {T.INK_850}; border: none; }}

/* ───────────────────────────── progress ───────────────────────────── */
QProgressBar {{
    background: {T.INK_800}; border: 1px solid {T.LINE_2};
    border-radius: {T.R_SM}px; text-align: center;
    color: {T.TX_1}; font-size: {T.FS_SMALL}px; max-height: 20px;
}}
QProgressBar::chunk {{ background: {T.ACCENT}; border-radius: 4px; }}

/* ───────────────────────────── scrollbars ─────────────────────────── */
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {T.LINE_2}; border-radius: 5px; min-height: 32px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {T.LINE_3}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {T.LINE_2}; border-radius: 5px; min-width: 32px; margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {T.LINE_3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ─────────────────────────── menus & misc ─────────────────────────── */
QMenu {{
    background: {T.INK_800}; border: 1px solid {T.LINE_2};
    border-radius: {T.R}px; padding: 5px;
}}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; color: {T.TX_2}; }}
QMenu::item:selected {{ background: {T.ACCENT_WASH}; color: #FFFFFF; }}
QMenu::separator {{ height: 1px; background: {T.LINE}; margin: 5px 8px; }}

QSplitter::handle {{ background: {T.LINE}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

QStatusBar {{ background: {T.INK_850}; color: {T.TX_3}; border-top: 1px solid {T.LINE}; }}
QStatusBar::item {{ border: none; }}

QMessageBox {{ background: {T.INK_850}; }}
QMessageBox QLabel {{ color: {T.TX_1}; font-size: {T.FS_BODY}px; }}
QDialogButtonBox QPushButton {{ min-width: 78px; }}
"""


# ═══════════════════════════════════════════════════════════ manager ══

class ThemeManager(QObject):
    themeChanged = Signal(str)
    _instance = None

    def __init__(self):
        super().__init__()
        self.current_theme = "dark"

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def apply(self):
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet())
            app.setFont(ui_font())
        self.themeChanged.emit(self.current_theme)

    # Kept so existing call sites keep working.
    def set_theme(self, theme_name: str = "dark"):
        self.current_theme = "dark"
        self.apply()

    def toggle(self):
        """
        Single-theme by design: a light UI biases how you judge image exposure
        and washes out the class colours, so the studio stays dark.
        """
        self.apply()
