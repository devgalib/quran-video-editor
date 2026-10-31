"""Desktop app (PySide6). Start with: python -m qve gui"""

import sys

STYLE = """
QWidget { font-size: 13px; }
QGroupBox { border: 1px solid #2a2f38; border-radius: 8px; margin-top: 16px; padding: 12px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #E3B85C; font-weight: 600; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QPlainTextEdit {
    background: #161a20; border: 1px solid #2a2f38; border-radius: 5px; padding: 4px 6px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #E3B85C; }
QPushButton { background: #232831; border: 1px solid #323946; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { border-color: #E3B85C; }
QPushButton:disabled { color: #5b626d; }
QPushButton#primary { background: #E3B85C; color: #17130a; border: none; font-weight: 600; padding: 7px 18px; }
QPushButton#primary:hover { background: #edc977; }
QPushButton#primary:disabled { background: #5d5340; color: #2a261c; }
QProgressBar { background: #161a20; border: 1px solid #2a2f38; border-radius: 6px; text-align: center;
    min-height: 20px; }
QProgressBar::chunk { background: #E3B85C; border-radius: 5px; }
QSlider::groove:horizontal { height: 4px; background: #2a2f38; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #E3B85C; border-radius: 2px; }
QSlider::handle:horizontal { background: #f2e2b8; width: 14px; margin: -6px 0; border-radius: 7px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { border: none; width: 18px; background: transparent; }
QAbstractSpinBox::up-arrow { width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-bottom: 5px solid #9aa3af; }
QAbstractSpinBox::down-arrow { width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid #9aa3af; }
QTabWidget::pane { border: none; }
QScrollArea { border: none; }
"""


def create_app(argv):
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    app = QApplication(argv)
    app.setApplicationName("Quran Video Editor")
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "#0f1216"), (QPalette.ColorRole.WindowText, "#e6e8eb"),
                        (QPalette.ColorRole.Base, "#161a20"), (QPalette.ColorRole.AlternateBase, "#1b2028"),
                        (QPalette.ColorRole.Text, "#e6e8eb"), (QPalette.ColorRole.Button, "#232831"),
                        (QPalette.ColorRole.ButtonText, "#e6e8eb"), (QPalette.ColorRole.Highlight, "#E3B85C"),
                        (QPalette.ColorRole.HighlightedText, "#17130a"), (QPalette.ColorRole.ToolTipBase, "#232831"),
                        (QPalette.ColorRole.ToolTipText, "#e6e8eb"), (QPalette.ColorRole.PlaceholderText, "#6b7380")):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    return app


def main():
    from .window import MainWindow

    app = create_app(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()
