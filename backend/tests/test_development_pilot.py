import base64
import json
from pathlib import Path

import httpx
import pytest
from lume.config import Settings
from lume.providers import OllamaProvider

from scripts.development_pilot import (
    MODEL_NAMES,
    PilotProvider,
    audit_report,
    load_run_inputs,
    model_metadata,
    public_request,
)
from scripts.evaluation_dataset import digest, dump, jsonl

DATASET = Path(__file__).resolve().parents[2] / "evaluation" / "dataset-v1"


def test_run_loader_does_not_parse_reference_or_heldout_question_files(monkeypatch):
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert path.name not in {"source.json", "references.jsonl", "queries-heldout.jsonl"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    scenarios, queries = load_run_inputs(DATASET)
    assert len(scenarios) == 4 and len(queries) == 16
    assert all(s["split"] == "dev" for s in scenarios)
    assert all(q["id"].startswith("q-dev-") for q in queries)


def test_public_request_records_image_digest_without_mutating_actual_image_input():
    encoded = base64.b64encode(b"synthetic-image").decode()
    payload = {"messages": [{"role": "user", "content": "q", "images": [encoded]}]}
    public = public_request(payload)
    assert public["messages"][0]["images"][0]["byte_count"] == 15
    assert encoded not in json.dumps(public)
    assert payload["messages"][0]["images"] == [encoded]


async def test_recording_keeps_final_content_and_excludes_private_model_trace(
    tmp_path, monkeypatch
):
    async def response(self, endpoint, payload):
        return {
            "message": {"content": "{}", "thinking": "SYNTHETIC_PRIVATE_REASONING"},
            "eval_count": 1,
        }

    monkeypatch.setattr(OllamaProvider, "_post", response)
    report = {"calls": []}
    provider = PilotProvider(Settings(_env_file=None), report, tmp_path / "report.json")
    await provider._post("/api/chat", {"messages": [{"role": "user", "content": "q"}]})
    assert report["calls"][0]["response_content"] == "{}"
    assert "SYNTHETIC_PRIVATE_REASONING" not in json.dumps(report)


def fake_audit_input(root, category, groups, messages, image_observed=False, image_cited=False):
    root.mkdir(exist_ok=True)
    dump(root / "manifest.json", {})
    jsonl(root / "queries-dev.jsonl", [{"id": "q-dev-001", "question": "synthetic question"}])
    jsonl(
        root / "references.jsonl",
        [
            {
                "query_id": "q-dev-001",
                "split": "dev",
                "category": category,
                "minimal_evidence_sets": groups,
                "expected_state": "completed",
            }
        ],
    )
    observations = [
        {
            "id": "context",
            "kind": "message_context",
            "content": {"messages": [{"message_id": mid} for mid in messages]},
        }
    ]
    if image_observed:
        observations.append(
            {
                "id": "vision",
                "kind": "image_observation",
                "content": {"image_id": "image-runtime", "semantic": True},
            }
        )
    return {
        "dataset_manifest_sha256": digest(root / "manifest.json"),
        "source_commit": "synthetic",
        "sources": [
            {"message_id": "m1", "source_id": "s1"},
            {"message_id": "m2", "source_id": "s2"},
            {"message_id": "m3", "source_id": "s3"},
        ],
        "images": [{"id": "image-runtime", "asset_id": "image-asset"}],
        "tasks": [
            {
                "query_id": "q-dev-001",
                "status": {"state": "completed"},
                "question": "synthetic question",
                "observations": observations,
                "answer": {
                    "citation_ids": ["vision" if image_cited else "context"],
                    "text": "synthetic",
                },
            }
        ],
    }


@pytest.mark.parametrize(
    "observed,cited,expected_observed,expected_cited",
    [
        (False, False, False, False),
        (True, False, True, False),
        (True, True, True, True),
    ],
)
def test_audit_distinguishes_message_image_observation_and_actual_image_citation(
    tmp_path, observed, cited, expected_observed, expected_cited
):
    run = fake_audit_input(tmp_path, "visual", [["image-asset"]], ["m1"], observed, cited)
    row = audit_report(run, tmp_path)["rows"][0]
    assert row["draft_set_observed"] is expected_observed
    assert row["draft_set_cited"] is expected_cited


@pytest.mark.parametrize("messages,complete", [(["m1"], False), (["m3"], True)])
def test_audit_requires_all_members_of_one_alternative_set(tmp_path, messages, complete):
    run = fake_audit_input(tmp_path, "context", [["s1", "s2"], ["s3"]], messages)
    row = audit_report(run, tmp_path)["rows"][0]
    assert row["draft_set_observed"] is complete


def test_audit_rejects_answer_associated_with_a_different_question(tmp_path):
    run = fake_audit_input(tmp_path, "context", [["s1"]], ["m1"])
    run["tasks"][0]["question"] = "a different question"
    with pytest.raises(ValueError, match="audit question differs"):
        audit_report(run, tmp_path)


async def test_changed_model_digest_is_rejected_before_inference(tmp_path, monkeypatch):
    expected = [{"name": name, "digest": "original"} for name in sorted(MODEL_NAMES)]
    dump(tmp_path / "models.json", {"models": expected})
    observed = [{**m, "size": 1, "details": {}} for m in expected]
    observed[0]["digest"] = "changed"
    original = httpx.AsyncClient

    def transport(request):
        return httpx.Response(
            200,
            json={"version": "test"}
            if request.url.path == "/api/version"
            else {"models": observed},
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(transport)),
    )
    with pytest.raises(ValueError, match="frozen model weights mismatch"):
        await model_metadata("http://127.0.0.1:11435", tmp_path / "models.json")
