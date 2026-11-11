from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kege_app.models import ExamPackage, Task, Variant
from kege_app.package_io import create_package
from kege_app.security import hash_secret


def build(output: Path, password: str, activation_code: str) -> Path:
    tasks = [
        Task(
            id="example-v01-task-01",
            number=1,
            title="Задание 1",
            html=(
                "<html><body><p>Вычислите значение выражения: "
                "<b>6 × 7</b>.</p></body></html>"
            ),
            answer_type="short",
            allowed_pattern=r"^[0-9]+$",
            max_length=10,
        ),
        Task(
            id="example-v01-task-02",
            number=2,
            title="Задание 2",
            html=(
                "<html><body><p>Запишите в таблицу числа 10 и 20.</p>"
                "<table><tr><th>Первое</th><th>Второе</th></tr>"
                "<tr><td>?</td><td>?</td></tr></table></body></html>"
            ),
            answer_type="table",
            table_rows=1,
            table_cols=2,
        ),
    ]
    variant = Variant(id="example-v01", name="Пример варианта", tasks=tasks)
    exam = ExamPackage(
        id="kege-public-example",
        title="Минимальный пример пакета",
        subject="Информатика",
        year=2026,
        duration_minutes=30,
        activation_code_hash=hash_secret(activation_code),
        variants=[variant],
        source="Собственный демонстрационный материал проекта KEGE Station.",
        answers={
            "example-v01": {
                "example-v01-task-01": "42",
                "example-v01-task-02": [["10", "20"]],
            }
        },
    )
    return create_package(output, exam, source_files={}, password=password)


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать минимальный учебный пакет KEGE Station")
    parser.add_argument("output", type=Path)
    parser.add_argument("--password", required=True, help="Пароль шифрования ключей")
    parser.add_argument("--activation-code", default="1597")
    args = parser.parse_args()
    result = build(args.output, args.password, args.activation_code)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
