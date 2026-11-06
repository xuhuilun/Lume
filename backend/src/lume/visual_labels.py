"""Read target labels from the actual inspected image, never from index-derived OCR."""

import asyncio
import csv
import io
import re

from PIL import Image


async def read_labels(data, language):
    with Image.open(io.BytesIO(data)) as original:
        if original.width * original.height > 12_000_000:
            raise ValueError("Image exceeds label pixel limit")
        rgba = original.convert("RGBA")
        visible = Image.new("RGB", rgba.size, "white")
        visible.paste(
            rgba.convert("RGB"), mask=rgba.getchannel("A").point(lambda a: 255 if a == 255 else 0)
        )
        visible.thumbnail((1024, 1024))
    png = io.BytesIO()
    visible.save(png, format="PNG")
    try:
        process = await asyncio.create_subprocess_exec(
            "tesseract",
            "stdin",
            "stdout",
            "-l",
            language,
            "tsv",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return []
    try:
        async with asyncio.timeout(10):
            output, _ = await process.communicate(png.getvalue())
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise
    except TimeoutError:
        process.kill()
        await process.communicate()
        return []
    if process.returncode or len(output) > 1_000_000:
        return []
    return parse_labels(output.decode("utf-8", errors="replace"), *visible.size)


def parse_labels(tsv, width, height):
    labels = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        try:
            confidence = float(row["conf"])
            text = (row.get("text") or "").strip()
            x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            if row["level"] != "5" or not 60 <= confidence <= 100 or not 1 <= len(text) <= 100:
                continue
            if not (0 <= x < x + w <= width and 0 <= y < y + h <= height):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        labels.append(
            {
                "text": text,
                "confidence": confidence,
                "center": [(x + w / 2) / width * 1000, (y + h / 2) / height * 1000],
                "box": [
                    x / width * 1000,
                    y / height * 1000,
                    (x + w) / width * 1000,
                    (y + h) / height * 1000,
                ],
            }
        )
    return labels


def bind_target(question, candidates, labels):
    tokens = set(re.findall(r"[a-z][a-z0-9_-]*", question.casefold()))
    matches = []
    for container in candidates["containers"]:
        x1, y1, x2, y2 = container["box"]
        anchors = [
            label
            for label in labels
            if (
                label["text"].casefold() in tokens
                or (
                    len(label["text"]) >= 2
                    and re.fullmatch(r"[\u4e00-\u9fff]+", label["text"])
                    and label["text"] in question
                )
            )
            and x1 <= label["box"][0] < label["box"][2] <= x2
            and y1 <= label["box"][1] < label["box"][3] <= y2
        ]
        if anchors:
            matches.append(
                {**container, "label_anchor": max(anchors, key=lambda a: a["confidence"])}
            )
    if len(matches) != 1:
        return None, "TARGET_LABEL_UNBOUND" if not matches else "TARGET_LABEL_AMBIGUOUS"
    target = matches[0]
    if target["marker_count"] != 1:
        return None, "AMBIGUOUS_MARKERS"
    x1, y1, x2, y2 = target["box"]
    markers = [
        m
        for m in candidates["markers"]
        if x1 <= m["box"][0] < m["box"][2] <= x2 and y1 <= m["box"][1] < m["box"][3] <= y2
    ]
    if len(markers) != 1:
        return None, "TARGET_MARKER_NOT_AVAILABLE"
    return {"markers": markers, "containers": [target]}, None
