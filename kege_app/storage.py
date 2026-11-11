from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .package_io import validate_package
from .security import hash_secret, verify_secret


DEFAULT_EXPERT_PASSWORD = "KEGE-2026"


class Storage:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.packages_dir = self.root / "packages"
        self.cache_dir = self.root / "cache"
        self.work_dir = self.root / "exam_files"
        for directory in (self.packages_dir, self.cache_dir, self.work_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "kege.sqlite3"
        self._init_database()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_database(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS exams (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    package_path TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_id TEXT NOT NULL,
                    exam_title TEXT NOT NULL,
                    variant_id TEXT NOT NULL,
                    variant_name TEXT NOT NULL,
                    registration_no TEXT NOT NULL,
                    kim_no TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    elapsed_seconds INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'finished'
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    result_id INTEGER PRIMARY KEY,
                    reviewed_at TEXT NOT NULL,
                    score REAL NOT NULL,
                    max_score REAL NOT NULL,
                    decisions_json TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(result_id) REFERENCES results(id) ON DELETE CASCADE
                );
                """
            )
            if db.execute("SELECT 1 FROM settings WHERE key='expert_password'").fetchone() is None:
                db.execute("INSERT INTO settings(key,value) VALUES('expert_password',?)", (hash_secret(DEFAULT_EXPERT_PASSWORD),))

    def setting(self, key: str, default: str = "") -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def verify_expert_password(self, password: str) -> bool:
        return verify_secret(password, self.setting("expert_password"))

    def change_expert_password(self, old_password: str, new_password: str) -> None:
        if not self.verify_expert_password(old_password):
            raise ValueError("Текущий пароль указан неверно")
        if len(new_password) < 8:
            raise ValueError("Новый пароль должен содержать не менее 8 символов")
        self.set_setting("expert_password", hash_secret(new_password))

    def import_exam(self, source: str | Path, password: str) -> str:
        source_path = Path(source)
        exam = validate_package(source_path, password)
        destination = self.packages_dir / f"{exam.id}.kege"
        if source_path.resolve() != destination.resolve():
            temporary = self.packages_dir / f".{exam.id}.importing"
            try:
                shutil.copy2(source_path, temporary)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            count = int(db.execute("SELECT COUNT(*) AS n FROM exams").fetchone()["n"])
            db.execute(
                """INSERT INTO exams(id,title,subject,year,package_path,source_name,imported_at,active)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,subject=excluded.subject,year=excluded.year,
                   package_path=excluded.package_path,source_name=excluded.source_name,imported_at=excluded.imported_at""",
                (exam.id, exam.title, exam.subject, exam.year, str(destination), source_path.name, now, 1 if count == 0 else 0),
            )
        return exam.id

    def exams(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM exams ORDER BY active DESC, imported_at DESC")]

    def active_exam_row(self) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM exams WHERE active=1 LIMIT 1").fetchone()
            return dict(row) if row else None

    def activate_exam(self, exam_id: str) -> None:
        with self.connect() as db:
            if db.execute("SELECT 1 FROM exams WHERE id=?", (exam_id,)).fetchone() is None:
                raise ValueError("Экзаменационный пакет не найден")
            db.execute("UPDATE exams SET active=0")
            db.execute("UPDATE exams SET active=1 WHERE id=?", (exam_id,))

    def remove_exam(self, exam_id: str) -> None:
        with self.connect() as db:
            row = db.execute("SELECT package_path,active FROM exams WHERE id=?", (exam_id,)).fetchone()
            if not row:
                return
            Path(row["package_path"]).unlink(missing_ok=True)
            db.execute("DELETE FROM exams WHERE id=?", (exam_id,))
            if row["active"]:
                next_row = db.execute("SELECT id FROM exams ORDER BY imported_at DESC LIMIT 1").fetchone()
                if next_row:
                    db.execute("UPDATE exams SET active=1 WHERE id=?", (next_row["id"],))
        self.set_setting("demo_bootstrapped", "1")

    def clear_exams(self) -> int:
        with self.connect() as db:
            rows = db.execute("SELECT package_path FROM exams").fetchall()
            db.execute("DELETE FROM exams")
        for row in rows:
            Path(row["package_path"]).unlink(missing_ok=True)
        self.set_setting("demo_bootstrapped", "1")
        return len(rows)

    def save_result(self, record: dict[str, Any]) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO results(exam_id,exam_title,variant_id,variant_name,registration_no,kim_no,
                   started_at,finished_at,elapsed_seconds,checksum,answers_json,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record["exam_id"], record["exam_title"], record["variant_id"], record["variant_name"],
                    record["registration_no"], record["kim_no"], record["started_at"], record["finished_at"],
                    record["elapsed_seconds"], record["checksum"], json.dumps(record["answers"], ensure_ascii=False),
                    record.get("status", "finished"),
                ),
            )
            return int(cursor.lastrowid)

    def results(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT results.*, reviews.reviewed_at, reviews.score AS review_score,
                   reviews.max_score AS review_max_score
                   FROM results LEFT JOIN reviews ON reviews.result_id=results.id
                   ORDER BY results.id DESC"""
            )]

    def remove_result(self, result_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM results WHERE id=?", (result_id,))

    def clear_results(self) -> int:
        with self.connect() as db:
            count = int(db.execute("SELECT COUNT(*) AS n FROM results").fetchone()["n"])
            db.execute("DELETE FROM results")
            db.execute("DELETE FROM sqlite_sequence WHERE name='results'")
        return count

    def result(self, result_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM results WHERE id=?", (result_id,)).fetchone()
            if not row:
                return None
            value = dict(row)
            value["answers"] = json.loads(value.pop("answers_json"))
            review = db.execute("SELECT * FROM reviews WHERE result_id=?", (result_id,)).fetchone()
            if review:
                review_value = dict(review)
                review_value["decisions"] = json.loads(review_value.pop("decisions_json"))
                value["review"] = review_value
            return value

    def save_review(self, result_id: int, review: dict[str, Any]) -> None:
        if self.result(result_id) is None:
            raise ValueError("Результат экзамена не найден")
        with self.connect() as db:
            db.execute(
                """INSERT INTO reviews(result_id,reviewed_at,score,max_score,decisions_json,comment)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(result_id) DO UPDATE SET reviewed_at=excluded.reviewed_at,
                   score=excluded.score,max_score=excluded.max_score,
                   decisions_json=excluded.decisions_json,comment=excluded.comment""",
                (
                    result_id,
                    review["reviewed_at"],
                    float(review["score"]),
                    float(review["max_score"]),
                    json.dumps(review["decisions"], ensure_ascii=False),
                    str(review.get("comment", "")),
                ),
            )
