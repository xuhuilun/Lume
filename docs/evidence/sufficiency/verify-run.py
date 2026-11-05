"""Check captured run artifacts only; this is not semantic or human quality scoring.

Run from the frozen Lume environment:
    uv run --frozen python ../outputs/lume-sufficiency/verify-run.py

No reference labels, heldout questions, live database or model endpoints are read.
"""

import argparse
import hashlib
import inspect
import json
import subprocess
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from lume.evidence import INSUFFICIENT_TEXT, render_evidence, selected_sources
from lume.schemas import EvidenceSelection
from lume.sufficiency import CONTRACT, review_binding, scope_constraints, validate_assessment

BASELINE = "dc77d0e0417264a09a31a520f14e491f489b0425"
MODEL_KINDS = {"model", "embedding", "vision", "support_review"}
TOOL_KINDS = {"search", "read_context", "inspect_image"}
TERMINAL = {"completed", "insufficient", "failed", "limited", "cancelled"}
ROOT = Path(__file__).resolve().parent


def require(condition, description):
    if not condition:
        raise ValueError(description)


def dependencies(rows):
    return {(d["message_id"], d["version"]) for row in rows for d in row["dependencies"]}


def source_ids(sources, source_map, image_map):
    return sorted({
        source_map[s["message_id"]]["source_id"] if s["message_id"]
        else image_map[s["observation_id"]]
        for s in sources
    })


def verify(path, executor):
    run = json.loads(path.read_text())
    require("finished_at" in run, "run has not finished")
    require(not run.get("fatal_error"), "run stopped before a complete terminal execution")
    require(run["application_baseline"] == BASELINE, "unexpected application baseline")
    require(run["source_dirty"] is False, "execution did not start clean")
    require(run["isolated_schema_removed"] is True, "isolated schema cleanup is unconfirmed")
    require(run["heldout_queries_executed"] == 0, "heldout execution declaration changed")
    require(run["offline_labels_parsed_during_run"] is False, "execution label boundary changed")
    require(len(run["tasks"]) == 16, "expected exactly 16 recorded development tasks")
    require(len({t["query_id"] for t in run["tasks"]}) == 16, "duplicate query execution")
    require(all(t["query_id"].startswith("q-dev-") for t in run["tasks"]), "non-development query")
    require(executor.exists(), "save the frozen executor snapshot before verifying provenance")
    require(hashlib.sha256(executor.read_bytes()).hexdigest() == run["script_sha256"],
            "executor snapshot digest differs from execution record")
    # The checks import pure helpers. Make their correspondence to the frozen code explicit.
    project = Path(inspect.getfile(selected_sources)).resolve().parents[3]
    difference = subprocess.check_output([
        "git", "diff", BASELINE, "--", "backend/src/lume/evidence.py",
        "backend/src/lume/sufficiency.py",
    ], cwd=project)
    require(not difference, "imported verification helpers differ from the frozen application")

    source_map = {s["message_id"]: s for s in run["sources"]}
    asset_map = {i["id"]: i["asset_id"] for i in run["images"]}
    owner_map, per_task = {}, []
    totals = Counter()
    for task in run["tasks"]:
        qid, task_id = task["query_id"], task["task_id"]
        status, config = task["status"], task["task_configuration"]
        state = status["state"]
        require(state in TERMINAL, f"{qid}: task remained nonterminal")
        require(not task.get("harness_error"), f"{qid}: harness could not capture complete artifacts")
        require(status["id"] == task_id, f"{qid}: status belongs to another task")
        require(status["question"] == task["question"], f"{qid}: question differs across API records")
        require(config["answer_contract"] == CONTRACT, f"{qid}: frozen answer contract changed")
        require(config["require_image"] == task["require_image"], f"{qid}: image requirement changed")
        require(config["rules_id"] == run["configuration"]["rules_id"], f"{qid}: rules mismatch")
        observations = {}
        for raw in task["observations"]:
            require(raw["id"] not in owner_map, f"{qid}: duplicate observation identity")
            owner_map[raw["id"]] = task_id
            # Ownership is reconstructed from the report's per-task SQL grouping, not a live DB.
            observations[raw["id"]] = SimpleNamespace(**raw, task_id=task_id)
        scope = set(task["requested_scope"])
        deps = dependencies(task["observations"])
        for mid, version in deps:
            require(mid in source_map and source_map[mid]["space_id"] in scope,
                    f"{qid}: observation dependency outside frozen scope")
            require(source_map[mid]["version"] == version, f"{qid}: dependency version mismatch")
        for ob in observations.values():
            if ob.kind == "message_context":
                for message in ob.content["messages"]:
                    source = source_map[message["message_id"]]
                    require(message["space_id"] in scope and message["space_id"] == source["space_id"],
                            f"{qid}: message context scope mismatch")
                    require(message["version"] == source["version"], f"{qid}: context version mismatch")
        image_ids = {o.id: asset_map[o.content["image_id"]] for o in observations.values()
                     if o.kind == "image_observation"}
        model_actions = [a for a in task["actions"] if a["kind"] in MODEL_KINDS]
        tool_actions = [a for a in task["actions"] if a["kind"] in TOOL_KINDS]
        require(len(model_actions) + len(tool_actions) == len(task["actions"]),
                f"{qid}: unclassified action kind")
        require(status["model_calls"] == len(model_actions) <= config["max_model_calls"],
                f"{qid}: cumulative model accounting mismatch")
        require(status["tool_calls"] == len(tool_actions) <= config["max_tool_calls"],
                f"{qid}: cumulative tool accounting mismatch")
        require(status["image_calls"] == sum(a["kind"] == "vision" for a in model_actions)
                <= config["max_image_calls"], f"{qid}: image accounting mismatch")
        task_calls = [c for c in run["calls"] if c.get("query_id") == qid and c["phase"] == "task"]
        require(len(task_calls) <= len(model_actions), f"{qid}: unaccounted model HTTP call")
        review_actions = sum(a["kind"] == "support_review" for a in model_actions)
        review_http = sum(c["purpose"] == "support_review" for c in task_calls)
        require(review_http <= review_actions, f"{qid}: review HTTP call bypassed model accounting")
        checked_reviews, proposed = [], set()
        for ob in observations.values():
            if ob.kind != "support_review":
                continue
            content = ob.content
            selections = [EvidenceSelection.model_validate(s) for s in content["selections"]]
            sources = selected_sources(task_id, selections, observations)
            proposed.update(source_ids(sources, source_map, image_ids))
            require(content["contract"] == CONTRACT, f"{qid}: review contract mismatch")
            require(content["binding"] == review_binding(task["question"], task["require_image"], sources),
                    f"{qid}: review does not bind the question and exact selected sources")
            canonical, issues, accepted = validate_assessment(content["assessment"], sources, task["question"])
            require(content["valid"] is (not issues) and content["issues"] == issues,
                    f"{qid}: recorded format/quote verdict differs from recomputation")
            require(content["accepted"] is accepted, f"{qid}: recorded acceptance differs")
            require(content["scope_constraints"] == scope_constraints(task["question"], sources),
                    f"{qid}: explicit scope veto differs")
            require(canonical == content["assessment"], f"{qid}: canonical assessment differs")
            checked_reviews.append((content, sources, selections))
            totals["valid_review_rejections" if not issues and not accepted else
                   "valid_review_acceptances" if not issues else "invalid_reviews"] += 1
        require(len(checked_reviews) <= review_http, f"{qid}: review observation lacks HTTP attempt")
        answer, published, image_cited = task.get("answer"), [], False
        if state in {"completed", "insufficient"}:
            require(answer is not None and task["answer_read_http_status"] == 200,
                    f"{qid}: published answer could not be read")
            require(deps <= dependencies([answer]), f"{qid}: answer omitted input dependencies")
            require(set(answer["citation_ids"]) <= set(observations), f"{qid}: citation outside task")
            require(all(observations[c].kind in {"message_context", "image_observation"}
                        for c in answer["citation_ids"]), f"{qid}: review/candidate cited as source")
        else:
            require(answer is None and not status.get("answer_id"), f"{qid}: failed task published an answer")
        if state == "completed":
            require(checked_reviews, f"{qid}: normal answer omitted independent review")
            content, sources, selections = checked_reviews[-1]
            require(content["valid"] and content["accepted"], f"{qid}: normal answer bypassed review")
            final = task["model_decisions"][-1]
            require(final["kind"] == "final" and not final.get("insufficient", False),
                    f"{qid}: normal answer has no normal proposal")
            proposed_selections = [EvidenceSelection.model_validate(s) for s in final["evidence"]]
            require(proposed_selections == selections, f"{qid}: proposal changed after review")
            expected_text, expected_citations = render_evidence(task_id, selections, observations)
            require(answer["text"] == expected_text and answer["citation_ids"] == expected_citations,
                    f"{qid}: answer differs from whole stored selected evidence")
            published = source_ids(sources, source_map, image_ids)
            image_cited = any(s["kind"] == "image_observation" for s in sources)
            require(not task["require_image"] or image_cited, f"{qid}: required image omitted")
            totals["normal_answers_equal_selected_stored_sources"] += 1
        if state == "insufficient":
            require(answer["text"] == INSUFFICIENT_TEXT and not answer["citation_ids"],
                    f"{qid}: insufficient answer contains unsupported free prose")
            if checked_reviews:
                require(checked_reviews[-1][0]["valid"] and not checked_reviews[-1][0]["accepted"],
                        f"{qid}: invalid/accepted review was mislabeled as insufficient")
                totals["insufficient_after_valid_review"] += 1
            else:
                totals["planner_declared_insufficient_without_review"] += 1
        if status.get("error") == "SUPPORT_REVIEW_INVALID":
            require(state == "failed" and checked_reviews and not checked_reviews[-1][0]["valid"],
                    f"{qid}: malformed review was not kept distinct")
            totals["failed_invalid_review_tasks"] += 1
        per_task.append({
            "query_id": qid, "state": state, "error": status.get("error"),
            "proposed_evidence_ids": sorted(proposed), "published_evidence_ids": published,
            "review_actions_in_model_budget": review_actions, "review_http_calls": review_http,
            "review_verdicts": [{k: r[0][k] for k in ["valid", "accepted", "issues", "scope_constraints"]}
                                for r in checked_reviews],
            "model_calls": status["model_calls"], "tool_calls": status["tool_calls"],
            "image_calls": status["image_calls"], "image_selected_in_published_answer": image_cited,
            "reserved_model_attempts_without_recorded_http": len(model_actions) - len(task_calls),
        })
    require(run["state_counts"] == dict(Counter(t["state"] for t in per_task)),
            "recorded state totals differ from task records")
    payloads = json.dumps([c["request"] for c in run["calls"]], ensure_ascii=False)
    require(not any(s in payloads for s in ["q-dev-", "q-heldout-", "minimal_evidence_sets",
                                           "expected_state", "Authorization", "Bearer "]),
            "model payload contains external query labels or credential fields")
    return {
        "scope": "captured artifact identity, source rendering, review binding and budget consistency only",
        "source_commit": run["source_commit"], "application_baseline": run["application_baseline"],
        "dataset_manifest_sha256": run["dataset_manifest_sha256"],
        "complete_terminal_run": True, "task_states": dict(Counter(t["state"] for t in per_task)),
        "calls": len(run["calls"]), "calls_by_purpose": dict(Counter(c["purpose"] for c in run["calls"])),
        "call_states": dict(Counter(c.get("status", "not_returned") for c in run["calls"])),
        "maximum_prompt_eval_count": max(c.get("usage", {}).get("prompt_eval_count", 0) for c in run["calls"]),
        "maximum_task_elapsed_seconds": max(t["elapsed_seconds"] for t in run["tasks"]),
        "checks": dict(totals), "per_task": per_task,
        "executor_snapshot_digest_matches": True, "imported_helpers_match_frozen_application": True,
        "human_reviewed_queries": 0, "heldout_queries_executed": 0, "quality_scores_computed": False,
        "limits": [
            "Task/observation ownership is checked from per-task SQL report grouping; no cleaned live database is queried.",
            "Exact quotes and literal environment veto do not prove semantic entailment or correct pixels.",
            "No reference labels or heldout files are read; human review and quality scores are not performed.",
            "Call budget accounting is checked against logged persisted actions, not an independent HTTP capture.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT / "run-06-reviewed-complete.json")
    parser.add_argument("--executor", type=Path, default=ROOT / "run-06-executor.py")
    parser.add_argument("--output", type=Path, default=ROOT / "execution-verification.json")
    args = parser.parse_args()
    result = verify(args.run, args.executor)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"task_states": result["task_states"], "checks": result["checks"],
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
