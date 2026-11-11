from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import zipfile

from kege_app.models import ExamPackage, Task, Variant
from kege_app.package_io import (
    choose_variant,
    control_sum,
    create_package,
    export_result,
    reencrypt_package_keys,
    validate_package,
    verify_activation,
)
from kege_app.security import hash_secret
from kege_app.storage import Storage
from kege_app.instructions import INSTRUCTION_SLIDES
from kege_app.resources import resource_path


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.asset = self.root / "condition.txt"
        self.asset.write_text("условие", encoding="utf-8")
        self.task = Task(id="t1", number=1, html="<b>Тест</b>", visual_assets=["assets/condition.txt"])
        self.exam = ExamPackage(
            id="exam-1", title="Тест", subject="Информатика", year=2026, duration_minutes=235,
            activation_code_hash=hash_secret("1597"), variants=[Variant("v1", "Вариант 1", [self.task])],
            answers={"v1": {"t1": "42"}},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_package_round_trip_and_encrypted_keys(self) -> None:
        package = self.root / "test.kege"
        create_package(package, self.exam, {"assets/condition.txt": self.asset}, "password-1")
        loaded = validate_package(package, "password-1")
        self.assertEqual(loaded.answers["v1"]["t1"], "42")
        with self.assertRaisesRegex(ValueError, "неверный пароль"):
            validate_package(package, "wrong")

    def test_password_reencryption(self) -> None:
        package = self.root / "test.kege"
        create_package(package, self.exam, {"assets/condition.txt": self.asset}, "password-1")
        reencrypt_package_keys(package, "password-1", "password-2")
        self.assertEqual(validate_package(package, "password-2").answers["v1"]["t1"], "42")
        with self.assertRaises(ValueError):
            validate_package(package, "password-1")

    def test_activation_and_checksum(self) -> None:
        self.assertTrue(verify_activation("1597", self.exam))
        self.assertFalse(verify_activation("1598", self.exam))
        first = control_sum("exam-1", "v1", "1234567890123", {"t1": "42"})
        second = control_sum("exam-1", "v1", "1234567890123", {"t1": "42"})
        self.assertEqual(first, second)
        self.assertRegex(first, r"^\d{2}(?:-\d{2}){4}$")

    def test_storage_and_result_export(self) -> None:
        package = self.root / "test.kege"
        create_package(package, self.exam, {"assets/condition.txt": self.asset}, "KEGE-2026")
        storage = Storage(self.root / "data")
        storage.import_exam(package, "KEGE-2026")
        self.assertEqual(storage.active_exam_row()["id"], "exam-1")
        record = {
            "exam_id": "exam-1", "exam_title": "Тест", "variant_id": "v1", "variant_name": "Вариант 1",
            "registration_no": "1234567890123", "kim_no": "00000001", "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00", "elapsed_seconds": 60, "checksum": "01-02-03-04-05",
            "answers": {"t1": "42"}, "status": "finished",
        }
        result_id = storage.save_result(record)
        loaded = storage.result(result_id)
        self.assertEqual(loaded["answers"], {"t1": "42"})
        storage.save_review(result_id, {
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "score": 1,
            "max_score": 1,
            "decisions": [{"task_id": "t1", "task_number": 1, "status": "correct", "points": 1, "max_points": 1, "comment": ""}],
            "comment": "Проверено",
        })
        loaded = storage.result(result_id)
        self.assertEqual(loaded["review"]["score"], 1)
        output = self.root / "answer.kege-result"
        export_result(output, loaded)
        self.assertTrue(output.exists())
        with zipfile.ZipFile(output) as archive:
            self.assertIn("review.csv", archive.namelist())

    def test_storage_can_remove_and_clear_results_and_packages(self) -> None:
        package = self.root / "test.kege"
        create_package(package, self.exam, {"assets/condition.txt": self.asset}, "KEGE-2026")
        storage = Storage(self.root / "data")
        storage.import_exam(package, "KEGE-2026")
        record = {
            "exam_id": "exam-1", "exam_title": "Тест", "variant_id": "v1", "variant_name": "Вариант 1",
            "registration_no": "1234567890123", "kim_no": "00000001", "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00", "elapsed_seconds": 60, "checksum": "01-02-03-04-05",
            "answers": {"t1": "42"}, "status": "finished",
        }
        first_id = storage.save_result(record)
        second_id = storage.save_result(record)
        storage.save_review(first_id, {
            "reviewed_at": datetime.now(timezone.utc).isoformat(), "score": 1, "max_score": 1,
            "decisions": [], "comment": "Проверено",
        })
        storage.remove_result(first_id)
        self.assertIsNone(storage.result(first_id))
        self.assertIsNotNone(storage.result(second_id))
        self.assertEqual(storage.clear_results(), 1)
        self.assertEqual(storage.results(), [])
        self.assertEqual(storage.clear_exams(), 1)
        self.assertEqual(storage.exams(), [])
        self.assertEqual(storage.setting("demo_bootstrapped"), "1")

    def test_required_ui_images_and_windows_bundle_config(self) -> None:
        self.assertEqual(len(INSTRUCTION_SLIDES), 8)
        for slide in INSTRUCTION_SLIDES:
            self.assertTrue(Path(slide["image"]).is_file(), slide["image"])
        self.assertTrue(resource_path("assets", "registration", "blank.png").is_file())
        self.assertTrue(resource_path("assets", "app_icon.png").is_file())
        self.assertTrue(resource_path("assets", "app_icon.ico").is_file())
        build_script = resource_path("build_windows.bat").read_text(encoding="utf-8")
        self.assertIn('--add-data "assets;assets"', build_script)
        self.assertIn('--icon "assets\\app_icon.ico"', build_script)


if __name__ == "__main__":
    unittest.main()
