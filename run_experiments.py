# -*- coding: utf-8 -*-
"""Воспроизводимый прогон ДЗ-2 через публичный CLI docscan.py.

Кадры курса: python run_experiments.py
Свои кадры: python run_experiments.py --personal --data data

Скрипт сохраняет настоящие JSON-ответы команд, таблицы и изображения.
REPORT.md не меняется: содержательные выводы и описание съёмки пишет автор.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parent
METHODS = ("contour", "hough", "auto")
SETTINGS = (("median", []), ("fixed", ["--canny", "50,150"]),
            ("no_close", ["--close", "0"]))


def read_image(path):
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Не удалось прочитать изображение: %s" % path)
    return image


def resolve_path(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def display_path(path):
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def validate_data(data, ann_path, personal):
    if not data.is_dir():
        raise ValueError("Нет папки с кадрами: %s" % data)
    if not ann_path.is_file():
        raise ValueError("Нет разметки %s. Сначала запустите annotate." % ann_path)
    ann = json.loads(ann_path.read_text(encoding="utf-8-sig"))
    if not isinstance(ann, dict):
        raise ValueError("corners.json должен содержать объект {имя файла: углы или null}.")
    # В ТЗ кадры — JPEG. page-gt.png курса — эталон страницы, не входной кадр.
    photos = sorted(p for p in data.iterdir() if p.is_file()
                    and p.suffix.lower() in (".jpg", ".jpeg"))
    if not photos:
        raise ValueError("В папке нет JPEG-кадров: %s" % data)
    missing = [p.name for p in photos if p.name not in ann]
    if missing:
        raise ValueError("Не размечены кадры: " + ", ".join(missing))
    if personal:
        expected = {"%02d.jpg" % n for n in range(1, 19)}
        if {p.name for p in photos} != expected:
            raise ValueError("Для --personal нужны ровно data/01.jpg … data/18.jpg.")
        if set(ann) != expected:
            raise ValueError("Для --personal corners.json должен содержать ровно имена 01.jpg … 18.jpg.")
    dimensions = {}
    for path in photos:
        image = read_image(path)
        height, width = image.shape[:2]
        dimensions[path.name] = {"width": width, "height": height,
                                 "bytes": path.stat().st_size}
        if personal and (max(height, width) > 2000 or path.stat().st_size > 1_000_000):
            raise ValueError("%s: нужно ≤ 2000 px и ≤ 1 000 000 байт." % path.name)
        if ann[path.name] is not None:
            points = np.asarray(ann[path.name], dtype=np.float64)
            if points.shape != (4, 2) or not np.isfinite(points).all():
                raise ValueError("%s: нужны четыре конечные пары [x, y]." % path.name)
            if (points[:, 0].min() < 0 or points[:, 0].max() > width - 1
                    or points[:, 1].min() < 0 or points[:, 1].max() > height - 1):
                raise ValueError("%s: размеченный угол вышел за изображение." % path.name)
            hull = cv2.convexHull(points.astype(np.float32))
            if len(hull) != 4 or cv2.contourArea(hull) <= 1:
                raise ValueError("%s: углы не образуют выпуклый четырёхугольник." % path.name)
    positives = [p for p in photos if ann[p.name] is not None]
    if personal and len(positives) != 15:
        raise ValueError("Нужны 15 кадров с четырьмя углами и 3 негативных с null.")
    if not positives:
        raise ValueError("Для полного эксперимента нужен хотя бы один кадр с листом.")
    return photos, positives, dimensions


def table(headers, rows):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(map(cell, headers)) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(map(cell, row)) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def write_results(meta, out):
    records = meta["commands"]
    def entries(section):
        return [r for r in records if r["section"] == section]
    def result(record):
        values = record["json"]
        return values[-1] if values else {}
    def ref(record):
        return "`%s`" % record["id"]
    text = ["# ДЗ-2: результаты воспроизводимого прогона\n",
            "**Тип набора:** " + meta["dataset_kind"] + ".\n",
            "**Источник:** `%s`; разметка: `%s`.\n" % (meta["data"], meta["annotations"]),
            "**Машина:** %s.\n" % meta["environment"]["label"],
            "**Среда:** Python %s, OpenCV %s, NumPy %s; %s.\n" % (
                meta["environment"]["python"], meta["environment"]["opencv"],
                meta["environment"]["numpy"], meta["environment"]["platform"]),
            "**Время запуска (UTC):** %s.\n" % meta["started_utc"],
            "Числа взяты из фактических JSON-ответов `docscan.py`. Полные ответы, stderr, "
            "коды возврата и точные аргументы — в `metrics.json`; команды с указанными "
            "ниже идентификаторами — в `commands.txt`. Время и FPS относятся к этой машине.\n"]
    if meta["personal"]:
        text.append("Проверены имена, размер, разрешение и наличие разметки 18 кадров: "
                    "15 с листом и 3 негативных. Авторство, условия освещения и разнообразие "
                    "сцен программа не определяет.\n")
    elif meta.get("course_data"):
        text.append("Это проверка на нарисованных кадрах курса. Она не заменяет требуемые "
                    "15 собственных фотографий с листом, 3 собственных негативных кадра "
                    "и локальную запись с веб-камеры.\n")
    else:
        text.append("Этот дополнительный набор не проходил проверку формата обязательных "
                    "18 собственных кадров (`--personal`). Происхождение снимков скрипт не определяет.\n")
    text += ["## 1. Шум\n", table(["Кадр", "σ шума", "Команда"], [
        (r["file"], result(r).get("noise_sigma", "ошибка"), ref(r)) for r in entries("noise")]),
        table(["Кадр", "Добавлено σ", "Оценка σ", "σ фильтра", "Остаток измеренный", "По формуле", "Команда"], [
            (r["file"], result(r).get("added_sigma", "—"), result(r).get("noise_sigma_noisy", "—"),
             result(r).get("filter_sigma", "—"), result(r).get("noise_after_measured", "—"),
             result(r).get("noise_after_predicted", "—"), ref(r)) for r in entries("added_noise")]),
        "## 2. Края\n", table(["Кадр", "Настройка", "Медиана", "Пороги", "Краёв, %", "Отрезков", "Команда"], [
            (r["file"], r["setting"], result(r).get("median", "—"), result(r).get("canny", "—"),
             result(r).get("edge_pct", "—"), result(r).get("segments", "—"), ref(r)) for r in entries("edges")]),
        "## 3. Оценка по набору\n",
        "`median`: пороги от медианы и закрытие 9; `fixed`: `--canny 50,150`; "
        "`no_close`: `--close 0` при порогах от медианы. Успех на кадре с листом — IoU ≥ 0.9; "
        "на негативном — отсутствие найденного четырёхугольника.\n"]
    summaries = []
    for r in entries("eval"):
        text.append("### %s — %s\n" % (r["setting"], ref(r)))
        rows = [value for value in r["json"] if "file" in value and "sheet" in value]
        def quality(row, method):
            return row[method + "_iou"] if row["sheet"] else ("ложное срабатывание" if row[method + "_found"] else "отклонён")
        text.append(table(["Кадр", "contour IoU", "hough IoU", "hough: успехи / %d" % meta["seeds"],
                           "auto IoU", "Путь auto", "мс: contour / hough / auto"], [
            (row["file"], quality(row, "contour"), quality(row, "hough"),
             row.get("hough_ok_of_%d" % meta["seeds"], "—"), quality(row, "auto"),
             row.get("auto_path") or "не найден", " / ".join(str(row[m + "_ms"]) for m in METHODS)) for row in rows]))
        for method, values in result(r).get("summary", {}).items():
            summaries.append((r["setting"], method, "%s / %s" % (values["found_iou_ok"], values["sheets"]),
                              values["mean_iou"], "%s / %s" % (values["rejected"], values["no_sheet"]),
                              values["mean_ms"], ref(r)))
    text += ["### Сводка\n", table(["Настройка", "Метод", "Листы: успехи", "Средний IoU", "Негативные: отклонены", "Среднее мс", "Команда"], summaries),
             "## 4. Выпрямление и бинаризация\n",
             "Для каждого положительного кадра используется один автоматический скан "
             "с `--method auto --canny 50,150`; затем три метода бинаризации применяются "
             "к одному выпрямленному изображению. Если лист не найден, ручные углы не подставляются.\n",
             table(["Кадр", "Лист найден", "Путь", "Размер W × H", "Команда"], [
                 (r["file"], result(r).get("found", False), result(r).get("path") or "—",
                  " × ".join(map(str, result(r).get("size_out", []))) or "—", ref(r)) for r in entries("scan")])]
    bins = []
    for r in entries("binarize") + entries("lamp"):
        for method in ("otsu", "adaptive", "flat"):
            values = result(r).get(method)
            if values:
                bins.append((r["file"], method, values["ink_pct"], values.get("match_pct", "нет эталона"), ref(r)))
    text += [table(["Кадр / страница", "Метод", "Чернил, %", "Совпадение с эталоном, %", "Команда"], bins),
             "## 5. Видео\n"]
    videos = entries("video")
    if videos:
        text.append("Видео из файла обрабатывается до конца без окна. Этот FPS измеряет "
                    "обработку файла на текущей машине, а не поток веб-камеры пользователя.\n")
        text.append(table(["Файл", "Метод", "Кадров", "FPS", "Кадров с листом, %", "Медиана detect, мс", "Команда"], [
            (r["file"], r["setting"], result(r).get("frames", "—"), result(r).get("fps", "—"),
             result(r).get("found_pct", "—"), result(r).get("detect_ms_median", "—"), ref(r)) for r in videos]))
    else:
        text.append("Видео в этом прогоне не измерялось. Для полного отчёта нужен локальный запуск "
                    "`docscan.py video --source 0` в трёх режимах и запись 10 секунд.\n")
    text.append("## 6. Пропуски и ошибки\n")
    issues = list(meta["notes"])
    issues += ["%s: код возврата %s. %s" % (r["id"], r["returncode"], r["stderr"].strip())
               for r in records if r["returncode"] != 0]
    text.append("\n".join("- " + issue for issue in issues) + "\n" if issues else "Команды завершились без ошибок.\n")
    (out / "RESULTS.md").write_text("\n".join(text), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="sample_data", help="папка JPEG-кадров")
    parser.add_argument("--ann", help="по умолчанию <data>/corners.json")
    parser.add_argument("--out", help="по умолчанию out/course или out/personal")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--personal", action="store_true", help="проверить формат обязательного набора из 18 кадров")
    parser.add_argument("--lamp-dir", default="sample_data/L3", help="каталог text-lamp.png и text-gt.png")
    parser.add_argument("--video", help="дополнительный видеофайл; по умолчанию clip.mp4 только для кадров курса")
    parser.add_argument("--machine-label", default="текущая машина", help="название машины для таблиц времени и FPS")
    args = parser.parse_args(argv)
    if args.seeds < 2:
        parser.error("--seeds должен быть не меньше 2 (для сдачи требуется 20).")
    data = resolve_path(args.data)
    ann_path = resolve_path(args.ann) if args.ann else data / "corners.json"
    out = resolve_path(args.out or ("out/personal" if args.personal else "out/course"))
    try:
        photos, positives, dimensions = validate_data(data, ann_path, args.personal)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    out.mkdir(parents=True, exist_ok=True)
    is_course = not args.personal and data == (ROOT / "sample_data").resolve()
    meta = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "dataset_kind": "собственные кадры (--personal; авторство не проверяется автоматически)" if args.personal
                            else ("нарисованные кадры курса (sample_data)" if is_course else "дополнительный набор"),
            "course_data": is_course,
            "personal": args.personal, "data": display_path(data), "annotations": display_path(ann_path),
            "seeds": args.seeds, "images": dimensions,
            "environment": {"label": args.machine_label, "python": platform.python_version(), "opencv": cv2.__version__,
                            "numpy": np.__version__, "platform": platform.platform(),
                            "processor": platform.processor(), "logical_cpus": os.cpu_count()},
            "notes": [], "commands": []}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    def save():
        # Чтение параллельно с прогоном увидит целый предыдущий или новый JSON.
        temporary = out / "metrics.partial.json"
        temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(out / "metrics.json")
        lines = ["# Выполнять из папки, содержащей docscan.py.\n# python — интерпретатор активированного окружения.\n"]
        for record in meta["commands"]:
            lines += ["# " + record["id"], record["command"]]
        temporary = out / "commands.partial.txt"
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(out / "commands.txt")

    def run(section, file, setting, cli):
        ident = "cmd%03d" % (len(meta["commands"]) + 1)
        argv_exact = [sys.executable, str(ROOT / "docscan.py")] + [str(value) for value in cli]
        portable = ["python", "docscan.py"] + [str(value) for value in cli]
        command = subprocess.list2cmdline(portable) if os.name == "nt" else shlex.join(portable)
        print("[%s] %s" % (ident, command), flush=True)
        process = subprocess.run(argv_exact, cwd=ROOT, env=env, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace")
        values = []
        for line in process.stdout.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    values.append(value)
            except json.JSONDecodeError:
                pass
        record = {"id": ident, "section": section, "file": file, "setting": setting,
                  "argv": argv_exact, "command": command, "returncode": process.returncode,
                  "stdout": process.stdout, "stderr": process.stderr, "json": values}
        meta["commands"].append(record)
        save()
        if process.returncode:
            print("  Команда завершилась с кодом %d; подробности в metrics.json." % process.returncode, flush=True)
        return record

    for path in photos:
        run("noise", path.name, "default", ["noise", display_path(path)])
    # На курсе добавка шума измерена именно для desk.jpg: удобно сверить числа.
    noise_photo = next((p for p in positives if p.name == "desk.jpg"), positives[0]) if is_course else positives[0]
    for sigma in (5, 10, 25):
        run("added_noise", noise_photo.name, str(sigma), ["noise", display_path(noise_photo), "--add-sigma", sigma])
    for path in positives:
        for setting, flags in SETTINGS:
            destination = out / "edges" / (path.stem + "_" + setting + ".png")
            run("edges", path.name, setting, ["edges", display_path(path)] + flags + ["-o", display_path(destination)])
    for setting, flags in SETTINGS:
        run("eval", display_path(data), setting,
            ["eval"] + [display_path(path) for path in photos] + ["--ann", display_path(ann_path), "--seeds", args.seeds]
            + flags + ["--csv", display_path(out / ("eval_" + setting + ".csv")),
                       "--overlays", display_path(out / ("eval_" + setting))])
    gt = data / "page-gt.png"
    gt_flags = ["--gt", display_path(gt)] if not args.personal and gt.is_file() else []
    for path in positives:
        # PNG сохраняет пиксели скана без дополнительной JPEG-компрессии.
        front = out / "scans" / (path.stem + "_scan.png")
        # Если повторный запуск не найдёт лист, результат прежнего успеха
        # не должен остаться рядом с новыми метриками как будто он актуален.
        generated = [front] + [out / "scans" / (path.stem + "_bw_" + method + ".png")
                               for method in ("otsu", "adaptive", "flat")]
        for old_file in generated:
            if old_file.is_file():
                old_file.unlink()
        record = run("scan", path.name, "fixed", ["scan", display_path(path), "--method", "auto",
                     "--canny", "50,150", "-o", display_path(front)])
        if record["returncode"] == 0 and record["json"] and record["json"][-1].get("found"):
            run("binarize", path.name, "same_rectification", ["binarize", display_path(front), "--method", "all"]
                + gt_flags + ["-o", display_path(out / "scans" / (path.stem + "_bw.png"))])
    lamp_dir = resolve_path(args.lamp_dir)
    if (lamp_dir / "text-lamp.png").is_file() and (lamp_dir / "text-gt.png").is_file():
        run("lamp", display_path(lamp_dir / "text-lamp.png"), "all", ["binarize", display_path(lamp_dir / "text-lamp.png"),
            "--gt", display_path(lamp_dir / "text-gt.png"), "-o", display_path(out / "lamp.png")])
    else:
        meta["notes"].append("Не найдены text-lamp.png и text-gt.png в %s; проверка L3 пропущена." % display_path(lamp_dir))
    video = resolve_path(args.video) if args.video else (data / "clip.mp4" if not args.personal else None)
    if video is not None and video.is_file():
        for method in METHODS:
            run("video", display_path(video), method, ["video", "--source", display_path(video), "--method", method,
                "--canny", "50,150", "--no-window", "--seconds", "0"])
    elif args.video:
        meta["notes"].append("Указанный видеофайл не найден: %s." % video)
    meta["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save()
    write_results(meta, out)
    unexpected = [r for r in meta["commands"] if r["returncode"] and not (
        r["section"] == "scan" and r["json"] and r["json"][-1].get("found") is False)]
    print("Готово: %s" % (out / "RESULTS.md"), flush=True)
    if unexpected:
        print("Есть ошибки команд: %s. Проверьте раздел 6 и metrics.json." % ", ".join(r["id"] for r in unexpected))
    return 1 if unexpected else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
