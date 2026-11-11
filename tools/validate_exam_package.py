from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kege_app.package_io import validate_package  # noqa: E402


@dataclass
class Audit:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict[str, object] = field(default_factory=dict)


def audit_package(
    path: Path,
    password: str | None,
    expect_variants: int | None,
    expect_tasks: int | None,
) -> Audit:
    audit = Audit()
    try:
        exam = validate_package(path, password)
    except Exception as exc:
        audit.errors.append(f"Пакет не прошёл базовую проверку: {exc}")
        return audit

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    audit.info.update({
        "id": exam.id,
        "title": exam.title,
        "variants": len(exam.variants),
        "tasks_per_variant": [len(variant.tasks) for variant in exam.variants],
        "files": len(names),
        "encrypted_keys": bool(manifest.get("expert_keys", {}).get("encrypted")),
    })

    if expect_variants is not None and len(exam.variants) != expect_variants:
        audit.errors.append(f"Ожидалось вариантов: {expect_variants}; найдено: {len(exam.variants)}")
    if not exam.source.strip():
        audit.warnings.append("Не заполнено поле source")

    variant_ids: set[str] = set()
    global_task_ids: set[str] = set()
    referenced: set[str] = set()

    for variant in exam.variants:
        if variant.id in variant_ids:
            audit.errors.append(f"Повторяется ID варианта: {variant.id}")
        variant_ids.add(variant.id)
        if expect_tasks is not None and len(variant.tasks) != expect_tasks:
            audit.errors.append(
                f"{variant.name}: ожидалось заданий {expect_tasks}; найдено {len(variant.tasks)}"
            )

        numbers: set[int] = set()
        variant_answers = exam.answers.get(variant.id, {}) if password else {}
        if password and manifest.get("expert_keys", {}).get("encrypted") and variant.id not in exam.answers:
            audit.errors.append(f"Нет секции ключей для варианта {variant.id}")

        for task in variant.tasks:
            label = f"{variant.name}, задание {task.number}"
            if task.id in global_task_ids:
                audit.errors.append(f"Повторяется ID задания: {task.id}")
            global_task_ids.add(task.id)
            if task.number in numbers:
                audit.errors.append(f"{variant.name}: повторяется номер задания {task.number}")
            numbers.add(task.number)

            if not task.html.strip():
                audit.errors.append(f"{label}: пустое HTML-условие")
            if re.search(r"data:image/[^;]+;base64,", task.html, flags=re.IGNORECASE):
                audit.warnings.append(f"{label}: изображение встроено как base64; лучше отдельный asset")
            if task.answer_type not in {"short", "table"}:
                audit.errors.append(f"{label}: неизвестный answer_type={task.answer_type!r}")
            if task.answer_type == "table" and (task.table_rows <= 0 or task.table_cols <= 0):
                audit.errors.append(f"{label}: для table не задан положительный размер")
            if task.answer_type == "short":
                try:
                    re.compile(task.allowed_pattern)
                except re.error as exc:
                    audit.errors.append(f"{label}: ошибочное регулярное выражение: {exc}")

            referenced.update(task.visual_assets)
            referenced.update(item.path for item in task.attachments)
            for asset in task.visual_assets:
                if f"asset://{asset}" not in task.html:
                    audit.warnings.append(f"{label}: visual asset не используется в HTML: {asset}")

            if password and manifest.get("expert_keys", {}).get("encrypted"):
                if task.id not in variant_answers:
                    audit.warnings.append(f"{label}: отсутствует ключ ответа")
                elif task.answer_type == "table":
                    answer = variant_answers[task.id]
                    valid_shape = (
                        isinstance(answer, list)
                        and len(answer) == task.table_rows
                        and all(isinstance(row, list) and len(row) == task.table_cols for row in answer)
                    )
                    if not valid_shape:
                        audit.errors.append(f"{label}: размер табличного ключа не совпадает с полями ответа")

    pdfs = sorted(name for name in names if name.lower().endswith(".pdf"))
    if pdfs:
        audit.errors.append("В пакет вложены PDF: " + ", ".join(pdfs[:10]))

    allowed_metadata = {"manifest.json", "expert/answer_keys.enc"}
    unreferenced = sorted(
        name for name in names
        if not name.endswith("/") and name not in allowed_metadata and name not in referenced
    )
    if unreferenced:
        audit.warnings.append("Непривязанные файлы: " + ", ".join(unreferenced[:10]))
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверить экзаменационный пакет KEGE Station")
    parser.add_argument("package", type=Path)
    parser.add_argument("--password", help="Пароль для проверки зашифрованных ключей")
    parser.add_argument("--expect-variants", type=int)
    parser.add_argument("--expect-tasks", type=int)
    parser.add_argument("--strict", action="store_true", help="Считать предупреждения ошибками")
    parser.add_argument("--json", action="store_true", help="Вывести машинный JSON")
    args = parser.parse_args()

    result = audit_package(args.package, args.password, args.expect_variants, args.expect_tasks)
    if args.json:
        print(json.dumps({"info": result.info, "errors": result.errors, "warnings": result.warnings}, ensure_ascii=False, indent=2))
    else:
        print(f"Пакет: {args.package}")
        for key, value in result.info.items():
            print(f"  {key}: {value}")
        for message in result.errors:
            print(f"ОШИБКА: {message}")
        for message in result.warnings:
            print(f"ПРЕДУПРЕЖДЕНИЕ: {message}")
        if not result.errors and not result.warnings:
            print("Проверка пройдена без замечаний.")

    return 1 if result.errors or (args.strict and result.warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
