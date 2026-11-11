from __future__ import annotations

import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QStandardPaths, QtMsgType, qInstallMessageHandler
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout


LOGGER_NAME = "kege_station"
_logger = logging.getLogger(LOGGER_NAME)
_log_dir: Path | None = None
_marker_path: Path | None = None
_native_log_handle = None


def logger() -> logging.Logger:
    return _logger


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_logging() -> Path:
    """Configure persistent logs and return the log directory."""
    global _log_dir, _native_log_handle
    root_override = os.environ.get("KEGE_DATA_DIR")
    root = Path(root_override) if root_override else Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    )
    _log_dir = root / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)

    if not _logger.handlers:
        handler = RotatingFileHandler(
            _log_dir / "kege_station.log",
            maxBytes=2_000_000,
            backupCount=4,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
        _logger.propagate = False

    try:
        _native_log_handle = (_log_dir / "native_crash.log").open("a", encoding="utf-8")
        faulthandler.enable(file=_native_log_handle, all_threads=True)
    except Exception:
        _logger.exception("Не удалось включить faulthandler")

    _logger.info(
        "Запуск приложения; Python=%s; ОС=%s; экранов=%s",
        sys.version.replace("\n", " "),
        platform.platform(),
        len(QGuiApplication.screens()),
    )
    return _log_dir


class CrashDialog(QDialog):
    def __init__(self, title: str, summary: str, details: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 500)
        layout = QVBoxLayout(self)
        heading = QLabel(summary)
        heading.setWordWrap(True)
        heading.setStyleSheet("font-size:16px;font-weight:600;color:#991b1b")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Скопируйте отчёт и передайте разработчику. Подробный журнал сохранён на компьютере."))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(details)
        layout.addWidget(self.details, 1)
        buttons = QHBoxLayout()
        copy_button = QPushButton("Скопировать отчёт")
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(details))
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(copy_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)


def _report_text(exc_type, exc_value, exc_traceback) -> str:
    trace = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    return (
        f"Время UTC: {_utc_now()}\n"
        f"Версия Python: {sys.version}\n"
        f"ОС: {platform.platform()}\n\n"
        f"{trace}"
    )


def report_exception(exc_type, exc_value, exc_traceback, *, title: str = "Авария тренажёра") -> None:
    details = _report_text(exc_type, exc_value, exc_traceback)
    _logger.critical("Необработанное исключение\n%s", details)
    try:
        app = QApplication.instance()
        if app is not None:
            CrashDialog(title, "Тренажёр столкнулся с ошибкой.", details).exec()
    except Exception:
        _logger.exception("Не удалось показать окно аварии")


def install_exception_hooks() -> None:
    sys.excepthook = report_exception

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        report_exception(args.exc_type, args.exc_value, args.exc_traceback, title="Ошибка фоновой операции")

    threading.excepthook = thread_hook

    def qt_message_handler(message_type: QtMsgType, context, message: str) -> None:
        level = logging.WARNING
        if message_type == QtMsgType.QtCriticalMsg:
            level = logging.ERROR
        elif message_type == QtMsgType.QtFatalMsg:
            level = logging.CRITICAL
        _logger.log(level, "Qt: %s", message)

    qInstallMessageHandler(qt_message_handler)


def begin_session() -> bool:
    """Create a session marker. Returns True if the previous session was unclean."""
    global _marker_path
    if _log_dir is None:
        raise RuntimeError("Logging is not configured")
    _marker_path = _log_dir / "running.session"
    previous_unclean = _marker_path.exists()
    _marker_path.write_text(f"pid={os.getpid()}\nstarted={_utc_now()}\n", encoding="utf-8")
    if previous_unclean:
        _logger.warning("Обнаружено аварийное завершение предыдущего сеанса")
    return previous_unclean


def end_session() -> None:
    if _marker_path is not None:
        _marker_path.unlink(missing_ok=True)
    _logger.info("Приложение завершено штатно")


def show_previous_crash_notice(parent=None) -> None:
    if _log_dir is None:
        return
    log_path = _log_dir / "kege_station.log"
    message = QMessageBox(parent)
    message.setIcon(QMessageBox.Icon.Warning)
    message.setWindowTitle("Предыдущий запуск завершился аварийно")
    message.setText("В прошлый раз тренажёр закрылся без штатного завершения.")
    message.setInformativeText("Журнал сохранён. Если проблема повторится, отправьте разработчику файл журнала.")
    message.setDetailedText(f"Журнал: {log_path}\nНативный журнал: {_log_dir / 'native_crash.log'}")
    message.exec()

