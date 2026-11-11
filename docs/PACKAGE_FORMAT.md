# Формат пакета KEGE Station

`.kege` — ZIP-контейнер формата `kege-exam`, версия `1`.

## Структура

```text
manifest.json
expert/answer_keys.enc
assets/...
attachments/...
```

Исходные PDF не должны входить в пакет. Особенно запрещено вкладывать PDF, содержащий ответы.

## `manifest.json`

```json
{
  "format": "kege-exam",
  "format_version": 1,
  "id": "stable-exam-id",
  "title": "Название экзамена",
  "subject": "Информатика",
  "year": 2026,
  "duration_minutes": 235,
  "activation_code_hash": "pbkdf2_sha256$...",
  "source": "Источник и статус адаптации",
  "variants": [],
  "expert_keys": {
    "encrypted": true,
    "path": "expert/answer_keys.enc"
  }
}
```

`activation_code_hash` формируется функцией `hash_secret()`. Код активации открытым текстом не хранится.

## Вариант

```json
{
  "id": "variant-01",
  "name": "Вариант 1",
  "tasks": []
}
```

ID вариантов уникальны внутри пакета.

## Задание

```json
{
  "id": "variant-01-task-01",
  "number": 1,
  "title": "Задание 1",
  "html": "<html>...</html>",
  "answer_type": "short",
  "allowed_pattern": "^[0-9]+$",
  "max_length": 120,
  "table_rows": 0,
  "table_cols": 0,
  "visual_assets": [],
  "attachments": []
}
```

Допустимые типы ответа:

- `short` — одно текстовое поле;
- `table` — таблица, для которой `table_rows > 0` и `table_cols > 0`.

`allowed_pattern` — регулярное выражение Python, проверяющее весь краткий ответ.

## Вложения

```json
{
  "name": "3.ods",
  "path": "attachments/demo/v01/task03/3.ods"
}
```

Все пути должны быть относительными POSIX-путями без `..`. Каждый указанный файл обязан находиться в ZIP.

## Визуальные ресурсы

Путь добавляется в `visual_assets`, а внутри HTML используется URI:

```html
<img src="asset://assets/demo/v01/task01/graph.png">
```

Поддерживаются обычные форматы изображений, читаемые Qt. Предпочтительны SVG для схем и PNG для растровых фрагментов.

## Ключи ответов

`expert/answer_keys.enc` — JSON, зашифрованный AES-256-GCM. Ключ получается из пароля через PBKDF2-HMAC-SHA256. Создавать секцию вручную не нужно: используйте `create_package()`.

Логическая структура расшифрованных данных:

```json
{
  "variant-01": {
    "variant-01-task-01": "42",
    "variant-01-task-17": [["13", "136098"]]
  }
}
```

## Совместимость

Новые необязательные поля допустимы только так, чтобы старые версии приложения продолжали читать пакет. Изменение значения `format_version` требует отдельной миграции и поддержки в `ExamPackage.from_manifest()`.
