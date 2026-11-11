from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .models import ExamPackage, Variant
from .security import decrypt_json, encrypt_json, verify_secret


def _safe_member(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Небезопасный путь в пакете: {name}")
    return str(path)


def validate_package(path: str | os.PathLike[str], password: str | None = None) -> ExamPackage:
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise ValueError("В пакете отсутствует manifest.json")
        for name in names:
            _safe_member(name)
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        answers: dict[str, dict[str, Any]] = {}
        keys = manifest.get("expert_keys", {})
        if keys.get("encrypted") and password:
            try:
                answers = decrypt_json(archive.read(keys["path"]), password)
            except Exception as exc:
                raise ValueError("Не удалось расшифровать ключи: неверный пароль эксперта") from exc
        exam = ExamPackage.from_manifest(manifest, answers)
        referenced = set()
        for variant in exam.variants:
            for task in variant.tasks:
                referenced.update(task.visual_assets)
                referenced.update(item.path for item in task.attachments)
        missing = sorted(name for name in referenced if name not in names)
        if missing:
            raise ValueError(f"В пакете отсутствуют файлы: {', '.join(missing[:5])}")
        return exam


def create_package(
    output_path: str | os.PathLike[str],
    exam: ExamPackage,
    source_files: dict[str, str | os.PathLike[str]] | None,
    password: str,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".kege", dir=output.parent) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            manifest = exam.manifest()
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for internal, local in (source_files or {}).items():
                archive.write(Path(local), _safe_member(internal))
            if exam.answers:
                archive.writestr("expert/answer_keys.enc", encrypt_json(exam.answers, password))
        validate_package(temp_path, password)
        temp_path.replace(output)
    finally:
        temp_path.unlink(missing_ok=True)
    return output


def reencrypt_package_keys(path: str | os.PathLike[str], old_password: str, new_password: str) -> None:
    source = Path(path)
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        keys = manifest.get("expert_keys", {})
        if not keys.get("encrypted"):
            return
        key_path = keys["path"]
        answers = decrypt_json(archive.read(key_path), old_password)
        items = [(info, archive.read(info.filename)) for info in archive.infolist() if info.filename != key_path]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".kege", dir=source.parent) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(temp_path, "w") as target:
            for info, payload in items:
                target.writestr(info, payload)
            target.writestr(key_path, encrypt_json(answers, new_password), compress_type=zipfile.ZIP_DEFLATED)
        validate_package(temp_path, new_password)
        temp_path.replace(source)
    finally:
        temp_path.unlink(missing_ok=True)


def extract_member(package_path: str | os.PathLike[str], member: str, destination: str | os.PathLike[str]) -> Path:
    safe = _safe_member(member)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "r") as archive, archive.open(safe) as src, open(destination_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    return destination_path


def choose_variant(exam: ExamPackage, rng: random.Random | None = None) -> Variant:
    return (rng or random.SystemRandom()).choice(exam.variants)


def verify_activation(code: str, exam: ExamPackage) -> bool:
    return verify_secret(code.strip(), exam.activation_code_hash)


def control_sum(exam_id: str, variant_id: str, registration_no: str, answers: dict[str, Any]) -> str:
    payload = json.dumps(
        {"exam": exam_id, "variant": variant_id, "registration": registration_no, "answers": answers},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    number = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 10_000_000_000
    digits = f"{number:010d}"
    return "-".join(digits[index:index + 2] for index in range(0, 10, 2))


def export_result(output_path: str | os.PathLike[str], record: dict[str, Any]) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    answers = record.get("answers", {})
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result.json", json.dumps(record, ensure_ascii=False, indent=2))
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["Номер задания", "Ответ"])
        for task_id, answer in answers.items():
            rendered = json.dumps(answer, ensure_ascii=False) if isinstance(answer, (list, dict)) else str(answer)
            writer.writerow([task_id, rendered])
        archive.writestr("answers.csv", "\ufeff" + buffer.getvalue())
        review = record.get("review")
        if review:
            review_buffer = io.StringIO()
            review_writer = csv.writer(review_buffer, delimiter=";")
            review_writer.writerow(["Номер задания", "Решение эксперта", "Балл", "Максимум", "Комментарий"])
            for decision in review.get("decisions", []):
                review_writer.writerow([
                    decision.get("task_number", decision.get("task_id", "")),
                    decision.get("status", "pending"),
                    decision.get("points", 0),
                    decision.get("max_points", 0),
                    decision.get("comment", ""),
                ])
            archive.writestr("review.csv", "\ufeff" + review_buffer.getvalue())
        archive.writestr(
            "README.txt",
            "Файл результатов тренировочной станции КЕГЭ.\n"
            + ("В файл включена сохранённая ведомость экспертной проверки.\n" if review else "Работа ещё не проверена экспертом.\n"),
        )
    return output
