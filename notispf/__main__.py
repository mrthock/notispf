import sys
from notispf.app import App


def main():
    if len(sys.argv) < 2:
        print("Usage: notispf <file>")
        sys.exit(1)
    app = App(sys.argv[1])
    app.run()


def main_qt():
    try:
        from notispf.app_qt import AppQt
        from PyQt6.QtWidgets import QApplication, QFileDialog
    except ImportError:
        print("PyQt6 is required: pip install notispf[qt]")
        sys.exit(1)

    if len(sys.argv) >= 2:
        filepath = sys.argv[1]
    else:
        qt_app = QApplication(sys.argv)
        filepath, _ = QFileDialog.getOpenFileName(None, "Open file — notispf")
        if not filepath:
            sys.exit(0)

    app = AppQt(filepath)
    app.run()


if __name__ == "__main__":
    main()
