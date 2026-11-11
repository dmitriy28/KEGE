# Публикация проекта на GitHub

## Вариант 1: через сайт GitHub и Git

1. На GitHub создайте новый **публичный** репозиторий `KEGE-Station`.
2. Не добавляйте на сайте README, `.gitignore` и лицензию — они уже находятся в проекте.
3. В каталоге проекта выполните, заменив `YOUR_USERNAME`:

```bash
git init
git branch -M main
git add .
git status
git commit -m "Initial public release: KEGE Station 1.3.0"
git remote add origin https://github.com/YOUR_USERNAME/KEGE-Station.git
git push -u origin main
```

Чтобы запустить автоматическую Windows-сборку версии:

```bash
git tag -a v1.3.0 -m "KEGE Station 1.3.0"
git push origin v1.3.0
```

Готовая папка Windows появится на странице **Actions → Build Windows → Artifacts**.

## Вариант 2: через GitHub CLI

```bash
git init
git branch -M main
git add .
git commit -m "Initial public release: KEGE Station 1.3.0"
gh auth login
gh repo create KEGE-Station --public --source=. --remote=origin --push
git tag -a v1.3.0 -m "KEGE Station 1.3.0"
git push origin v1.3.0
```

Перед каждым коммитом проверяйте `git status`. В публичный репозиторий нельзя добавлять `.kege`, `.kege-result`, SQLite-базы, журналы и персональные данные учеников.
