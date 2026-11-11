from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from kege_app.student_ui import InstructionsPage, LandingPage, OverviewPage, RegistrationPage
from kege_app.theme import APP_QSS


def render(widget, destination: Path, width: int = 1920, height: int = 1000) -> None:
    widget.resize(width, height)
    widget.show()
    app.processEvents()
    widget.grab().save(str(destination))
    widget.hide()


root = Path(__file__).resolve().parent.parent
output = root / "tmp_ui_check"
output.mkdir(exist_ok=True)
app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

render(LandingPage(), output / "landing.png")
render(OverviewPage(), output / "overview.png")
render(RegistrationPage(), output / "registration.png")
instructions = InstructionsPage()
instructions.index = 4
instructions._render()
render(instructions, output / "instruction_5.png")
