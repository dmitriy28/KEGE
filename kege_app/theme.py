from __future__ import annotations


NAVY = "#213a66"
NAVY_DARK = "#162f59"
PALE = "#eaf1fc"
CYAN = "#28a8c7"
GREEN = "#11c889"
TEXT = "#10284f"
MUTED = "#7d8da7"


APP_QSS = r"""
* { font-family: "Segoe UI", "Arial"; font-size: 14px; color: #10284f; }
QMainWindow, QDialog, QWidget#Root { background: #eaf1fc; }
QToolTip { background: white; color: #10284f; border: 1px solid #9bb0ce; padding: 5px; }
QLabel#PageTitle { font-size: 32px; font-weight: 300; color: #0b1f3d; }
QLabel#HeroTitle { font-size: 38px; font-weight: 400; color: #0b1f3d; }
QLabel#Muted { color: #7d8da7; }
QLabel#Error { color: #c93e44; }
QFrame#Header { background: #213a66; border: none; }
QFrame#Card { background: white; border: 1px solid #d4dfef; border-radius: 3px; }
QFrame#SoftCard { background: #f5f8fd; border: 1px solid #d4dfef; border-radius: 4px; }
QPushButton { min-height: 38px; padding: 0 18px; border-radius: 3px; border: 1px solid #9cafca; background: white; color: #10284f; }
QPushButton:hover { background: #f3f7fc; border-color: #58759f; }
QPushButton:pressed { background: #e6eef8; }
QPushButton:disabled { color: #9aa7b9; border-color: #d6deea; background: #edf2f8; }
QPushButton#Primary { background: #11c889; border-color: #0cab77; color: #063d2a; font-weight: 600; letter-spacing: 1px; }
QPushButton#Primary:hover { background: #19d696; }
QPushButton#Secondary { background: #213a66; border-color: #162f59; color: white; font-weight: 600; }
QPushButton#Danger { background: #cd5e62; border-color: #b7494d; color: white; font-weight: 600; }
QPushButton#Link { background: transparent; border: none; color: #1978ae; text-decoration: underline; padding: 0 4px; }
QPushButton#TaskButton { min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; padding: 0; background: white; border: 1px solid transparent; font-weight: 600; }
QPushButton#TaskButton:hover { border-color: #6f8bad; }
QPushButton#TaskButton[answered="true"] { background: #edf4e6; border-color: #9cbf75; }
QPushButton#TaskButton[active="true"] { background: #213a66; color: white; border-color: #162f59; }
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QTableWidget { background: white; border: 1px solid #aebdd1; border-radius: 2px; padding: 7px; selection-background-color: #b9dded; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus { border: 2px solid #28a8c7; }
QLineEdit#RegistrationPart { font-size: 31px; letter-spacing: 4px; min-height: 54px; }
QLineEdit#Answer { font-size: 20px; min-height: 38px; padding: 4px 10px; }
QTabWidget::pane { border: 1px solid #c8d5e7; background: white; }
QTabBar::tab { background: #e2eaf5; border: 1px solid #c8d5e7; padding: 11px 18px; }
QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: 600; }
QHeaderView::section { background: #e7eef8; color: #10284f; padding: 8px; border: none; border-right: 1px solid #c8d5e7; border-bottom: 1px solid #c8d5e7; font-weight: 600; }
QTableWidget { gridline-color: #d9e2ef; padding: 0; }
QScrollBar:vertical { background: #edf2f8; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #9fb0c8; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: #d9e5f5; border: none; height: 4px; }
QProgressBar::chunk { background: #28a8c7; }
"""

