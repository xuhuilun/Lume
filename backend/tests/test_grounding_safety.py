"""Original pixel fixtures for ambiguity and alpha-channel grounding boundaries."""

import io

from lume.visual_grounding import interpret_vision, pixel_candidates
from PIL import Image, ImageDraw


def png_bytes(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_candidate_cap_does_not_hide_another_marker_in_selected_container():
    image = Image.new("RGB", (1000, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 100, 300, 500), outline=(160, 160, 160), width=2)
    # Both points satisfy the pixel detector's minimum area. The smaller one
    # must still make this container ambiguous when the prompt list is capped.
    draw.ellipse((88, 288, 112, 312), fill=(245, 89, 6))
    draw.ellipse((193, 293, 207, 307), fill=(37, 99, 235))
    for row in range(3):
        for column in range(5):
            x, y = 400 + column * 110, 150 + row * 150
            draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(124, 58, 237))

    candidates = pixel_candidates(png_bytes(image))
    selected = next(marker for marker in candidates["markers"] if marker["box"][2] < 300)
    observation = interpret_vision(
        {
            "kind": "region_marker",
            "target": "Probe",
            "container_id": "R1",
            "marker_id": selected["id"],
            "uncertain": False,
        },
        candidates,
        True,
    )
    assert observation["semantic"] is False


def test_fully_transparent_hidden_regions_cannot_produce_visible_pixel_facts():
    image = Image.new("RGBA", (640, 360), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 60, 310, 290), outline=(160, 160, 160, 0), width=2)
    draw.ellipse((240, 150, 280, 190), fill=(245, 89, 6, 0))

    observation = interpret_vision(
        {
            "kind": "region_marker",
            "target": "Probe",
            "container_id": "R1",
            "marker_id": "C1",
            "uncertain": False,
        },
        pixel_candidates(png_bytes(image)),
        True,
    )
    assert observation["semantic"] is False
