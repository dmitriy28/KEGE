#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
instruction_dir="$root/assets/instructions"
registration_dir="$root/assets/registration"
mkdir -p "$instruction_dir" "$registration_dir"

titles=("Перед началом экзамена" "Проверка регистрации" "Активация экзамена" "Навигация по заданиям" "Дополнительные файлы" "Краткий ответ" "Табличный ответ" "Завершение экзамена")
bodies=(
  "Подготовьте рабочее место. Закройте лишние программы и введите 13-значный номер тренировочного бланка."
  "Внимательно проверьте номер бланка и номер КИМ. Если обнаружена ошибка, вернитесь к регистрации."
  "Введите код, полученный от организатора или создателя тренировочного пакета. После активации запустится таймер."
  "Номера заданий расположены слева. Выполняйте их в любом порядке и сохраняйте каждый введённый ответ."
  "Кнопка файла открывает вложение в системной программе. Не перемещайте рабочие файлы до завершения."
  "Введите ответ без лишних символов и нажмите «Сохранить ответ». Сохранённое задание отмечается в списке."
  "Заполняйте ячейки по строкам. Данные из таблицы можно вставлять сочетанием Ctrl+V."
  "Проверьте список ответов, завершите экзамен и перенесите сформированную контрольную сумму."
)

for index in "${!titles[@]}"; do
  number=$(printf "%02d" "$((index + 1))")
  magick -size 1600x900 canvas:'#f4f7fb' \
    -fill '#19365f' -draw 'roundrectangle 45,45 1555,180 28,28' \
    -fill '#13b9ad' -draw 'roundrectangle 105,260 420,650 34,34' \
    -fill '#ffffff' -draw 'roundrectangle 165,325 360,470 18,18' \
    -fill '#19365f' -draw 'rectangle 220,485 305,505' \
    -fill '#19365f' -draw 'roundrectangle 185,505 340,535 12,12' \
    \( -background none -fill white -font DejaVu-Sans -pointsize 48 label:"${titles[$index]}" \) -gravity northwest -geometry +120+82 -composite \
    \( -background none -fill '#111827' -font DejaVu-Sans -pointsize 34 -size 930x360 caption:"${bodies[$index]}" \) -gravity northwest -geometry +520+285 -composite \
    -fill '#f59e0b' -draw "circle 1440,760 1440,710" \
    -fill white -font DejaVu-Sans-Bold -pointsize 38 -gravity northwest -annotate +1428+735 "$((index + 1))" \
    "$instruction_dir/$number.jpg"
done

magick -size 1200x700 canvas:'#ffffff' \
  -stroke '#19365f' -strokewidth 6 -fill none -draw 'roundrectangle 35,35 1165,665 28,28' \
  -fill '#19365f' -stroke none -font DejaVu-Sans-Bold -pointsize 42 -annotate +90+110 'ОБРАЗЕЦ ТРЕНИРОВОЧНОГО БЛАНКА' \
  -fill '#475569' -font DejaVu-Sans -pointsize 30 -annotate +90+190 'Номер бланка регистрации' \
  -stroke '#13b9ad' -strokewidth 4 -fill '#f8fafc' -draw 'roundrectangle 90,225 1110,360 18,18' \
  -fill '#111827' -stroke none -font DejaVu-Sans-Mono -pointsize 58 -annotate +145+315 '1  234567  890123' \
  -fill '#64748b' -font DejaVu-Sans -pointsize 28 -annotate +90+455 'Введите в программу все 13 цифр без пробелов.' \
  -fill '#e2e8f0' -draw 'roundrectangle 90,510 1110,590 14,14' \
  -fill '#475569' -font DejaVu-Sans -pointsize 26 -annotate +125+562 'Рисунок не является официальным экзаменационным бланком.' \
  "$registration_dir/blank.png"

echo "Public UI assets generated."
