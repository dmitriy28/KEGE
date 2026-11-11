from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QKeySequence, QPainter, QPixmap
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .instructions import GENERAL_STEPS, INSTRUCTION_SLIDES
from .models import ExamPackage, Task, Variant
from .package_io import control_sum, export_result, extract_member, verify_activation
from .resources import resource_path


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExamSession:
    exam: ExamPackage
    package_path: str
    registration_no: str = ""
    kim_no: str = ""
    variant: Variant | None = None
    answers: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    elapsed_seconds: int = 0
    result_id: int | None = None


class Page(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Root")


class FitPixmapLabel(QLabel):
    """Scales a source image to the available area without cropping it."""

    def __init__(self, path: str | None = None):
        super().__init__()
        self.source = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(1, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if path:
            self.set_image(path)

    def set_image(self, path: str) -> None:
        self.source = QPixmap(path)
        self._update_pixmap()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        if self.source.isNull() or self.width() < 2 or self.height() < 2:
            return
        self.setPixmap(
            self.source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class TimelineStep(QWidget):
    def __init__(self, number: int, heading: str, description: str, first: bool, last: bool):
        super().__init__()
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(22)
        indicator = QWidget()
        indicator.setFixedWidth(30)
        marker_layout = QVBoxLayout(indicator)
        marker_layout.setContentsMargins(0, 0, 0, 0)
        marker_layout.setSpacing(0)

        def segment(visible: bool) -> QWidget:
            host = QWidget()
            line_layout = QHBoxLayout(host)
            line_layout.setContentsMargins(0, 0, 0, 0)
            line_layout.addStretch()
            line = QFrame()
            line.setFixedWidth(1)
            line.setStyleSheet("background:#79c7d8" if visible else "background:transparent")
            line_layout.addWidget(line)
            line_layout.addStretch()
            return host

        marker_layout.addWidget(segment(not first), 1)
        badge = QLabel(str(number))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(30, 30)
        badge.setStyleSheet("background:#28a8c7;color:white;border-radius:15px;font-size:15px")
        marker_layout.addWidget(badge)
        marker_layout.addWidget(segment(not last), 1)
        root.addWidget(indicator)
        text = QLabel(f"<span style='font-weight:500'>{heading}</span><br>{description.replace(chr(10), '<br>')}")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text.setStyleSheet("font-size:15px;color:#090f18")
        root.addWidget(text, 1)


class LandingPage(Page):
    begin_requested = pyqtSignal()
    expert_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(44, 38, 44, 28)
        top = QHBoxLayout()
        title = QLabel("Тренировочная версия\nстанции КЕГЭ")
        title.setObjectName("HeroTitle")
        top.addWidget(title)
        top.addStretch()
        expert = QPushButton("Режим эксперта")
        expert.setObjectName("Link")
        expert.clicked.connect(self.expert_requested)
        top.addWidget(expert, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)
        subtitle = QLabel(
            "Программное обеспечение имитирует основные приёмы работы участника экзамена\n"
            "по информатике в компьютерной форме (КЕГЭ)."
        )
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)
        layout.addStretch(2)
        start = QPushButton("НАЧАТЬ ЭКЗАМЕН")
        start.setObjectName("Primary")
        start.setFixedSize(294, 58)
        start.clicked.connect(self.begin_requested)
        layout.addWidget(start, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(3)
        note = QLabel(
            "ⓘ   В режиме имитации поведение системы максимально близко к реальному экзамену.\n\n"
            "      Внимание! Тренировочная система не является официальным программным обеспечением ЕГЭ."
        )
        note.setWordWrap(True)
        layout.addWidget(note)


class OverviewPage(Page):
    next_requested = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 38, 44, 28)
        title = QLabel("Режим имитации: Общие сведения")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        root.addWidget(QLabel("Процесс сдачи экзамена включает следующие основные этапы:"))
        steps_host = QWidget()
        steps = QVBoxLayout(steps_host)
        steps.setContentsMargins(258, 26, 145, 10)
        steps.setSpacing(0)
        for number, (heading, description) in enumerate(GENERAL_STEPS, 1):
            item = TimelineStep(number, heading, description, number == 1, number == len(GENERAL_STEPS))
            item.setMinimumHeight({1: 94, 2: 94, 3: 140, 4: 94, 5: 120, 6: 104}[number])
            steps.addWidget(item)
        steps_scroll = QScrollArea()
        steps_scroll.setWidgetResizable(True)
        steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        steps_scroll.setStyleSheet("QScrollArea{background:transparent;border:none}QScrollArea>QWidget>QWidget{background:transparent}")
        steps_scroll.setWidget(steps_host)
        root.addWidget(steps_scroll, 1)
        buttons = QHBoxLayout()
        back = QPushButton("Назад")
        back.clicked.connect(self.back_requested)
        next_button = QPushButton("Далее")
        next_button.setObjectName("Primary")
        next_button.clicked.connect(self.next_requested)
        buttons.addWidget(back)
        buttons.addStretch()
        buttons.addWidget(next_button)
        root.addLayout(buttons)


class RegistrationPage(Page):
    next_requested = pyqtSignal(str)
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 32, 34, 28)
        title = QLabel("Единый государственный экзамен по информатике")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        line = QFrame()
        line.setFixedHeight(4)
        line.setStyleSheet("background:#28a8c7")
        root.addWidget(line)
        content_host = QWidget()
        content_host.setMaximumWidth(1200)
        content = QHBoxLayout(content_host)
        content.setContentsMargins(0, 70, 0, 20)
        content.setSpacing(20)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(QLabel("Введите номер вашего бланка регистрации"))
        fields = QHBoxLayout()
        self.parts: list[QLineEdit] = []
        for length in (1, 6, 6):
            edit = QLineEdit()
            edit.setObjectName("RegistrationPart")
            edit.setMaxLength(length)
            edit.setFixedWidth(58 if length == 1 else 170)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.textChanged.connect(lambda text, widget=edit: self._digits_only(widget, text))
            self.parts.append(edit)
            fields.addWidget(edit)
        left.addLayout(fields)
        hint = QLabel("ⓘ  Введите любую цифровую комбинацию, включающую 13 цифр.\nПосле ввода станет доступна кнопка «Далее».")
        hint.setWordWrap(True)
        left.addWidget(hint)
        left.addStretch()
        left_host = QWidget(); left_host.setLayout(left); left_host.setFixedWidth(430)
        content.addWidget(left_host)
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(560)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 12, 10, 10)
        card_layout.addWidget(QLabel("<b>Бланк регистрации</b>"))
        card_layout.addWidget(QLabel("Номер расположен в верхней части бланка и состоит из 13 цифр."))
        blank_path = resource_path("assets", "registration", "blank.png")
        sample = FitPixmapLabel(str(blank_path))
        sample.setMinimumHeight(330)
        card_layout.addWidget(sample, 1)
        content.addWidget(card, 1)
        root.addWidget(content_host, 1, alignment=Qt.AlignmentFlag.AlignHCenter)
        buttons = QHBoxLayout()
        back = QPushButton("Назад")
        back.clicked.connect(self.back_requested)
        self.next_button = QPushButton("Далее")
        self.next_button.setObjectName("Primary")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self._submit)
        buttons.addWidget(back)
        buttons.addStretch()
        buttons.addWidget(self.next_button)
        root.addLayout(buttons)

    def _digits_only(self, edit: QLineEdit, value: str) -> None:
        clean = "".join(character for character in value if character.isdigit())
        if clean != value:
            edit.setText(clean)
        self.next_button.setEnabled(sum(len(part.text()) for part in self.parts) == 13)

    def _submit(self) -> None:
        self.next_requested.emit("".join(part.text() for part in self.parts))


class InstructionsPage(Page):
    finished = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.index = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        self.title = QLabel("Инструкция")
        self.title.setObjectName("PageTitle")
        root.addWidget(self.title)
        line = QFrame()
        line.setFixedHeight(4)
        line.setStyleSheet("background:#28a8c7")
        root.addWidget(line)
        self.counter = QLabel()
        root.addWidget(self.counter)
        middle = QHBoxLayout()
        self.previous = QPushButton("←")
        self.previous.setFixedSize(58, 58)
        self.previous.clicked.connect(self._previous)
        middle.addWidget(self.previous)
        self.viewer = FitPixmapLabel()
        self.viewer.setStyleSheet("background:#f7f7f7;border:1px solid #8f98a6")
        self.viewer.setMinimumWidth(900)
        middle.addWidget(self.viewer, 1)
        self.next = QPushButton("→")
        self.next.setFixedSize(58, 58)
        self.next.clicked.connect(self._next)
        middle.addWidget(self.next)
        root.addLayout(middle, 1)
        bottom = QHBoxLayout()
        back = QPushButton("К вводу бланка")
        back.clicked.connect(self.back_requested)
        self.continue_button = QPushButton("Продолжить")
        self.continue_button.setObjectName("Primary")
        self.continue_button.clicked.connect(self.finished)
        bottom.addWidget(back)
        bottom.addStretch()
        bottom.addWidget(self.continue_button)
        root.addLayout(bottom)
        self._render()

    def reset(self) -> None:
        self.index = 0
        self._render()

    def _render(self) -> None:
        slide = INSTRUCTION_SLIDES[self.index]
        self.counter.setText(f"{self.index + 1} / {len(INSTRUCTION_SLIDES)}")
        self.viewer.set_image(slide["image"])
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(self.index < len(INSTRUCTION_SLIDES) - 1)
        self.continue_button.setEnabled(self.index == len(INSTRUCTION_SLIDES) - 1)

    def _previous(self) -> None:
        if self.index > 0:
            self.index -= 1
            self._render()

    def _next(self) -> None:
        if self.index < len(INSTRUCTION_SLIDES) - 1:
            self.index += 1
            self._render()


class ParticipantConfirmationPage(Page):
    confirmed = pyqtSignal()
    edit_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(38, 34, 38, 26)
        title = QLabel("Регистрация участника")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        line = QFrame(); line.setFixedHeight(4); line.setStyleSheet("background:#28a8c7")
        root.addWidget(line)
        root.addWidget(QLabel("<b>БЛАНК РЕГИСТРАЦИИ</b>"))
        identity = QHBoxLayout()
        self.registration_label = QLabel()
        self.registration_label.setStyleSheet("font-size:42px;letter-spacing:7px;background:white;border:1px solid #c3c9d1;padding:12px 18px")
        identity.addWidget(self.registration_label)
        edit = QPushButton("ИЗМЕНИТЬ"); edit.setObjectName("Danger"); edit.setFixedWidth(240)
        edit.clicked.connect(self.edit_requested)
        identity.addWidget(edit); identity.addStretch()
        root.addLayout(identity)
        root.addWidget(QLabel("<b>НОМЕР КИМ</b>"))
        self.kim_label = QLabel()
        self.kim_label.setStyleSheet("font-size:36px;letter-spacing:5px")
        root.addWidget(self.kim_label)
        card = QFrame(); card.setObjectName("Card"); card.setMaximumWidth(1000)
        card_layout = QVBoxLayout(card)
        notes = [
            "Сверьте приведённый выше номер бланка регистрации с номером, указанным на Вашем бланке регистрации.",
            "Если Вы ошиблись при вводе номера бланка регистрации, нажмите «Изменить» справа от номера бланка.",
            "Если введённый номер бланка регистрации верный, подтвердите корректность данных.",
        ]
        for number, text in enumerate(notes, 1):
            row = QHBoxLayout(); badge = QLabel(str(number)); badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(64, 64); badge.setStyleSheet("background:#28a8c7;color:white;border-radius:32px;font-size:29px")
            label = QLabel(text); label.setWordWrap(True); row.addWidget(badge); row.addWidget(label, 1); card_layout.addLayout(row)
        root.addWidget(card)
        root.addStretch()
        bottom = QHBoxLayout()
        confirm = QPushButton("ДАННЫЕ КОРРЕКТНЫ"); confirm.setObjectName("Primary"); confirm.setFixedWidth(360)
        confirm.clicked.connect(self.confirmed)
        bottom.addWidget(confirm); bottom.addWidget(QLabel("ⓘ  В режиме имитации подтвердите корректность данных самостоятельно.")); bottom.addStretch()
        root.addLayout(bottom)

    def configure(self, registration: str, kim: str) -> None:
        self.registration_label.setText(f"{registration[:1]}  {registration[1:7]}  {registration[7:]}")
        self.kim_label.setText(f"{kim[:4]}  {kim[4:7]}  {kim[7:]}")


class ActivationPage(Page):
    start_requested = pyqtSignal(str)
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.registration = ""
        self.kim = ""
        self.exam_title = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 32, 34, 28)
        title = QLabel("Режим имитации: Активация экзамена")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        line = QFrame()
        line.setFixedHeight(4)
        line.setStyleSheet("background:#28a8c7")
        root.addWidget(line)
        self.registration_label = QLabel()
        self.registration_label.setStyleSheet("font-size:30px;letter-spacing:6px")
        root.addWidget(QLabel("<b>БЛАНК РЕГИСТРАЦИИ</b>"))
        root.addWidget(self.registration_label)
        self.kim_label = QLabel(); self.kim_label.setStyleSheet("font-size:31px;letter-spacing:5px")
        root.addWidget(QLabel("<b>НОМЕР КИМ</b>")); root.addWidget(self.kim_label)
        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(880)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(QLabel("❶  Введите код активации, сообщённый организатором."))
        card_layout.addWidget(QLabel("❷  Нажмите «Начать экзамен» после объявления о начале."))
        root.addWidget(card)
        root.addStretch()
        root.addWidget(QLabel('ЭКЗАМЕН НАЧНЁТСЯ ПОСЛЕ НАЖАТИЯ КНОПКИ "НАЧАТЬ ЭКЗАМЕН"'), alignment=Qt.AlignmentFlag.AlignCenter)
        root.addStretch()
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Код активации:"))
        self.code = QLineEdit()
        self.code.setEchoMode(QLineEdit.EchoMode.Password)
        self.code.setMaxLength(30)
        self.code.setFixedWidth(330)
        controls.addWidget(self.code)
        start = QPushButton("НАЧАТЬ ЭКЗАМЕН")
        start.setObjectName("Primary")
        start.clicked.connect(lambda: self.start_requested.emit(self.code.text()))
        controls.addWidget(start)
        root.addLayout(controls)
        back = QPushButton("Назад к инструкции")
        back.clicked.connect(self.back_requested)
        root.addWidget(back, alignment=Qt.AlignmentFlag.AlignLeft)

    def configure(self, registration: str, kim: str) -> None:
        self.registration = registration
        self.registration_label.setText(f"{registration[:1]}  {registration[1:7]}  {registration[7:]}")
        self.kim = kim
        self.kim_label.setText(f"{kim[:4]}  {kim[4:7]}  {kim[7:]}")
        self.code.clear()


class PasteTableWidget(QTableWidget):
    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            text = QApplication.clipboard().text()
            start_row = max(self.currentRow(), 0)
            start_col = max(self.currentColumn(), 0)
            for row_offset, line in enumerate(text.splitlines()):
                values = line.split("\t")
                for col_offset, value in enumerate(values):
                    row, col = start_row + row_offset, start_col + col_offset
                    if row < self.rowCount() and col < self.columnCount():
                        self.setItem(row, col, QTableWidgetItem(value.strip()))
            return
        super().keyPressEvent(event)


class ImageAsset(QWidget):
    def __init__(self, path: str):
        super().__init__()
        self.pixmap = QPixmap(path)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self.pixmap.isNull():
            self.setMinimumHeight(60)

    def hasHeightForWidth(self) -> bool:
        return not self.pixmap.isNull()

    def heightForWidth(self, width: int) -> int:
        if self.pixmap.isNull() or self.pixmap.width() <= 0:
            return 60
        return max(1, round(width * self.pixmap.height() / self.pixmap.width()))

    def sizeHint(self) -> QSize:
        if self.pixmap.isNull():
            return QSize(600, 60)
        width = min(max(self.pixmap.width(), 600), 1200)
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self.pixmap.isNull():
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Не удалось открыть изображение условия")
            return
        target = self.pixmap.size()
        target.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - target.width()) // 2
        painter.drawPixmap(x, 0, target.width(), target.height(), self.pixmap)


class TaskHtmlLabel(QTextBrowser):
    def __init__(self, html: str):
        super().__init__()
        self._height_update_pending = False
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.document().setDocumentMargin(4)
        self.setHtml(html)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("QTextBrowser{background:white;color:#111827;font-size:16px;padding:0;border:none}")
        QTimer.singleShot(0, self._update_document_height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._height_update_pending:
            self._height_update_pending = True
            QTimer.singleShot(0, self._update_document_height)

    def _update_document_height(self) -> None:
        self._height_update_pending = False
        width = max(self.viewport().width(), 200)
        self.document().setTextWidth(width)
        height = min(max(round(self.document().size().height()) + 4, 40), 100_000)
        if abs(self.height() - height) > 2:
            self.setFixedHeight(height)


class ExamPage(Page):
    finish_requested = pyqtSignal()

    def __init__(self, work_root: Path, cache_root: Path):
        super().__init__()
        self.work_root = work_root
        self.cache_root = cache_root
        self.session: ExamSession | None = None
        self.current_index = 0
        self.remaining_seconds = 0
        self.task_buttons: list[QPushButton] = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(78)
        header_layout = QHBoxLayout(header)
        logo = QLabel("◉")
        logo.setStyleSheet("font-size:34px;color:#ffb01e")
        header_layout.addWidget(logo)
        self.time_label = QLabel("⌛ 3:55")
        self.time_label.setStyleSheet("font-size:22px;color:#16cba0;border:1px solid #158f8d;padding:8px")
        header_layout.addWidget(self.time_label)
        self.identity = QLabel()
        self.identity.setStyleSheet("font-size:23px;color:white")
        header_layout.addWidget(self.identity)
        header_layout.addStretch()
        finish = QPushButton("Завершить экзамен досрочно")
        finish.setStyleSheet("background:transparent;border:none;color:white;font-size:17px;font-weight:600;letter-spacing:2px")
        finish.clicked.connect(self._confirm_finish)
        header_layout.addWidget(finish)
        help_button = QPushButton("?")
        help_button.setFixedWidth(45)
        help_button.setStyleSheet("background:transparent;border:none;color:white;font-size:20px")
        help_button.clicked.connect(self._show_help)
        header_layout.addWidget(help_button)
        root.addWidget(header)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 8, 8)
        body.setSpacing(0)
        side = QFrame()
        side.setFixedWidth(142)
        side.setStyleSheet("background:#dfe8f7")
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(16, 16, 16, 14)
        self.count_label = QLabel("0 / 0")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setStyleSheet("font-size:26px;font-weight:700")
        side_layout.addWidget(QLabel("Дано ответов"), alignment=Qt.AlignmentFlag.AlignCenter)
        side_layout.addWidget(self.count_label)
        up = QPushButton("↑")
        up.setObjectName("Secondary")
        up.setFixedSize(38, 38)
        up.setStyleSheet("padding:0;font-size:20px;background:#213a66;color:white")
        up.clicked.connect(lambda: self.task_scroll.verticalScrollBar().setValue(self.task_scroll.verticalScrollBar().value() - 150))
        side_layout.addWidget(up, alignment=Qt.AlignmentFlag.AlignHCenter)
        info = QPushButton("i")
        info.setObjectName("Secondary")
        info.setFixedSize(38, 38)
        info.setStyleSheet("padding:0;font-size:19px;background:#213a66;color:white")
        info.clicked.connect(self._show_help)
        side_layout.addWidget(info, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.task_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.task_list = QWidget()
        self.task_list_layout = QVBoxLayout(self.task_list)
        self.task_list_layout.setContentsMargins(0, 0, 0, 0)
        self.task_list_layout.setSpacing(8)
        self.task_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.task_scroll.setWidget(self.task_list)
        side_layout.addWidget(self.task_scroll, 1)
        down = QPushButton("↓")
        down.setObjectName("Secondary")
        down.setFixedSize(38, 38)
        down.setStyleSheet("padding:0;font-size:20px;background:#213a66;color:white")
        down.clicked.connect(lambda: self.task_scroll.verticalScrollBar().setValue(self.task_scroll.verticalScrollBar().value() + 150))
        side_layout.addWidget(down, alignment=Qt.AlignmentFlag.AlignHCenter)
        body.addWidget(side)
        center = QVBoxLayout()
        center.setContentsMargins(0, 6, 0, 0)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setStyleSheet("QScrollArea{background:white;border:none}")
        self.content = QWidget()
        self.content.setStyleSheet("background:white")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(28, 24, 28, 18)
        self.content_scroll.setWidget(self.content)
        center.addWidget(self.content_scroll, 1)
        nav = QHBoxLayout()
        self.previous = QPushButton("←")
        self.previous.setFixedSize(58, 48)
        self.previous.clicked.connect(lambda: self.open_task(self.current_index - 1))
        self.next = QPushButton("→")
        self.next.setFixedSize(58, 48)
        self.next.clicked.connect(lambda: self.open_task(self.current_index + 1))
        nav.addWidget(self.previous)
        nav.addStretch()
        nav.addWidget(self.next)
        center.addLayout(nav)
        body.addLayout(center, 1)
        body_host = QWidget()
        body_host.setLayout(body)
        root.addWidget(body_host, 1)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "content_scroll"):
            QTimer.singleShot(0, self._sync_content_margins)

    def _sync_content_margins(self) -> None:
        width = self.content_scroll.viewport().width()
        margin = max(28, (width - 1320) // 2)
        self.content_layout.setContentsMargins(margin, 24, margin, 18)

    def start(self, session: ExamSession) -> None:
        self.session = session
        self.remaining_seconds = session.exam.duration_minutes * 60
        self.identity.setText(f"КИМ № {session.kim_no}    БР № {session.registration_no}")
        while self.task_list_layout.count():
            item = self.task_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.task_buttons.clear()
        assert session.variant is not None
        for index, task in enumerate(session.variant.tasks):
            button = QPushButton(str(task.number))
            button.setObjectName("TaskButton")
            button.setFixedSize(38, 38)
            button.clicked.connect(lambda _checked=False, idx=index: self.open_task(idx))
            self.task_list_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.task_buttons.append(button)
        self.current_index = 0
        self._update_time()
        self.open_task(0)
        self.timer.start(1000)

    def _clear_content(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _asset_path(self, member: str) -> Path:
        assert self.session is not None
        target = self.cache_root / self.session.exam.id / member
        if not target.exists():
            extract_member(self.session.package_path, member, target)
        return target

    def open_task(self, index: int) -> None:
        if not self.session or not self.session.variant:
            return
        tasks = self.session.variant.tasks
        if not 0 <= index < len(tasks):
            return
        self.current_index = index
        task = tasks[index]
        self._clear_content()
        self._sync_content_margins()
        condition_host = QWidget()
        condition_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        condition_layout = QVBoxLayout(condition_host)
        condition_layout.setContentsMargins(0, 0, 0, 8)
        condition_layout.setSpacing(8)
        title = QLabel(f"Задание {task.number}")
        title.setStyleSheet("font-size:20px;font-weight:700")
        condition_layout.addWidget(title)
        embedded_assets: set[str] = set()
        if task.html:
            html = task.html
            for member in task.visual_assets:
                marker = f"asset://{member}"
                if marker in html:
                    html = html.replace(marker, QUrl.fromLocalFile(str(self._asset_path(member).resolve())).toString())
                    embedded_assets.add(member)
            condition_layout.addWidget(TaskHtmlLabel(html))
        for member in task.visual_assets:
            if member not in embedded_assets:
                condition_layout.addWidget(ImageAsset(str(self._asset_path(member))))
        self.content_layout.addWidget(condition_host)
        if task.attachments:
            attachments = QFrame()
            attachments.setObjectName("SoftCard")
            row = QHBoxLayout(attachments)
            row.addWidget(QLabel("Файлы задания:"))
            for item in task.attachments:
                button = QPushButton(f"⇩  {item.name}")
                button.clicked.connect(lambda _checked=False, attachment=item, current=task: self._open_attachment(current, attachment.name, attachment.path))
                row.addWidget(button)
            row.addStretch()
            self.content_layout.addWidget(attachments)
        answer_card = QFrame()
        answer_card.setObjectName("SoftCard")
        answer_card.setMaximumWidth(520)
        answer_layout = QVBoxLayout(answer_card)
        answer_layout.addWidget(QLabel("Ответ"))
        saved = self.session.answers.get(task.id)
        if task.answer_type == "table":
            self.answer_table = PasteTableWidget(max(task.table_rows, 1), max(task.table_cols, 1))
            self.answer_table.setMaximumHeight(min(360, 42 * max(task.table_rows, 1) + 50))
            self.answer_table.horizontalHeader().setStretchLastSection(True)
            if isinstance(saved, list):
                for row, values in enumerate(saved):
                    for column, value in enumerate(values):
                        if row < self.answer_table.rowCount() and column < self.answer_table.columnCount():
                            self.answer_table.setItem(row, column, QTableWidgetItem(str(value)))
            answer_layout.addWidget(self.answer_table)
            self.answer_edit = None
        else:
            self.answer_edit = QLineEdit()
            self.answer_edit.setObjectName("Answer")
            self.answer_edit.setMaxLength(task.max_length)
            self.answer_edit.setText(str(saved or ""))
            answer_layout.addWidget(self.answer_edit)
            self.answer_table = None
        row = QHBoxLayout()
        clear = QPushButton("Очистить")
        clear.clicked.connect(self._clear_answer)
        save = QPushButton("Ответ сохранён" if self._is_answered(task.id) else "Сохранить ответ")
        save.setObjectName("Primary")
        save.setStyleSheet("background:#11c889;border:1px solid #0cab77;color:#063d2a;font-weight:600")
        save.clicked.connect(self._save_answer)
        row.addStretch()
        row.addWidget(clear)
        row.addWidget(save)
        answer_layout.addLayout(row)
        self.content_layout.addWidget(answer_card, alignment=Qt.AlignmentFlag.AlignRight)
        self.content_layout.addStretch()
        self.content_scroll.verticalScrollBar().setValue(0)
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index < len(tasks) - 1)
        self._refresh_task_buttons()

    def _open_attachment(self, task: Task, name: str, member: str) -> None:
        assert self.session is not None
        log = logging.getLogger("kege_station")
        try:
            folder = self.work_root / self.session.registration_no / f"task_{task.number}"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / Path(name).name
            extract_member(self.session.package_path, member, path)
            resolved = path.resolve()
            log.info("Открытие файла задания: %s", resolved)
            if sys.platform == "win32":
                os.startfile(str(resolved))  # type: ignore[attr-defined]
                opened = True
            elif sys.platform == "darwin":
                opened = subprocess.Popen(["open", str(resolved)], start_new_session=True).pid > 0
            else:
                opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
            if not opened:
                raise OSError("Операционная система не нашла программу для этого типа файла")
        except Exception as exc:
            log.exception("Не удалось открыть файл задания %s", name)
            QMessageBox.warning(
                self,
                "Файл не открыт",
                f"Не удалось открыть «{name}».\n\n{exc}\n\nФайл можно открыть вручную из папки экзамена.",
            )

    def _clear_answer(self) -> None:
        if self.answer_edit is not None:
            self.answer_edit.clear()
        if self.answer_table is not None:
            self.answer_table.clearContents()

    def _save_answer(self) -> None:
        assert self.session and self.session.variant
        task = self.session.variant.tasks[self.current_index]
        if self.answer_edit is not None:
            value: Any = self.answer_edit.text().strip()
            try:
                valid = re.fullmatch(task.allowed_pattern, value) is not None
            except re.error:
                valid = True
            if value and not valid:
                QMessageBox.warning(self, "Ответ не сохранён", "Ответ содержит недопустимые для этого задания символы.")
                return
        else:
            assert self.answer_table is not None
            value = []
            for row in range(self.answer_table.rowCount()):
                values = []
                for column in range(self.answer_table.columnCount()):
                    item = self.answer_table.item(row, column)
                    values.append(item.text().strip() if item else "")
                value.append(values)
        if self._value_has_data(value):
            self.session.answers[task.id] = value
        else:
            self.session.answers.pop(task.id, None)
        self.open_task(self.current_index)

    @staticmethod
    def _value_has_data(value: Any) -> bool:
        if isinstance(value, list):
            return any(str(cell).strip() for row in value for cell in row)
        return bool(str(value).strip())

    def _is_answered(self, task_id: str) -> bool:
        return self.session is not None and task_id in self.session.answers and self._value_has_data(self.session.answers[task_id])

    def _refresh_task_buttons(self) -> None:
        assert self.session and self.session.variant
        answered = 0
        for index, (button, task) in enumerate(zip(self.task_buttons, self.session.variant.tasks)):
            is_answered = self._is_answered(task.id)
            answered += int(is_answered)
            button.setProperty("answered", is_answered)
            button.setProperty("active", index == self.current_index)
            if index == self.current_index:
                button.setStyleSheet("background:#213a66;color:white;border:1px solid #162f59;padding:0;font-weight:600")
            elif is_answered:
                button.setStyleSheet("background:#edf4e6;color:#10284f;border:1px solid #9cbf75;padding:0;font-weight:600")
            else:
                button.setStyleSheet("background:white;color:#10284f;border:1px solid transparent;padding:0;font-weight:600")
        self.count_label.setText(f"{answered} / {len(self.task_buttons)}")

    def _tick(self) -> None:
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            if self.session:
                self.session.elapsed_seconds += 1
            self._update_time()
        if self.remaining_seconds <= 0:
            self.timer.stop()
            QMessageBox.information(self, "Время истекло", "Время выполнения экзаменационной работы завершилось.")
            self.finish_requested.emit()

    def _update_time(self) -> None:
        hours, remainder = divmod(self.remaining_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.time_label.setText(f"⌛ {hours}:{minutes:02d}:{seconds:02d}")

    def _confirm_finish(self) -> None:
        assert self.session and self.session.variant
        answered = len(self.session.answers)
        total = len(self.session.variant.tasks)
        response = QMessageBox.question(
            self,
            "Завершить экзамен?",
            f"Дано ответов: {answered} из {total}.\nПосле завершения вернуться к заданиям будет невозможно.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response == QMessageBox.StandardButton.Yes:
            self.timer.stop()
            self.finish_requested.emit()

    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Инструкция")
        dialog.resize(1280, 860)
        layout = QVBoxLayout(dialog)
        counter = QLabel()
        layout.addWidget(counter)
        row = QHBoxLayout()
        previous = QPushButton("←"); previous.setFixedSize(58, 58)
        viewer = FitPixmapLabel(); viewer.setStyleSheet("background:#f7f7f7;border:1px solid #8f98a6")
        next_button = QPushButton("→"); next_button.setFixedSize(58, 58)
        row.addWidget(previous); row.addWidget(viewer, 1); row.addWidget(next_button)
        layout.addLayout(row, 1)
        state = {"index": 0}

        def render() -> None:
            index = state["index"]
            viewer.set_image(INSTRUCTION_SLIDES[index]["image"])
            counter.setText(f"{index + 1} / {len(INSTRUCTION_SLIDES)}")
            previous.setEnabled(index > 0)
            next_button.setEnabled(index < len(INSTRUCTION_SLIDES) - 1)

        def move(delta: int) -> None:
            state["index"] = max(0, min(len(INSTRUCTION_SLIDES) - 1, state["index"] + delta))
            render()

        previous.clicked.connect(lambda: move(-1))
        next_button.clicked.connect(lambda: move(1))
        close = QPushButton("Закрыть"); close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        render()
        dialog.exec()


class FinishPage(Page):
    new_exam_requested = pyqtSignal()
    export_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.record: dict[str, Any] | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(90)
        header_layout = QHBoxLayout(header)
        title = QLabel("Единый государственный экзамен  Информатика и ИКТ (КЕГЭ)")
        title.setStyleSheet("font-size:28px;color:white")
        header_layout.addWidget(title)
        root.addWidget(header)
        content = QVBoxLayout()
        content.setContentsMargins(290, 38, 290, 38)
        heading = QLabel("Экзамен закончен")
        heading.setStyleSheet("font-size:38px;font-weight:600")
        content.addWidget(heading)
        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        self.identity = QLabel()
        self.identity.setStyleSheet("font-size:24px")
        self.answered = QLabel()
        self.answered.setStyleSheet("font-size:23px")
        self.checksum = QLabel()
        self.checksum.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.checksum.setStyleSheet("font-size:28px;font-weight:700;background:#f3f6fb;padding:20px")
        grid.addWidget(self.identity, 0, 0, 1, 2)
        grid.addWidget(self.answered, 1, 0, 1, 2)
        grid.addWidget(QLabel("Запишите контрольную сумму в соответствующее поле бланка регистрации"), 2, 0, 1, 2)
        grid.addWidget(self.checksum, 3, 0, 1, 2)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Пароль технического специалиста")
        export_button = QPushButton("Перейти к экспорту результата")
        export_button.clicked.connect(lambda: self.export_requested.emit(self.password.text()))
        grid.addWidget(self.password, 4, 0)
        grid.addWidget(export_button, 4, 1)
        content.addWidget(card)
        content.addWidget(QLabel("ⓘ  Файл ответов сохранён в системе и доступен в режиме эксперта."))
        content.addStretch()
        new_button = QPushButton("Вернуться на начальную страницу")
        new_button.clicked.connect(self.new_exam_requested)
        content.addWidget(new_button, alignment=Qt.AlignmentFlag.AlignLeft)
        host = QWidget()
        host.setLayout(content)
        root.addWidget(host, 1)

    def show_record(self, record: dict[str, Any], total_tasks: int) -> None:
        self.record = record
        self.identity.setText(f"КИМ № {record['kim_no']}    БР № {record['registration_no']}")
        self.answered.setText(f"Дано ответов: <b>{len(record['answers'])} / {total_tasks}</b>")
        self.checksum.setText(f"Контрольная сумма\n{record['checksum']}")
        self.password.clear()
