"""Pixel-bound measurements for colored markers in outlined UI components."""

import colorsys
import io
import re
from collections import deque
from typing import Literal

from PIL import Image
from pydantic import Field

from .schemas import Input


class GeneralVision(Input):
    kind: Literal["general"]
    text: str = Field(min_length=1, max_length=8000)


class MarkerVision(Input):
    kind: Literal["region_marker"]
    target: str = Field(min_length=1, max_length=100)
    container_id: str = Field(min_length=1, max_length=10)
    marker_id: str = Field(min_length=1, max_length=10)
    uncertain: bool


def marker_question(question):
    """Explicit, bounded intent routing, independent of dataset identities or answer values."""
    return bool(
        re.search(r"圆点|标记|指示灯|\b(?:dot|marker|indicator)\b", question, re.I)
        and re.search(r"颜色|什么色|左|右|位置|\b(?:colou?r|left|right|position)\b", question, re.I)
    )


def color_name(rgb):
    hue = colorsys.rgb_to_hsv(*(v / 255 for v in rgb))[0] * 360
    for limit, name in [
        (15, "红色"),
        (45, "橙色"),
        (70, "黄色"),
        (170, "绿色"),
        (200, "青色"),
        (260, "蓝色"),
        (290, "紫色"),
        (345, "粉色"),
        (361, "红色"),
    ]:
        if hue < limit:
            return name
    raise ValueError("Invalid color")


def connected_regions(mask, rgb, width, height):
    regions = []
    for start in range(len(mask)):
        if not mask[start]:
            continue
        mask[start] = 0
        queue = deque([start])
        area = 0
        left, right, top, bottom = width, 0, height, 0
        totals = [0, 0, 0]
        while queue:
            index = queue.popleft()
            y, x = divmod(index, width)
            area += 1
            left, right, top, bottom = min(left, x), max(right, x), min(top, y), max(bottom, y)
            for channel in range(3):
                totals[channel] += rgb[3 * index + channel]
            for nx in range(max(0, x - 1), min(width, x + 2)):
                for ny in range(max(0, y - 1), min(height, y + 2)):
                    neighbor = ny * width + nx
                    if mask[neighbor]:
                        mask[neighbor] = 0
                        queue.append(neighbor)
        bw, bh = right - left + 1, bottom - top + 1
        regions.append(
            {
                "center": [
                    round((left + right + 1) / 2 / width * 1000, 2),
                    round((top + bottom + 1) / 2 / height * 1000, 2),
                ],
                "box": [
                    round(left / width * 1000, 2),
                    round(top / height * 1000, 2),
                    round((right + 1) / width * 1000, 2),
                    round((bottom + 1) / height * 1000, 2),
                ],
                "pixels": area,
                "mean_rgb": [round(v / area, 2) for v in totals],
                "width": bw,
                "height": bh,
                "fill": area / (bw * bh),
            }
        )
    return regions


def pixel_candidates(data):
    with Image.open(io.BytesIO(data)) as original:
        if original.width * original.height > 12_000_000:
            raise ValueError("Image exceeds grounding pixel limit")
        rgba = original.convert("RGBA")
        rgba.thumbnail((768, 768))
        image = rgba.convert("RGB")
        alpha = rgba.getchannel("A").tobytes()
    width, height = image.size
    rgb = image.tobytes()
    hsv = image.convert("HSV").tobytes()
    colored = bytearray(
        a == 255 and s >= 120 and v >= 90
        for a, s, v in zip(alpha, hsv[1::3], hsv[2::3], strict=True)
    )
    neutral = bytearray(
        a == 255 and s <= 65 and 60 <= v <= 225
        for a, s, v in zip(alpha, hsv[1::3], hsv[2::3], strict=True)
    )
    minimum = max(24, int(width * height * 0.0001))
    markers = [
        r
        for r in connected_regions(colored, rgb, width, height)
        if minimum <= r["pixels"] <= width * height * 0.1
        and 0.5 <= r["width"] / r["height"] <= 2
        and r["fill"] >= 0.4
    ]
    containers = [
        r
        for r in connected_regions(neutral, rgb, width, height)
        if r["width"] >= width * 0.12
        and r["height"] >= height * 0.12
        and r["width"] * r["height"] >= width * height * 0.02
        and r["fill"] <= 0.2
    ]

    # Uniqueness is measured before prompt truncation, including hidden-from-prompt candidates.
    for container in containers:
        x1, y1, x2, y2 = container["box"]
        container["marker_count"] = sum(
            x1 <= m["box"][0] < m["box"][2] <= x2 and y1 <= m["box"][1] < m["box"][3] <= y2
            for m in markers
        )

    def bounded(items, prefix):
        items = sorted(
            sorted(items, key=lambda r: -r["pixels"])[:16],
            key=lambda r: (r["center"][1], r["center"][0]),
        )
        return [{"id": f"{prefix}{i}", **r} for i, r in enumerate(items, 1)]

    return {
        "markers": [{**r, "color": color_name(r["mean_rgb"])} for r in bounded(markers, "C")],
        "containers": bounded(containers, "R"),
    }


def vision_schema(candidates, require_marker=False):
    if not require_marker:
        return GeneralVision.model_json_schema()
    schema = MarkerVision.model_json_schema()
    schema["properties"]["marker_id"]["enum"] = [r["id"] for r in candidates["markers"]]
    schema["properties"]["container_id"]["enum"] = [r["id"] for r in candidates["containers"]]
    return schema


def interpret_vision(raw, candidates, require_marker=False):
    if not require_marker and raw.get("kind") == "general":
        parsed = GeneralVision.model_validate(raw)
        return {
            "text": parsed.text,
            "semantic": True,
            "grounding": {"method": "general-model-text"},
        }
    grounding = {"method": "outlined-marker-v2", "valid": False}

    def uncertain(reason):
        return {
            "text": "目标组件与标记未能可靠绑定，无法确定颜色和组件内部位置。",
            "semantic": False,
            "grounding": {**grounding, "reason": reason},
        }

    if raw.get("kind") != "region_marker":
        return uncertain("MARKER_GROUNDING_REQUIRED")
    parsed = MarkerVision.model_validate(raw)
    if parsed.uncertain:
        return uncertain("MODEL_UNCERTAIN")
    marker = next((r for r in candidates["markers"] if r["id"] == parsed.marker_id), None)
    container = next((r for r in candidates["containers"] if r["id"] == parsed.container_id), None)
    if not marker or not container:
        return uncertain("UNKNOWN_PIXEL_REGION")
    x1, y1, x2, y2 = container["box"]
    inside = [
        c
        for c in candidates["markers"]
        if x1 <= c["box"][0] < c["box"][2] <= x2 and y1 <= c["box"][1] < c["box"][3] <= y2
    ]
    if (
        container["marker_count"] != 1
        or len(inside) != 1
        or inside[0]["id"] != marker["id"]
        or container["width"] < marker["width"] * 2
        or container["height"] < marker["height"] * 2
    ):
        return uncertain("AMBIGUOUS_OR_OUTSIDE_MARKER")
    ratio = (marker["center"][0] - x1) / (x2 - x1)
    position = "左侧" if ratio < 0.4 else "右侧" if ratio > 0.6 else "中部"
    label = container.get("label_anchor", {}).get("text", "所选目标")
    text = f"{label}组件内的标记颜色为{marker['color']}，位于组件内部{position}。"
    return {
        "text": text,
        "semantic": True,
        "grounding": {
            **grounding,
            "valid": True,
            "model_target": parsed.target,
            "selected": marker,
            "container": container,
            "horizontal_ratio": round(ratio, 4),
            "position": position,
        },
    }
