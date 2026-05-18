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
    from PyQt6.QtWidgets import QApplication

    filepath = sys.argv[1] if len(sys.argv) >= 2 else "Untitled.txt"
    app = AppQt(filepath)
    app.run()


if __name__ == "__main__":
    main()
