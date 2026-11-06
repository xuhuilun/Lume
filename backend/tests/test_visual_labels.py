from lume.visual_grounding import pixel_candidates
from lume.visual_labels import bind_target, parse_labels

from .test_visual_grounding import marker_image


def label(text, box, confidence=90):
    return {
        "text": text,
        "box": box,
        "center": [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2],
        "confidence": confidence,
    }


def test_question_label_binds_right_container_independently_of_candidate_order():
    candidates = pixel_candidates(marker_image())
    bound, reason = bind_target(
        "Probe卡片圆点的颜色和位置",
        candidates,
        [label("Other", [40, 200, 150, 300]), label("Probe", [550, 200, 680, 300])],
    )
    assert not reason
    assert bound["containers"][0]["id"] == "R2"
    assert bound["markers"][0]["id"] == "C2"


def test_missing_or_ambiguous_target_label_cannot_be_guessed():
    candidates = pixel_candidates(marker_image())
    assert bind_target("Probe圆点颜色", candidates, [])[1] == "TARGET_LABEL_UNBOUND"
    labels = [label("Probe", [40, 200, 150, 300]), label("Probe", [550, 200, 680, 300])]
    assert bind_target("Probe圆点颜色", candidates, labels)[1] == "TARGET_LABEL_AMBIGUOUS"


def test_tsv_parser_rejects_low_confidence_and_invalid_pixel_bounds():
    header = "level\tleft\ttop\twidth\theight\tconf\ttext\n"
    rows = (
        "5\t10\t10\t20\t10\t95\tProbe\n"
        "5\t10\t10\t20\t10\t10\tWrong\n"
        "5\t-1\t0\t20\t10\t95\tOutside\n"
    )
    parsed = parse_labels(header + rows, 100, 100)
    assert [p["text"] for p in parsed] == ["Probe"]
    assert parsed[0]["box"] == [100, 100, 300, 200]
