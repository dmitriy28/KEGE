from __future__ import annotations

import os
import logging
import secrets
from pathlib import Path

from PyQt6.QtCore import QEvent, QStandardPaths, Qt
from PyQt6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QStackedWidget

from .expert_ui import ExpertLoginDialog, ExpertWindow
from .package_io import choose_variant, control_sum, export_result, validate_package, verify_activation
from .storage import Storage
from .student_ui import (
    ActivationPage,
    ExamPage,
    ExamSession,
    FinishPage,
    InstructionsPage,
    LandingPage,
    OverviewPage,
    ParticipantConfirmationPage,
    RegistrationPage,
    utcnow,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Тренировочная станция КЕГЭ")
        self.setMinimumSize(1180, 760)
        self.showMaximized()
        data_override = os.environ.get("KEGE_DATA_DIR")
        data_root = Path(data_override) if data_override else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        self.storage = Storage(data_root)
        self.session: ExamSession | None = None
        self.current_result: dict | None = None
        self.expert_window: ExpertWindow | None = None
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.landing = LandingPage()
        self.overview = OverviewPage()
        self.registration = RegistrationPage()
        self.instructions = InstructionsPage()
        self.confirmation = ParticipantConfirmationPage()
        self.activation = ActivationPage()
        self.exam_page = ExamPage(self.storage.work_dir, self.storage.cache_dir)
        self.finish_page = FinishPage()
        for page in (self.landing, self.overview, self.registration, self.instructions, self.confirmation, self.activation, self.exam_page, self.finish_page):
            self.stack.addWidget(page)
        self._connect()
        self.stack.setCurrentWidget(self.landing)

    def _connect(self) -> None:
        self.landing.begin_requested.connect(self._begin)
        self.landing.expert_requested.connect(self._open_expert)
        self.overview.next_requested.connect(lambda: self.stack.setCurrentWidget(self.registration))
        self.overview.back_requested.connect(lambda: self.stack.setCurrentWidget(self.landing))
        self.registration.next_requested.connect(self._registration_done)
        self.registration.back_requested.connect(lambda: self.stack.setCurrentWidget(self.overview))
        self.instructions.finished.connect(self._instructions_done)
        self.instructions.back_requested.connect(lambda: self.stack.setCurrentWidget(self.registration))
        self.confirmation.edit_requested.connect(lambda: self.stack.setCurrentWidget(self.registration))
        self.confirmation.confirmed.connect(self._registration_confirmed)
        self.activation.start_requested.connect(self._activate)
        self.activation.back_requested.connect(lambda: self.stack.setCurrentWidget(self.confirmation))
        self.exam_page.finish_requested.connect(self._finish_exam)
        self.finish_page.new_exam_requested.connect(self._reset)
        self.finish_page.export_requested.connect(self._export_current_result)

    def closeEvent(self, event) -> None:
        log = logging.getLogger("kege_station")
        log.info("Получен запрос на закрытие главного окна")
        if self.session and self.session.variant and self.stack.currentWidget() is self.exam_page:
            message = "Сейчас идёт экзамен. Несохранённые ответы будут потеряны. Вы уверены, что хотите закрыть программу?"
        else:
            message = "Вы уверены, что хотите закрыть программу?"
        answer = QMessageBox.question(
            self,
            "Закрытие программы",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            log.info("Пользователь подтвердил закрытие")
            event.accept()
        else:
            log.info("Пользователь отменил закрытие")
            event.ignore()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            state = self.windowState()
            logging.getLogger("kege_station").info(
                "Состояние главного окна изменено: minimized=%s maximized=%s active=%s",
                bool(state & Qt.WindowState.WindowMinimized),
                bool(state & Qt.WindowState.WindowMaximized),
                self.isActiveWindow(),
            )

    def _active_exam(self):
        row = self.storage.active_exam_row()
        if not row:
            return None, None
        try:
            return validate_package(row["package_path"]), row
        except Exception as exc:
            QMessageBox.critical(self, "Пакет повреждён", str(exc))
            return None, None

    def _begin(self) -> None:
        exam, row = self._active_exam()
        if not exam or not row:
            QMessageBox.information(self, "Нет активного экзамена", "Войдите в режим эксперта, импортируйте пакет .kege и сделайте его активным.")
            return
        self.session = ExamSession(exam=exam, package_path=row["package_path"])
        self.stack.setCurrentWidget(self.overview)

    def _registration_done(self, registration_no: str) -> None:
        if not self.session:
            return
        self.session.registration_no = registration_no
        if not self.session.kim_no:
            self.session.kim_no = f"0250{secrets.randbelow(1_000_000):06d}"
        self.instructions.reset()
        self.stack.setCurrentWidget(self.instructions)

    def _instructions_done(self) -> None:
        if not self.session:
            return
        self.confirmation.configure(self.session.registration_no, self.session.kim_no)
        self.stack.setCurrentWidget(self.confirmation)

    def _registration_confirmed(self) -> None:
        if not self.session:
            return
        self.activation.configure(self.session.registration_no, self.session.kim_no)
        self.stack.setCurrentWidget(self.activation)

    def _activate(self, code: str) -> None:
        if not self.session:
            return
        if not verify_activation(code, self.session.exam):
            QMessageBox.warning(self, "Неверный код", "Код активации экзамена указан неверно.")
            return
        self.session.variant = choose_variant(self.session.exam)
        self.session.started_at = utcnow()
        self.session.answers.clear()
        self.session.elapsed_seconds = 0
        self.exam_page.start(self.session)
        self.stack.setCurrentWidget(self.exam_page)

    def _finish_exam(self) -> None:
        if not self.session or not self.session.variant:
            return
        checksum = control_sum(
            self.session.exam.id,
            self.session.variant.id,
            self.session.registration_no,
            self.session.answers,
        )
        record = {
            "format": "kege-result",
            "format_version": 1,
            "exam_id": self.session.exam.id,
            "exam_title": self.session.exam.title,
            "variant_id": self.session.variant.id,
            "variant_name": self.session.variant.name,
            "registration_no": self.session.registration_no,
            "kim_no": self.session.kim_no,
            "started_at": self.session.started_at,
            "finished_at": utcnow(),
            "elapsed_seconds": self.session.elapsed_seconds,
            "checksum": checksum,
            "answers": dict(self.session.answers),
            "status": "finished",
        }
        result_id = self.storage.save_result(record)
        record["id"] = result_id
        self.session.result_id = result_id
        self.current_result = record
        self.finish_page.show_record(record, len(self.session.variant.tasks))
        self.stack.setCurrentWidget(self.finish_page)

    def _export_current_result(self, password: str) -> None:
        if not self.current_result:
            return
        if not self.storage.verify_expert_password(password):
            QMessageBox.warning(self, "Доступ запрещён", "Неверный пароль технического специалиста.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт файла ответов",
            f"КЕГЭ_{self.current_result['registration_no']}_{self.current_result['kim_no']}.kege-result",
            "Результат КЕГЭ (*.kege-result)",
        )
        if not path:
            return
        if not path.lower().endswith(".kege-result"):
            path += ".kege-result"
        export_result(path, self.current_result)
        QMessageBox.information(self, "Готово", "Файл ответов экспортирован.")

    def _open_expert(self) -> None:
        login = ExpertLoginDialog(self.storage, self)
        if login.exec() != ExpertLoginDialog.DialogCode.Accepted:
            return
        self.expert_window = ExpertWindow(self.storage, login.password_value, self)
        self.expert_window.show()

    def _reset(self) -> None:
        self.session = None
        self.current_result = None
        self.stack.setCurrentWidget(self.landing)
