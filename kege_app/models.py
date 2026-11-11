from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Attachment:
    name: str
    path: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Attachment":
        return cls(name=str(value["name"]), path=str(value["path"]))

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": self.path}


@dataclass(slots=True)
class Task:
    id: str
    number: int
    title: str = ""
    html: str = ""
    answer_type: str = "short"
    allowed_pattern: str = r"^[0-9A-Za-zА-Яа-яЁё\-\s]*$"
    max_length: int = 120
    table_rows: int = 0
    table_cols: int = 0
    visual_assets: list[str] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Task":
        return cls(
            id=str(value["id"]),
            number=int(value["number"]),
            title=str(value.get("title", "")),
            html=str(value.get("html", "")),
            answer_type=str(value.get("answer_type", "short")),
            allowed_pattern=str(value.get("allowed_pattern", r"^[0-9A-Za-zА-Яа-яЁё\-\s]*$")),
            max_length=int(value.get("max_length", 120)),
            table_rows=int(value.get("table_rows", 0)),
            table_cols=int(value.get("table_cols", 0)),
            visual_assets=[str(item) for item in value.get("visual_assets", [])],
            attachments=[Attachment.from_dict(item) for item in value.get("attachments", [])],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "html": self.html,
            "answer_type": self.answer_type,
            "allowed_pattern": self.allowed_pattern,
            "max_length": self.max_length,
            "table_rows": self.table_rows,
            "table_cols": self.table_cols,
            "visual_assets": self.visual_assets,
            "attachments": [item.as_dict() for item in self.attachments],
        }


@dataclass(slots=True)
class Variant:
    id: str
    name: str
    tasks: list[Task]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Variant":
        tasks = sorted((Task.from_dict(item) for item in value.get("tasks", [])), key=lambda x: x.number)
        return cls(id=str(value["id"]), name=str(value.get("name", "Вариант")), tasks=tasks)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "tasks": [task.as_dict() for task in self.tasks]}


@dataclass(slots=True)
class ExamPackage:
    id: str
    title: str
    subject: str
    year: int
    duration_minutes: int
    activation_code_hash: str
    variants: list[Variant]
    source: str = ""
    answers: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, value: dict[str, Any], answers: dict[str, dict[str, Any]] | None = None) -> "ExamPackage":
        if value.get("format") != "kege-exam" or int(value.get("format_version", 0)) != 1:
            raise ValueError("Неподдерживаемый формат экзаменационного пакета")
        variants = [Variant.from_dict(item) for item in value.get("variants", [])]
        if not variants or any(not variant.tasks for variant in variants):
            raise ValueError("В пакете отсутствуют варианты или задания")
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            subject=str(value.get("subject", "Информатика")),
            year=int(value.get("year", 2026)),
            duration_minutes=int(value.get("duration_minutes", 235)),
            activation_code_hash=str(value["activation_code_hash"]),
            variants=variants,
            source=str(value.get("source", "")),
            answers=answers or {},
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "format": "kege-exam",
            "format_version": 1,
            "id": self.id,
            "title": self.title,
            "subject": self.subject,
            "year": self.year,
            "duration_minutes": self.duration_minutes,
            "activation_code_hash": self.activation_code_hash,
            "source": self.source,
            "variants": [variant.as_dict() for variant in self.variants],
            "expert_keys": {"encrypted": bool(self.answers), "path": "expert/answer_keys.enc" if self.answers else ""},
        }

