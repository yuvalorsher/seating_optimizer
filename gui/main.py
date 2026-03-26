import sys
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Seating Optimizer")
    app.setOrganizationName("SeatingOptimizer")
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
