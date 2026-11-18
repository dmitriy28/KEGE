from __future__ import annotations

import sys

from PyQt6.QtGui import QFont, QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication

from kege_app.main_window import MainWindow
from kege_app.theme import APP_QSS
from kege_app.resources import resource_path
from kege_app.crash_reporting import (
    begin_session,
    configure_logging,
    end_session,
    install_exception_hooks,
    logger,
    report_exception,
    show_previous_crash_notice,
)


def main() -> int:
    if sys.platform.startswith("linux"):
        QGuiApplication.setDesktopFileName("kege-station")  # связывает окно с .desktop-файлом (Wayland)
    app = QApplication(sys.argv)
    app.setApplicationName("KEGE Station")
    app.setOrganizationName("KEGE Training")
    app.setWindowIcon(QIcon(str(resource_path("assets", "app_icon.png"))))
    font = QFont("Segoe UI", 10)
    font.setFamilies(["Segoe UI", "Noto Sans", "Ubuntu", "DejaVu Sans", "Arial"])
    app.setFont(font)
    app.setStyleSheet(APP_QSS)
    configure_logging()
    install_exception_hooks()
    previous_unclean = begin_session()
    clean_exit = False
    try:
        window = MainWindow()
        window.show()
        if previous_unclean:
            show_previous_crash_notice(window)
        app.applicationStateChanged.connect(lambda state: logger().info("Состояние приложения: %s", state.name))
        result = app.exec()
        clean_exit = True
        return result
    except BaseException:
        report_exception(*sys.exc_info())
        return 1
    finally:
        if clean_exit:
            end_session()


if __name__ == "__main__":
    raise SystemExit(main())

