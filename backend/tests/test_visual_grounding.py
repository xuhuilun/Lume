import io
import json

import pytest
from lume.config import Settings
from lume.providers import OllamaProvider
from lume.visual_grounding import interpret_vision, marker_question, pixel_candidates, vision_schema
from PIL import Image, ImageDraw


def marker_image():
    image = Image.new("RGB", (640, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 60, 310, 290), outline=(160, 160, 160), width=2)
    draw.rectangle((330, 60, 630, 290), outline=(160, 160, 160), width=2)
    draw.ellipse((240, 150, 280, 190), fill=(245, 89, 6))
    draw.ellipse((480, 150, 520, 190), fill=(37, 99, 235))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def test_marker_measurement_uses_pixels_and_component_relative_geometry(monkeypatch):
    async def labels(*args):
        return [
            {"text": "Status", "confidence": 95, "box": [30, 200, 140, 300], "center": [85, 250]}
        ]

    monkeypatch.setattr("lume.providers.read_labels", labels)
    provider = OllamaProvider(Settings(_env_file=None))

    async def reply(endpoint, payload):
        return {
            "message": {
                "content": json.dumps(
                    {
                        "kind": "region_marker",
                        "target": "状态组件",
                        "container_id": "R1",
                        "marker_id": "C1",
                        "uncertain": False,
                    }
                )
            }
        }

    monkeypatch.setattr(provider, "_post", reply)
    observation = await provider.vision("Status组件的标记颜色和组件内位置是什么？", marker_image())
    assert observation["grounding"]["selected"]["color"] == "橙色"
    assert observation["grounding"]["position"] == "右侧"
    assert observation["semantic"] is True


@pytest.mark.parametrize(
    "container,marker,uncertain,reason",
    [
        ("R2", "C1", False, "AMBIGUOUS_OR_OUTSIDE_MARKER"),
        ("unknown", "C1", False, "UNKNOWN_PIXEL_REGION"),
        ("R1", "unknown", False, "UNKNOWN_PIXEL_REGION"),
        ("R1", "C1", True, "MODEL_UNCERTAIN"),
    ],
)
def test_unbound_or_ambiguous_region_never_becomes_visual_fact(
    container, marker, uncertain, reason
):
    result = interpret_vision(
        {
            "kind": "region_marker",
            "target": "组件",
            "container_id": container,
            "marker_id": marker,
            "uncertain": uncertain,
        },
        pixel_candidates(marker_image()),
        True,
    )
    assert result["semantic"] is False
    assert result["grounding"]["reason"] == reason


def test_general_mode_cannot_bypass_required_marker_grounding():
    raw = {"kind": "general", "text": "标记是蓝色在左端。"}
    assert not interpret_vision(raw, pixel_candidates(marker_image()), True)["semantic"]
    assert interpret_vision(raw, {}, False)["text"] == raw["text"]
    assert vision_schema({}, False)["properties"]["kind"]["const"] == "general"


def test_detector_measures_pixels_and_caps_candidate_count():
    candidates = pixel_candidates(marker_image())
    assert len(candidates["markers"]) == 2 and len(candidates["containers"]) == 2
    assert [c["color"] for c in candidates["markers"]] == ["橙色", "蓝色"]
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    for row in range(5):
        for col in range(8):
            x, y = 10 + col * 45, 10 + row * 45
            draw.ellipse((x, y, x + 10, y + 10), fill="red")
    output = io.BytesIO()
    image.save(output, format="PNG")
    assert len(pixel_candidates(output.getvalue())["markers"]) == 16


def test_marker_intent_routing_is_independent_of_dataset_names():
    assert marker_question("Acme indicator color and position?")
    assert marker_question("控件的指示灯在左还是右？")
    assert not marker_question("图里的连接上限字段是什么？")


def test_multiple_markers_in_one_container_are_not_arbitrarily_chosen():
    candidates = pixel_candidates(marker_image())
    candidates["containers"][0]["box"] = [0, 0, 1000, 1000]
    result = interpret_vision(
        {
            "kind": "region_marker",
            "target": "组件",
            "container_id": "R1",
            "marker_id": "C1",
            "uncertain": False,
        },
        candidates,
        True,
    )
    assert not result["semantic"]


async def test_no_pixel_pair_returns_unavailable_instead_of_free_guess(monkeypatch):
    provider = OllamaProvider(Settings(_env_file=None))
    image = Image.new("RGB", (100, 100), "white")
    output = io.BytesIO()
    image.save(output, format="PNG")

    async def forbidden(*args, **kwargs):
        raise AssertionError("No model should invent a missing marker")

    monkeypatch.setattr(provider, "_post", forbidden)
    result = await provider.vision("指示灯是什么颜色？", output.getvalue())
    assert not result["semantic"] and result["grounding"]["reason"] == "NO_PIXEL_PAIR"
