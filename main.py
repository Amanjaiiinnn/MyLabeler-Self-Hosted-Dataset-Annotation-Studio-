"""
MyLabeler — self-hosted YOLO annotation, audit and dataset-generation studio.

Run:
    python main.py
"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.theme import ThemeManager
from ui.main_window import MainWindow


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("MyLabeler")
    app.setStyle("Fusion")

    ThemeManager.instance().apply()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
