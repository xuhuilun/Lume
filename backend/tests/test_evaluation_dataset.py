"""Offline regression checks protect draft data integrity; they do not judge model quality."""

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from scripts.evaluation_dataset import build, check, digest, dump, jsonl, read_rows, task_payload

DATASET = Path(__file__).resolve().parents[2] / "evaluation" / "dataset-v1"


@pytest.fixture
def bundle(tmp_path):
    result = tmp_path / "dataset"
    shutil.copytree(DATASET, result)
    return result


def reseal(root):
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["files"] = {
        p.relative_to(root).as_posix(): digest(p)
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    dump(root / "manifest.json", manifest)


def test_draft_bundle_is_intake_compatible_without_claiming_human_review_or_scores():
    result = check(DATASET)
    assert result["queries"] == 48 and result["message_input_checks"] == 72
    assert result["human_reviewed_queries"] == 0
    assert result["quality_scores_computed"] is False
    assert result["this_check_calls_models"] is False


def test_two_clean_builds_produce_identical_data_and_image_hashes(tmp_path):
    source = json.loads((DATASET / "source.json").read_text())
    a, b = tmp_path / "a", tmp_path / "b"
    build(source, a)
    build(source, b)
    ma = json.loads((a / "manifest.json").read_text())
    mb = json.loads((b / "manifest.json").read_text())
    assert ma == mb
    # Rebuild determinism is scoped to this environment, not arbitrary PNG encoder versions.
    assert check(a)["queries"] == check(b)["queries"] == 48


def test_task_request_excludes_query_identity_and_all_reference_metadata():
    query = read_rows(DATASET / "queries-dev.jsonl")[3]
    assert set(query) == {"id", "question", "scope_scenarios", "require_image"}
    assert "unanswerable" not in query["id"]
    payload = task_payload(query, {s: "runtime-" + s for s in query["scope_scenarios"]})
    assert set(payload) == {"question", "space_ids", "require_image"}
    assert query["id"] not in json.dumps(payload)
    with pytest.raises(ValueError, match="query contains label"):
        task_payload({**query, "category": "unanswerable"}, {})


@pytest.mark.parametrize(
    "damage, message",
    [
        ("label_in_query", "query contains label"),
        ("cross_split_scope", "cross-split query scope"),
        ("wrong_excerpt", "evidence excerpt mismatch"),
        ("out_of_scope_gold", "gold evidence outside query scope"),
        ("wrong_visual_truth", "visual truth differs"),
        ("tampered_marker", "visual marker pixel mismatch"),
        ("naive_timestamp", "timezone"),
        ("unanswerable_with_claim", "unanswerable reference contains"),
        ("false_review", "draft review status"),
        ("false_counts", "manifest declared counts"),
        ("unsafe_asset_path", "unsafe asset/manifest path"),
        ("family_leakage", "scenario family split leakage"),
        ("qrel_drift", "qrels mapping mismatch"),
        ("and_changed_to_or", "minimum evidence set does not cover"),
        ("fact_label_drift", "fact reference differs"),
    ],
)
def test_resealed_invalid_data_is_rejected_for_its_content(bundle, damage, message):
    # Recomputing hashes must not let invalid labels or protocol fields pass content checks.
    scenarios = json.loads((bundle / "scenarios.json").read_text())
    queries = read_rows(bundle / "queries-dev.jsonl")
    refs = read_rows(bundle / "references.jsonl")
    manifest = json.loads((bundle / "manifest.json").read_text())
    if damage == "label_in_query":
        queries[0]["reference_answer"] = "not allowed in model-facing input"
    elif damage == "cross_split_scope":
        queries[0]["scope_scenarios"].append("h-timezone")
    elif damage == "wrong_excerpt":
        refs[0]["claims"][0]["supports"][0]["excerpt"] = "not present in evidence"
    elif damage == "out_of_scope_gold":
        refs[0]["minimal_evidence_sets"] = [["h-timezone-m3"]]
    elif damage == "wrong_visual_truth":
        refs[2]["visual_assertions"][0]["color"] = "orange"
    elif damage == "tampered_marker":
        asset = scenarios["scenarios"][0]["assets"][0]
        path = bundle / asset["path"]
        with Image.open(path) as image:
            changed = image.convert("RGB")
            changed.putpixel((105, 315), (0, 0, 0))
            changed.save(path)
        asset["sha256"] = digest(path)
    elif damage == "naive_timestamp":
        scenarios["scenarios"][0]["messages"][0]["sent_at"] = "2026-11-03T01:00:00"
    elif damage == "unanswerable_with_claim":
        refs[3]["claims"] = refs[0]["claims"]
    elif damage == "false_review":
        manifest["human_review_status"], manifest["human_reviewed_queries"] = "approved", 48
    elif damage == "false_counts":
        manifest["counts"]["queries"] = 49
    elif damage == "unsafe_asset_path":
        scenarios["scenarios"][0]["assets"][0]["path"] = "../outside.png"
    elif damage == "family_leakage":
        scenarios["scenarios"][4]["family"] = scenarios["scenarios"][0]["family"]
    elif damage == "qrel_drift":
        path = bundle / "qrels.tsv"
        path.write_text("\n".join(path.read_text().splitlines()[1:]) + "\n")
    elif damage == "and_changed_to_or":
        refs[1]["minimal_evidence_sets"] = [[eid] for eid in refs[1]["minimal_evidence_sets"][0]]
    elif damage == "fact_label_drift":
        refs[0]["claims"][0]["text"] = "incorrect new value"
    dump(bundle / "scenarios.json", scenarios)
    dump(bundle / "manifest.json", manifest)
    jsonl(bundle / "queries-dev.jsonl", queries)
    jsonl(bundle / "references.jsonl", refs)
    reseal(bundle)
    with pytest.raises(ValueError, match=message):
        check(bundle)
