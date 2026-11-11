from __future__ import annotations

import html
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import Task
from .package_io import extract_member, export_result, reencrypt_package_keys, validate_package
from .storage import Storage
from .student_ui import ImageAsset, TaskHtmlLabel


class ExpertLoginDialog(QDialog):
    def __init__(self, storage: Storage, parent: QWidget | None = None):
        super().__init__(parent)
        self.storage = storage
        self.password_value = ""
        self.setWindowTitle("Режим эксперта")
        self.setModal(True)
        self.setFixedWidth(430)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Вход в режим эксперта</h2>"))
        layout.addWidget(QLabel("Управление экзаменационными пакетами и результатами защищено паролем."))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Пароль эксперта")
        self.password.returnPressed.connect(self._accept)
        layout.addWidget(self.password)
        self.error = QLabel()
        self.error.setObjectName("Error")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        value = self.password.text()
        if not self.storage.verify_expert_password(value):
            self.error.setText("Неверный пароль эксперта")
            return
        self.password_value = value
        self.accept()


class PackageImportWorker(QThread):
    imported = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, storage: Storage, path: str, password: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.storage = storage
        self.path = path
        self.password = password

    def run(self) -> None:
        try:
            self.imported.emit(self.storage.import_exam(self.path, self.password))
        except Exception as exc:
            self.failed.emit(str(exc))


class PackagePreviewDialog(QDialog):
    def __init__(self, package_path: str, password: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.package_path = package_path
        self.exam = validate_package(package_path, password)
        self._temporary = tempfile.TemporaryDirectory(prefix="kege_preview_")
        self.setWindowTitle(f"Предпросмотр — {self.exam.title}")
        self.resize(1260, 820)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        heading = QLabel(
            f"<h2>{html.escape(self.exam.title)}</h2>"
            f"<b>Предмет:</b> {html.escape(self.exam.subject)} &nbsp;&nbsp; "
            f"<b>Год:</b> {self.exam.year} &nbsp;&nbsp; "
            f"<b>Время:</b> {self.exam.duration_minutes} мин &nbsp;&nbsp; "
            f"<b>Вариантов:</b> {len(self.exam.variants)}"
        )
        heading.setWordWrap(True)
        root.addWidget(heading)

        variant_row = QHBoxLayout()
        variant_row.addWidget(QLabel("Вариант:"))
        self.variant_combo = QComboBox()
        for variant in self.exam.variants:
            self.variant_combo.addItem(f"{variant.name} ({len(variant.tasks)} заданий)")
        self.variant_combo.currentIndexChanged.connect(self._variant_changed)
        variant_row.addWidget(self.variant_combo, 1)
        root.addLayout(variant_row)

        splitter = QSplitter()
        self.task_list = QListWidget()
        self.task_list.setMaximumWidth(300)
        self.task_list.currentRowChanged.connect(self._show_task)
        splitter.addWidget(self.task_list)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_host = QWidget()
        self.content_layout = QVBoxLayout(self.scroll_host)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_host)
        splitter.addWidget(self.scroll)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._variant_changed(0)

    def _variant_changed(self, index: int) -> None:
        self.task_list.blockSignals(True)
        self.task_list.clear()
        if 0 <= index < len(self.exam.variants):
            for task in self.exam.variants[index].tasks:
                self.task_list.addItem(f"Задание {task.number}" + (f" — {task.title}" if task.title else ""))
        self.task_list.blockSignals(False)
        if self.task_list.count():
            self.task_list.setCurrentRow(0)
            self._show_task(0)
        else:
            self._clear_content()

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _asset_path(self, member: str) -> Path:
        destination = Path(self._temporary.name) / member
        if not destination.exists():
            extract_member(self.package_path, member, destination)
        return destination

    def _show_task(self, row: int) -> None:
        variant_index = self.variant_combo.currentIndex()
        if not 0 <= variant_index < len(self.exam.variants):
            return
        tasks = self.exam.variants[variant_index].tasks
        if not 0 <= row < len(tasks):
            return
        task = tasks[row]
        self._clear_content()
        title = QLabel(f"Задание {task.number}" + (f" — {html.escape(task.title)}" if task.title else ""))
        title.setStyleSheet("font-size:22px;font-weight:700")
        self.content_layout.addWidget(title)

        embedded_assets: set[str] = set()
        condition = task.html
        for member in task.visual_assets:
            marker = f"asset://{member}"
            if marker in condition:
                condition = condition.replace(marker, QUrl.fromLocalFile(str(self._asset_path(member).resolve())).toString())
                embedded_assets.add(member)
        if condition:
            self.content_layout.addWidget(TaskHtmlLabel(condition))
        for member in task.visual_assets:
            if member not in embedded_assets:
                self.content_layout.addWidget(ImageAsset(str(self._asset_path(member))))

        key = self.exam.answers.get(self.exam.variants[variant_index].id, {}).get(task.id)
        answer_type = "таблица" if task.answer_type == "table" else "краткий ответ"
        attachments = ", ".join(html.escape(item.name) for item in task.attachments) or "нет"
        details = QFrame()
        details.setObjectName("SoftCard")
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(QLabel(
            f"<b>Тип ответа:</b> {answer_type}<br>"
            f"<b>Файлы задания:</b> {attachments}<br>"
            f"<b>Ключ:</b> {self._render_key(key)}"
        ))
        self.content_layout.addWidget(details)
        self.content_layout.addStretch()
        self.scroll.verticalScrollBar().setValue(0)

    @staticmethod
    def _render_key(value: Any) -> str:
        if value in (None, "", []):
            return "не указан"
        if isinstance(value, list):
            text = " | ".join("; ".join(map(str, row)) for row in value)
        else:
            text = str(value)
        return html.escape(text)

    def done(self, result: int) -> None:
        self._temporary.cleanup()
        super().done(result)


class ResultReviewDialog(QDialog):
    STATUSES = [
        ("Не проверено", "pending"),
        ("Верно", "correct"),
        ("Частично верно", "partial"),
        ("Неверно", "incorrect"),
    ]

    def __init__(self, storage: Storage, result: dict[str, Any], password: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.storage = storage
        self.result = result
        self.password = password
        self.tasks: list[Task] = []
        self.answer_keys: dict[str, Any] = {}
        self.status_boxes: list[QComboBox] = []
        self.point_boxes: list[QSpinBox] = []
        self.comment_edits: list[QLineEdit] = []
        self.setWindowTitle(f"Проверка работы №{result['id']}")
        self.resize(1380, 820)
        self._load_exam()
        self._build()
        self._restore_review()

    def _load_exam(self) -> None:
        exam_row = next((item for item in self.storage.exams() if item["id"] == self.result["exam_id"]), None)
        if not exam_row:
            raise ValueError("Экзаменационный пакет для этой работы не найден")
        exam = validate_package(exam_row["package_path"], self.password)
        variant = next((item for item in exam.variants if item.id == self.result["variant_id"]), None)
        if not variant:
            raise ValueError("Вариант этой работы отсутствует в экзаменационном пакете")
        self.tasks = variant.tasks
        self.answer_keys = exam.answers.get(variant.id, {})

    def _build(self) -> None:
        root = QVBoxLayout(self)
        heading = QLabel(
            f"<h2>Экспертная проверка работы №{self.result['id']}</h2>"
            f"Бланк: <b>{self.result['registration_no']}</b> &nbsp;&nbsp; КИМ: <b>{self.result['kim_no']}</b> &nbsp;&nbsp; "
            f"Вариант: <b>{self.result['variant_name']}</b>"
        )
        root.addWidget(heading)
        info = QLabel("Автосверка заполняет ведомость по точному совпадению с ключом. Эксперт может изменить решение, балл и комментарий для любого задания.")
        info.setWordWrap(True); root.addWidget(info)
        toolbar = QHBoxLayout()
        auto = QPushButton("Автосверка по ключу"); auto.setObjectName("Secondary"); auto.clicked.connect(self.auto_compare)
        clear = QPushButton("Сбросить решения"); clear.clicked.connect(self.clear_decisions)
        toolbar.addWidget(auto); toolbar.addWidget(clear); toolbar.addStretch()
        self.total_label = QLabel(); self.total_label.setStyleSheet("font-size:20px;font-weight:700")
        toolbar.addWidget(self.total_label); root.addLayout(toolbar)
        self.table = QTableWidget(len(self.tasks), 7)
        self.table.setHorizontalHeaderLabels(["№", "Ответ участника", "Ключ", "Решение эксперта", "Балл", "Макс.", "Комментарий"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(0, 50); self.table.setColumnWidth(1, 260); self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(3, 165); self.table.setColumnWidth(4, 80); self.table.setColumnWidth(5, 65)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, task in enumerate(self.tasks):
            answer = self.result.get("answers", {}).get(task.id, "")
            key = self.answer_keys.get(task.id, "")
            maximum = 2 if task.number in (26, 27) else 1
            self.table.setItem(row, 0, QTableWidgetItem(str(task.number)))
            self.table.setItem(row, 1, QTableWidgetItem(self._render_value(answer)))
            self.table.setItem(row, 2, QTableWidgetItem(self._render_value(key)))
            status = QComboBox()
            for label, value in self.STATUSES:
                status.addItem(label, value)
            points = QSpinBox(); points.setRange(0, maximum)
            comment = QLineEdit(); comment.setPlaceholderText("Комментарий к заданию")
            status.currentIndexChanged.connect(lambda _index, r=row: self._status_changed(r))
            points.valueChanged.connect(self._update_total)
            self.table.setCellWidget(row, 3, status); self.table.setCellWidget(row, 4, points)
            maximum_item = QTableWidgetItem(str(maximum)); maximum_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, maximum_item); self.table.setCellWidget(row, 6, comment)
            self.status_boxes.append(status); self.point_boxes.append(points); self.comment_edits.append(comment)
        root.addWidget(self.table, 1)
        root.addWidget(QLabel("Общий комментарий эксперта"))
        self.overall_comment = QTextEdit(); self.overall_comment.setMaximumHeight(90); root.addWidget(self.overall_comment)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить проверку")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.save_review); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self._update_total()

    @staticmethod
    def _render_value(value: Any) -> str:
        if value in (None, "", []):
            return "—"
        if isinstance(value, list):
            return "\n".join("\t".join(map(str, row)) for row in value)
        return str(value)

    @classmethod
    def _normalise(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [[str(cell).strip().casefold() for cell in row] for row in value]
        return "".join(str(value or "").split()).casefold()

    def _status_changed(self, row: int) -> None:
        status = self.status_boxes[row].currentData()
        maximum = self.point_boxes[row].maximum()
        self.point_boxes[row].blockSignals(True)
        if status == "correct":
            self.point_boxes[row].setValue(maximum)
        elif status in ("incorrect", "pending"):
            self.point_boxes[row].setValue(0)
        elif status == "partial" and maximum > 1:
            self.point_boxes[row].setValue(1)
        self.point_boxes[row].blockSignals(False)
        self._update_total()

    def auto_compare(self) -> None:
        for row, task in enumerate(self.tasks):
            answer = self.result.get("answers", {}).get(task.id, "")
            key = self.answer_keys.get(task.id, "")
            matched = bool(self._normalise(answer)) and self._normalise(answer) == self._normalise(key)
            self.status_boxes[row].setCurrentIndex(1 if matched else 3)
        self._update_total()

    def clear_decisions(self) -> None:
        for box in self.status_boxes:
            box.setCurrentIndex(0)
        for edit in self.comment_edits:
            edit.clear()
        self.overall_comment.clear(); self._update_total()

    def _restore_review(self) -> None:
        review = self.result.get("review")
        if not review:
            return
        saved = {str(item.get("task_id")): item for item in review.get("decisions", [])}
        for row, task in enumerate(self.tasks):
            decision = saved.get(task.id)
            if not decision:
                continue
            status_index = self.status_boxes[row].findData(decision.get("status", "pending"))
            self.status_boxes[row].setCurrentIndex(max(status_index, 0))
            self.point_boxes[row].setValue(int(decision.get("points", 0)))
            self.comment_edits[row].setText(str(decision.get("comment", "")))
        self.overall_comment.setPlainText(str(review.get("comment", ""))); self._update_total()

    def _update_total(self) -> None:
        score = sum(box.value() for box in self.point_boxes)
        maximum = sum(box.maximum() for box in self.point_boxes)
        self.total_label.setText(f"Итого: {score} / {maximum}")

    def save_review(self) -> None:
        decisions = []
        for row, task in enumerate(self.tasks):
            decisions.append({
                "task_id": task.id,
                "task_number": task.number,
                "status": str(self.status_boxes[row].currentData()),
                "points": self.point_boxes[row].value(),
                "max_points": self.point_boxes[row].maximum(),
                "comment": self.comment_edits[row].text().strip(),
            })
        self.storage.save_review(int(self.result["id"]), {
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "score": sum(item["points"] for item in decisions),
            "max_score": sum(item["max_points"] for item in decisions),
            "decisions": decisions,
            "comment": self.overall_comment.toPlainText().strip(),
        })
        self.accept()


class ExpertWindow(QMainWindow):
    exams_changed = pyqtSignal()

    def __init__(self, storage: Storage, password: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.storage = storage
        self.password = password
        self._import_worker: PackageImportWorker | None = None
        self._import_progress: QProgressDialog | None = None
        self._import_outcome: tuple[bool, str] | None = None
        self.package_action_buttons: list[QPushButton] = []
        self.setWindowTitle("Станция КЕГЭ — режим эксперта")
        self.resize(1280, 800)
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        self.package_tab = QWidget(); tabs.addTab(self.package_tab, "Экзаменационные пакеты")
        self.results_tab = QWidget(); tabs.addTab(self.results_tab, "Результаты")
        self.package_help_tab = QWidget(); tabs.addTab(self.package_help_tab, "Как получить пакет")
        self.settings_tab = QWidget(); tabs.addTab(self.settings_tab, "Безопасность")
        self._build_packages()
        self._build_results()
        self._build_package_help()
        self._build_settings()
        self.refresh_packages(); self.refresh_results()

    def _build_packages(self) -> None:
        layout = QVBoxLayout(self.package_tab)
        toolbar = QHBoxLayout()
        for label, callback, object_name in [
            ("Импортировать .kege", self.import_package, "Primary"),
            ("Предпросмотр", self.preview_package, "Secondary"),
            ("Сделать активным", self.activate_package, ""),
            ("Сохранить копию", self.copy_package, ""),
            ("Удалить выбранный", self.delete_package, "Danger"),
            ("Очистить список", self.clear_packages, "Danger"),
        ]:
            button = QPushButton(label)
            if object_name: button.setObjectName(object_name)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
            self.package_action_buttons.append(button)
            if callback == self.import_package:
                self.import_button = button
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.package_table = QTableWidget(0, 6)
        self.package_table.setHorizontalHeaderLabels(["Активен", "Название", "Предмет", "Год", "Файл", "ID"])
        self.package_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.package_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.package_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.package_table.itemDoubleClicked.connect(lambda _item: self.preview_package())
        self.package_table.horizontalHeader().setStretchLastSection(True)
        for column, width in enumerate((75, 360, 140, 70, 220)):
            self.package_table.setColumnWidth(column, width)
        layout.addWidget(self.package_table)
        note = QLabel("Дважды щёлкните пакет для предпросмотра. Создание пакетов выполняется отдельно — памятка находится на вкладке «Как получить пакет».")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _build_results(self) -> None:
        layout = QVBoxLayout(self.results_tab)
        toolbar = QHBoxLayout()
        review_button = QPushButton("Проверить выбранную работу"); review_button.setObjectName("Secondary"); review_button.clicked.connect(self.review_selected_result)
        export_button = QPushButton("Экспортировать файл ответов"); export_button.setObjectName("Primary"); export_button.clicked.connect(self.export_selected_result)
        refresh_button = QPushButton("Обновить"); refresh_button.clicked.connect(self.refresh_results)
        delete_button = QPushButton("Удалить выбранный"); delete_button.setObjectName("Danger"); delete_button.clicked.connect(self.delete_selected_result)
        clear_button = QPushButton("Очистить список"); clear_button.setObjectName("Danger"); clear_button.clicked.connect(self.clear_results)
        toolbar.addWidget(review_button); toolbar.addWidget(export_button); toolbar.addWidget(refresh_button)
        toolbar.addWidget(delete_button); toolbar.addWidget(clear_button); toolbar.addStretch()
        layout.addLayout(toolbar)
        splitter = QSplitter()
        self.result_table = QTableWidget(0, 9)
        self.result_table.setHorizontalHeaderLabels(["ID", "Дата", "Бланк", "КИМ", "Пакет", "Вариант", "Контрольная сумма", "Проверка", "Баллы"])
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_table.itemSelectionChanged.connect(self.show_result_detail)
        self.result_table.itemDoubleClicked.connect(lambda _item: self.review_selected_result())
        for column, width in enumerate((55, 145, 135, 110, 230, 180, 150, 110, 90)):
            self.result_table.setColumnWidth(column, width)
        splitter.addWidget(self.result_table)
        self.result_detail = QTextBrowser()
        splitter.addWidget(self.result_detail)
        splitter.setStretchFactor(0, 2); splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _build_package_help(self) -> None:
        layout = QVBoxLayout(self.package_help_tab)
        help_text = QTextBrowser()
        help_text.setHtml(
            "<h2>Как заказать готовый экзаменационный пакет</h2>"
            "<p>Редактор пакетов убран из программы. Так меньше риск получить повреждённый файл или потерять часть условий.</p>"
            "<h3>Что нужно прислать</h3>"
            "<ol>"
            "<li><b>PDF или другой исходник</b> с заданиями. Для открытого варианта можно просто указать точное название и год.</li>"
            "<li><b>Архив дополнительных файлов</b> к заданиям, если они есть: таблицы, тексты, программы, базы данных и изображения.</li>"
            "<li><b>Ответы.</b> Напишите, находятся ли они в конце сборника или приложены отдельным файлом.</li>"
            "<li><b>Количество вариантов</b> и желаемый код активации. Если вариантов несколько, станция назначит один случайно.</li>"
            "</ol>"
            "<h3>Пример запроса</h3>"
            "<p style='background:#eef4fb;padding:12px'>Создай пакет для экзамена по информатике из приложенного PDF. "
            "Возьми 20 вариантов, дополнительные файлы находятся в ZIP, ответы — в конце сборника. Код активации 1597.</p>"
            "<h3>Как установить полученный файл</h3>"
            "<ol><li>Скачайте готовый файл с расширением <b>.kege</b>.</li>"
            "<li>Откройте режим эксперта и нажмите <b>«Импортировать .kege»</b>.</li>"
            "<li>Выделите пакет, откройте <b>«Предпросмотр»</b> и проверьте варианты, задания, файлы и ключи.</li>"
            "<li>Нажмите <b>«Сделать активным»</b>.</li></ol>"
            "<p><b>Важно:</b> исходные материалы и ответы не нужно вручную переносить в программу.</p>"
        )
        layout.addWidget(help_text)

    def _build_settings(self) -> None:
        layout = QVBoxLayout(self.settings_tab)
        card = QFrame(); card.setObjectName("Card"); card.setMaximumWidth(600)
        form = QFormLayout(card)
        self.old_password = QLineEdit(); self.old_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password = QLineEdit(); self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat_password = QLineEdit(); self.repeat_password.setEchoMode(QLineEdit.EchoMode.Password)
        change = QPushButton("Изменить пароль"); change.setObjectName("Primary"); change.clicked.connect(self.change_password)
        form.addRow("Текущий пароль", self.old_password)
        form.addRow("Новый пароль", self.new_password)
        form.addRow("Повтор нового пароля", self.repeat_password)
        form.addRow("", change)
        layout.addWidget(card)
        layout.addWidget(QLabel("При изменении пароля ключи ответов во всех импортированных пакетах перешифровываются."))
        layout.addStretch()

    def selected_exam(self) -> dict[str, Any] | None:
        row = self.package_table.currentRow()
        if row < 0:
            return None
        exam_id = self.package_table.item(row, 5).text()
        return next((item for item in self.storage.exams() if item["id"] == exam_id), None)

    def refresh_packages(self) -> None:
        rows = self.storage.exams()
        self.package_table.setRowCount(len(rows))
        for row, exam in enumerate(rows):
            values = ["Да" if exam["active"] else "", exam["title"], exam["subject"], str(exam["year"]), exam["source_name"], exam["id"]]
            for column, value in enumerate(values):
                self.package_table.setItem(row, column, QTableWidgetItem(value))

    def import_package(self, path: str | None = None) -> None:
        if self._import_worker and self._import_worker.isRunning():
            QMessageBox.information(self, "Импорт выполняется", "Дождитесь завершения текущего импорта.")
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Импорт пакета", "", "Пакет КЕГЭ (*.kege)")
        if not path:
            return
        self._set_package_actions_enabled(False)
        self._import_outcome = None
        self._import_progress = QProgressDialog("Проверка и копирование пакета…", "", 0, 0, self)
        self._import_progress.setCancelButton(None)
        self._import_progress.setWindowTitle("Импорт пакета")
        self._import_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._import_progress.setMinimumDuration(0)
        self._import_worker = PackageImportWorker(self.storage, path, self.password, self)
        self._import_worker.imported.connect(self._package_imported)
        self._import_worker.failed.connect(self._package_import_failed)
        self._import_worker.finished.connect(self._package_import_finished)
        self._import_worker.start()

    def _set_package_actions_enabled(self, enabled: bool) -> None:
        for button in self.package_action_buttons:
            button.setEnabled(enabled)

    def _package_imported(self, _exam_id: str) -> None:
        self.refresh_packages()
        self.exams_changed.emit()
        self._import_outcome = (True, "Пакет проверен и добавлен в список.")

    def _package_import_failed(self, message: str) -> None:
        self._import_outcome = (False, message)

    def _package_import_finished(self) -> None:
        if self._import_progress:
            self._import_progress.close()
            self._import_progress = None
        self._set_package_actions_enabled(True)
        if self._import_worker:
            self._import_worker.deleteLater()
            self._import_worker = None
        outcome = self._import_outcome
        self._import_outcome = None
        if outcome:
            if outcome[0]:
                QMessageBox.information(self, "Пакет импортирован", outcome[1])
            else:
                QMessageBox.critical(self, "Ошибка импорта", outcome[1])

    def preview_package(self) -> None:
        exam = self.selected_exam()
        if not exam:
            QMessageBox.information(self, "Пакет не выбран", "Выберите пакет в таблице.")
            return
        try:
            dialog = PackagePreviewDialog(exam["package_path"], self.password, self)
        except Exception as exc:
            QMessageBox.critical(self, "Предпросмотр недоступен", str(exc))
            return
        dialog.exec()

    def activate_package(self) -> None:
        exam = self.selected_exam()
        if not exam: return
        self.storage.activate_exam(exam["id"])
        self.refresh_packages(); self.exams_changed.emit()

    def copy_package(self) -> None:
        exam = self.selected_exam()
        if not exam: return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить копию", exam["source_name"], "Пакет КЕГЭ (*.kege)")
        if path:
            if not path.lower().endswith(".kege"): path += ".kege"
            shutil.copy2(exam["package_path"], path)

    def delete_package(self) -> None:
        exam = self.selected_exam()
        if not exam:
            QMessageBox.information(self, "Пакет не выбран", "Выберите пакет в таблице.")
            return
        if QMessageBox.question(self, "Удалить пакет?", f"Удалить «{exam['title']}»? Сохранённые результаты останутся.") == QMessageBox.StandardButton.Yes:
            self.storage.remove_exam(exam["id"])
            self.refresh_packages(); self.exams_changed.emit()

    def clear_packages(self) -> None:
        count = len(self.storage.exams())
        if not count:
            QMessageBox.information(self, "Список пуст", "Экзаменационных пакетов нет.")
            return
        answer = QMessageBox.question(
            self,
            "Очистить список пакетов?",
            f"Будут удалены все пакеты ({count}). Сохранённые результаты останутся. Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.storage.clear_exams()
            self.refresh_packages()
            self.exams_changed.emit()

    def refresh_results(self) -> None:
        rows = self.storage.results()
        self.result_table.setRowCount(len(rows))
        for row, result in enumerate(rows):
            checked = "Проверено" if result.get("reviewed_at") else "Не проверено"
            score = f"{result['review_score']:g} / {result['review_max_score']:g}" if result.get("reviewed_at") else "—"
            values = [str(result["id"]), result["finished_at"][:19].replace("T", " "), result["registration_no"], result["kim_no"], result["exam_title"], result["variant_name"], result["checksum"], checked, score]
            for column, value in enumerate(values):
                self.result_table.setItem(row, column, QTableWidgetItem(value))
        self.result_detail.clear()

    def selected_result(self) -> dict[str, Any] | None:
        row = self.result_table.currentRow()
        if row < 0: return None
        return self.storage.result(int(self.result_table.item(row, 0).text()))

    def delete_selected_result(self) -> None:
        result = self.selected_result()
        if not result:
            QMessageBox.information(self, "Работа не выбрана", "Выберите работу в таблице результатов.")
            return
        answer = QMessageBox.question(
            self,
            "Удалить результат?",
            f"Удалить результат №{result['id']} и его экспертную ведомость? Это действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.storage.remove_result(int(result["id"]))
            self.refresh_results()

    def clear_results(self) -> None:
        count = len(self.storage.results())
        if not count:
            QMessageBox.information(self, "Список пуст", "Сохранённых результатов нет.")
            return
        answer = QMessageBox.question(
            self,
            "Очистить список результатов?",
            f"Будут удалены все результаты и экспертные ведомости ({count}). Это действие нельзя отменить. Продолжить?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.storage.clear_results()
            self.refresh_results()

    def show_result_detail(self) -> None:
        result = self.selected_result()
        if not result:
            self.result_detail.clear(); return
        answer_keys: dict[str, Any] = {}
        exam_row = next((item for item in self.storage.exams() if item["id"] == result["exam_id"]), None)
        task_numbers: dict[str, int] = {}
        if exam_row:
            try:
                exam = validate_package(exam_row["package_path"], self.password)
                answer_keys = exam.answers.get(result["variant_id"], {})
                variant = next((item for item in exam.variants if item.id == result["variant_id"]), None)
                if variant:
                    task_numbers = {task.id: task.number for task in variant.tasks}
            except Exception:
                pass
        rows = []
        all_ids = sorted(set(result["answers"]) | set(answer_keys), key=lambda key: task_numbers.get(key, 9999))
        for task_id in all_ids:
            answer = result["answers"].get(task_id, "—")
            key = answer_keys.get(task_id, "—")
            rows.append(f"<tr><td>{task_numbers.get(task_id, task_id)}</td><td>{self._html_value(answer)}</td><td>{self._html_value(key)}</td></tr>")
        self.result_detail.setHtml(
            f"<h2>Результат №{result['id']}</h2><p><b>БР:</b> {result['registration_no']}<br><b>КИМ:</b> {result['kim_no']}<br><b>Контрольная сумма:</b> {result['checksum']}</p>"
            + (f"<p><b>Проверено:</b> {result['review']['score']:g} / {result['review']['max_score']:g}<br><b>Комментарий:</b> {self._html_value(result['review'].get('comment') or '—')}</p>" if result.get("review") else "<p><b>Статус:</b> работа ещё не проверена.</p>")
            + "<table border='1' cellspacing='0' cellpadding='6' width='100%'><tr><th>№</th><th>Ответ участника</th><th>Ключ</th></tr>" + "".join(rows) + "</table>"
        )

    def review_selected_result(self) -> None:
        result = self.selected_result()
        if not result:
            QMessageBox.information(self, "Работа не выбрана", "Выберите работу в таблице результатов.")
            return
        try:
            dialog = ResultReviewDialog(self.storage, result, self.password, self)
        except Exception as exc:
            QMessageBox.critical(self, "Проверка недоступна", str(exc))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_results()
            QMessageBox.information(self, "Проверка сохранена", "Экспертная ведомость работы сохранена в системе.")

    @staticmethod
    def _html_value(value: Any) -> str:
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def export_selected_result(self) -> None:
        result = self.selected_result()
        if not result: return
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт ответов", f"КЕГЭ_{result['registration_no']}_{result['kim_no']}.kege-result", "Результат КЕГЭ (*.kege-result)")
        if not path: return
        if not path.lower().endswith(".kege-result"): path += ".kege-result"
        export_result(path, result)
        QMessageBox.information(self, "Готово", "Файл ответов экспортирован.")

    def change_password(self) -> None:
        old, new, repeat = self.old_password.text(), self.new_password.text(), self.repeat_password.text()
        if not self.storage.verify_expert_password(old):
            QMessageBox.warning(self, "Ошибка", "Текущий пароль указан неверно."); return
        if new != repeat:
            QMessageBox.warning(self, "Ошибка", "Новые пароли не совпадают."); return
        if len(new) < 8:
            QMessageBox.warning(self, "Ошибка", "Новый пароль должен содержать не менее 8 символов."); return
        try:
            for exam in self.storage.exams():
                reencrypt_package_keys(exam["package_path"], old, new)
            self.storage.change_expert_password(old, new)
        except Exception as exc:
            QMessageBox.critical(self, "Пароль не изменён", str(exc)); return
        self.password = new
        self.old_password.clear(); self.new_password.clear(); self.repeat_password.clear()
        QMessageBox.information(self, "Готово", "Пароль эксперта изменён, ключи пакетов перешифрованы.")
