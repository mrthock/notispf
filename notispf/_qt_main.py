import sys
import traceback

def _main():
    try:
        from notispf.__main__ import main_qt
        main_qt()
    except Exception:
        err = traceback.format_exc()
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "notispf startup error", err)
        except Exception:
            pass

if __name__ == "__main__":
    _main()
