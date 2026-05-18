import sys


def main():
    from notispf.app import App
    if len(sys.argv) < 2:
        print("Usage: notispf <file>")
        sys.exit(1)
    app = App(sys.argv[1])
    app.run()


def main_qt():
    from notispf.app_qt import AppQt
    from PyQt6.QtWidgets import QApplication, QFileDialog

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
