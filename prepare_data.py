# -*- coding: utf-8 -*-
"""Подготовить 18 своих фотографий: python prepare_data.py raw --out data.

Исходники не меняются. Снимки сортируются по имени, получают имена 01..18.jpg,
уменьшаются до 2000 px и сохраняются размером строго меньше 1 МБ.
Разметку нужно делать ПОСЛЕ подготовки, на уже сохранённых изображениях.
"""
import argparse
import json
from pathlib import Path
import re
import tempfile

import cv2
import numpy as np


def natural_key(path):
    return [int(piece) if piece.isdigit() else piece.lower()
            for piece in re.split(r"(\d+)", path.name)]


def encode_photo(image):
    h, w = image.shape[:2]
    scale = min(1.0, 2000 / max(h, w))
    if scale < 1:
        image = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))),
                           interpolation=cv2.INTER_AREA)
    # Сначала меняем качество JPEG. Дополнительное уменьшение — только если нужно.
    while True:
        for quality in (95, 90, 85, 80, 75, 70, 65):
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if not ok:
                raise ValueError("OpenCV не смог сохранить JPEG")
            if buf.nbytes < 1_000_000:
                return buf, image.shape, quality
        h, w = image.shape[:2]
        image = cv2.resize(image, (max(1, round(w * 0.85)), max(1, round(h * 0.85))),
                           interpolation=cv2.INTER_AREA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="папка с 18 исходными JPG/JPEG/PNG")
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args()
    if not args.source.is_dir():
        parser.error("папка исходных фотографий не найдена")
    paths = sorted((p for p in args.source.iterdir()
                    if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}),
                   key=natural_key)
    if len(paths) != 18:
        parser.error(f"нужно ровно 18 фотографий, найдено {len(paths)}")
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / "corners.json").exists() or any(
            p.suffix.lower() in {".jpg", ".jpeg", ".png"} for p in args.out.iterdir()):
        parser.error("в папке назначения уже есть снимки или разметка; выбери новую папку --out")
    if (args.out / "source_files.json").exists():
        parser.error("в папке назначения уже есть source_files.json; выбери новую папку --out")
    mapping = []
    # Сначала готовим весь набор во временной папке: ошибка чтения не оставит полунабор.
    with tempfile.TemporaryDirectory(prefix="prepare_", dir=args.out) as tmp:
        staging = Path(tmp)
        for index, path in enumerate(paths, 1):
            image = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"не удалось прочитать {path.name}")
            buf, shape, quality = encode_photo(image)
            name = f"{index:02d}.jpg"
            buf.tofile(staging / name)
            mapping.append({"file": name, "source": path.name,
                            "width": shape[1], "height": shape[0],
                            "size_bytes": int(buf.nbytes), "jpeg_quality": quality})
        (staging / "source_files.json").write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for path in staging.iterdir():
            path.rename(args.out / path.name)
    for row in mapping:
        print(f"{row['source']} -> {row['file']}: {row['width']}x{row['height']}, {row['size_bytes']} bytes")
    print(f"\nГотово. Проверь порядок, затем разметь: python docscan.py annotate \"{args.out}\" --ann \"{args.out / 'corners.json'}\"")


if __name__ == "__main__":
    main()
