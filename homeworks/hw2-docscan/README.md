# ДЗ 2: сканер документов

В проекте опубликованы сканер, тесты и результаты экспериментов:

- [18 собственных фотографий и разметка](data/), включая `01.jpg`–`18.jpg` и `corners.json`.
- [Измерения на собственном наборе](../../out/personal/RESULTS.md), [логи](../../out/personal/metrics.json), [команды](../../out/personal/commands.txt) и изображения в [`out/personal/`](../../out/personal/).
- [Запись с камеры](../../out/video.mp4) (1 436 448 байт).
- [Отчёт](REPORT.md) с результатами и ограничениями; [проверка CI](https://github.com/Mahan1341/cv-homework2/actions/runs/41528050154) завершилась успешно.

Учебные изображения [`sample_data/`](../../sample_data/) синтетические и хранятся отдельно от собственного набора.

## 1. Запуск

Все команды ниже выполняются **из корня репозитория** (там лежат
`prepare_data.py`, `run_experiments.py`, `sample_data/` и `out/`).
Сканер, зависимости, тесты и собственный набор находятся в `homeworks/hw2-docscan/`.
Можно использовать уже установленное окружение курса. Новое окружение в PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r homeworks/hw2-docscan/requirements.txt
.\.venv\Scripts\python.exe -m pytest homeworks/hw2-docscan/tests -q
```

Подойдёт и Python 3.10. Далее `python` означает интерпретатор этого окружения:
активируйте его или заменяйте `python` на `.\.venv\Scripts\python.exe`.

Пример — скан листа с закрытым углом:

```powershell
python homeworks/hw2-docscan/docscan.py scan sample_data/corner.jpg --canny 50,150 -o out/reproduced/demo_scan.jpg --bw out/reproduced/demo_bw.png
```

Измеренные результаты курса находятся в [`out/course/`](../../out/course/).
[REPORT.md](REPORT.md) описывает собственные измерения; [EXPLAIN.md](../../EXPLAIN.md)
помогает разобраться в коде. Полный повторный прогон описан в разделе 3.

## 2. Свои фотографии и подготовка нового набора

Опубликованный набор уже подготовлен и размечен: [описание и план](data/README.md).
Для его проверки повторная подготовка и разметка не нужны. Следующие команды —
только для **нового набора** из 18 исходных JPG/JPEG/PNG в папке `raw/`.
Удобно заранее назвать их `01.jpg` … `18.jpg` по плану.

```powershell
python prepare_data.py raw --out data_new
python homeworks/hw2-docscan/docscan.py annotate data_new --ann data_new/corners.json
```

Первый скрипт уменьшает длинную сторону до 2000 пикселей, каждый JPEG — до
размера меньше 1 МБ. Исходники сохраняются; соответствие имён записывается
в `data_new/source_files.json`. Если в папке назначения уже есть фото или разметка,
скрипт завершится с ошибкой и предложит выбрать другую папку, чтобы не затереть готовую работу.
Разметку нужно делать после уменьшения, на уже подготовленных фотографиях.

В окне разметки:

- Четыре клика по углам листа в произвольном порядке → **Enter**.
- Закрытый предметом угол: отметить предполагаемое положение угла.
- **r** — сбросить клики текущего кадра.
- **n** — один из трёх запланированных негативных кадров.

Обычный положительный кадр не становится негативным из-за ошибки программы.
Разметка сохраняется после каждого снимка. Исправить один кадр нового набора:

```powershell
python homeworks/hw2-docscan/docscan.py annotate data_new/07.jpg --ann data_new/corners.json --redo
```

## 3. Повторение измерений

В текущем дереве `run_experiments.py` ищет `docscan.py` рядом с собой через
`ROOT / "docscan.py"`. Поэтому прямой запуск корневого скрипта после переноса
сканера не работает. Без изменения исходного кода можно собрать временную
папку запуска. Этот блок PowerShell запускает оба набора; новые результаты
пишутся в отдельный каталог `out/reproduced/<идентификатор>/`:

```powershell
$repo = (Get-Location).Path
$runId = [guid]::NewGuid().ToString("N")
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("docscan-" + $runId)
$resultRoot = Join-Path $repo ("out/reproduced/" + $runId)
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    Copy-Item run_experiments.py -Destination $stage
    Copy-Item homeworks/hw2-docscan/docscan.py -Destination $stage
    Copy-Item sample_data -Destination $stage -Recurse
    python (Join-Path $stage "run_experiments.py") --data sample_data --out (Join-Path $resultRoot "course")
    if ($LASTEXITCODE -ne 0) { throw "Ошибка прогона курса: см. новые metrics.json и RESULTS.md" }
    python (Join-Path $stage "run_experiments.py") --data (Join-Path $repo "homeworks/hw2-docscan/data") --out (Join-Path $resultRoot "personal") --personal
    if ($LASTEXITCODE -ne 0) { throw "Ошибка личного прогона: см. новые metrics.json и RESULTS.md" }
} finally {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
```

Для нового набора во второй команде замените `homeworks/hw2-docscan/data` на
`data_new`. Скрипт проверяет имена, размеры, разрешение, полную разметку и
соотношение 15 положительных / 3 негативных. Затем оценивает шум, строит карты
краёв, делает три прогона `eval` с 20 зёрнами RANSAC и сравнивает бинаризацию.
Реальные отказы сохраняются в результатах. `REPORT.md` не перезаписывается.

Опубликованные [таблицы](../../out/personal/RESULTS.md) и [отчёт](REPORT.md)
уже содержат собственные измерения. По ним для поиска выбран
`--method auto --close 9 --long-side 640` с медианными порогами Canny
(без `--canny 50,150`). В полном прогоне также сохраняются сравнения с
50/150 и без закрытия текста; сканы в нём строятся с фиксированными 50/150.
Параметры не подбираются отдельно для каждого кадра по известной разметке.

## 4. Камера

Ролик уже опубликован: [out/video.mp4](../../out/video.mp4).
Измерения камеры и повторной обработки MP4 приведены в [отчёте](REPORT.md#7-видеорежим).
Ниже — команды для **новой** локальной записи. Во время записи двигайте лист, прикройте угол ладонью,
затем уберите лист. Номер камеры обычно `0`; при необходимости попробуйте `1`.

```powershell
python homeworks/hw2-docscan/docscan.py video --source 0 --method contour --seconds 10
python homeworks/hw2-docscan/docscan.py video --source 0 --method hough --seconds 10
python homeworks/hw2-docscan/docscan.py video --source 0 --method auto --seconds 10 --long-side 480 --save out/reproduced/video-new.mp4
```

Для нового измерения сохраните JSON-ответы и характеристики машины отдельно.
Опубликованные значения в отчёте относятся к прежним прогонам.
Требование к `auto`: не менее 10 FPS на вашем компьютере. Если медленно,
попробуйте `--long-side 480` и заново сравните режимы с одной настройкой.
`fps` относится к циклу обработки; `finalize_seconds` — к отдельному
сохранению ролика после захвата. Для камеры частота записи согласуется
с измеренной длительностью. Реальная камера в серверной проверке не использовалась.

Проверьте размер ролика: не больше 10 МБ. При необходимости уменьшите
разрешение самой камеры. `--long-side` уменьшает кадр для поиска,
но не разрешение сохраняемого видео.


