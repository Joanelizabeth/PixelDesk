"""Pixel Desk entry point.

    python main.py             start (or bring the running instance forward)
    python main.py --window    force normal window mode for this session
    python main.py --verbose   debug logging
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="PixelDesk")
    parser.add_argument("--window", action="store_true", help="use normal window mode for this session")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args, _qt_args = parser.parse_known_args(argv)

    from app.logging_setup import setup_logging

    setup_logging(args.verbose)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.config import APP_DISPLAY_NAME, APP_NAME, APP_VERSION
    from app.single_instance import SingleInstance
    from ui.pixel_art import app_icon

    if sys.platform == "win32":
        try:  # taskbar grouping/icon for the python.exe case
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PixelDesk.App")
        except Exception:
            pass

    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationDisplayName(APP_DISPLAY_NAME)
    qapp.setApplicationVersion(APP_VERSION)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setWindowIcon(app_icon())
    qapp.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    instance = SingleInstance()
    if instance.already_running():
        return 0
    instance.listen()

    from app.application import PixelDeskApplication

    app = PixelDeskApplication(qapp, single_instance=instance)
    try:
        ctx = app.start()
    except Exception as exc:  # noqa: BLE001 - last-resort error dialog
        import logging

        logging.getLogger("pixeldesk").exception("Startup failed")
        app.shutdown()
        QMessageBox.critical(None, APP_DISPLAY_NAME, f"Pixel Desk could not start:\n\n{exc}\n\n"
                                                     "Details are in the log file in the data folder.")
        return 1
    if args.window and ctx.settings["display_mode"] != "window":
        ctx.settings.set_transient("display_mode", "window")
        app.shell.rebuild()
    # Ctrl+C in a console quits cleanly (saving pending data).
    import signal

    from PySide6.QtCore import QTimer

    signal.signal(signal.SIGINT, lambda *_: qapp.quit())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)  # lets Python handle signals
    keepalive.start(500)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
