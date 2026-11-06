"""Structural export tests using invented placeholders, never real answers."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "export_human_review", Path(__file__).with_name("export_human_review.py")
)
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class HumanReviewExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dataset = self.root / "dataset"
        self.output = self.root / "packet"
        (self.dataset / "assets").mkdir(parents=True)
        self.scenarios = []
        self.source_scenarios = []
        self.references = []
        for split in EXPORT.SPLITS:
            sid, mid, aid, qid = (
                f"{split}-{kind}" for kind in ("scenario", "message", "asset", "query")
            )
            asset_path = f"assets/{split}.png"
            (self.dataset / asset_path).write_bytes(b"structural-fixture-only-" + split.encode())
            self.scenarios.append(
                {
                    "id": sid,
                    "family": "placeholder",
                    "split": split,
                    "title": "Synthetic fixture",
                    "messages": [
                        {
                            "source_id": mid,
                            "text": "Original ``` [literal](missing.txt)\nmessage",
                            "sent_at": "2026-01-01T00:00:00+00:00",
                            "author": "fixture",
                            "reply_to": None,
                            "images": [{"asset_id": aid}],
                        }
                    ],
                    "assets": [
                        {
                            "id": aid,
                            "message_source_id": mid,
                            "path": asset_path,
                            "filename": "fixture.png",
                            "sha256": EXPORT.sha256(self.dataset / asset_path),
                        }
                    ],
                }
            )
            self.source_scenarios.append({"id": sid, "panel": {"label": "fixture", "side": "left"}})
            self.references.append(
                {
                    "query_id": qid,
                    "scenario_id": sid,
                    "split": split,
                    "category": "fixture",
                    "answerable": True,
                    "expected_state": "fixture",
                    "claims": [
                        {
                            "text": "Uninterpreted fixture draft",
                            "supports": [{"evidence_id": mid, "excerpt": "Original"}],
                        }
                    ],
                    "minimal_evidence_sets": [[mid, aid]],
                    "visual_assertions": [],
                    "insufficient_reason": None,
                    "reason_kind": None,
                    "forbidden_evidence_ids": [],
                    "review_status": "pending",
                }
            )
            self.write_jsonl(
                f"queries-{split}.jsonl",
                [
                    {
                        "id": qid,
                        "question": "Original fixture question?",
                        "require_image": True,
                        "scope_scenarios": [sid],
                    }
                ],
            )
        self.write_json("scenarios.json", {"scenarios": self.scenarios})
        self.write_json(
            "source.json",
            {
                "dataset_id": "structural-fixture",
                "provenance": "synthetic fixture",
                "human_review_status": "pending",
                "human_reviewed_queries": 0,
                "scenarios": self.source_scenarios,
            },
        )
        self.write_json(
            "manifest.json",
            {
                "human_review_status": "pending",
                "human_reviewed_queries": 0,
                "counts": {
                    "queries": 2,
                    "splits": {"dev": 1, "heldout": 1},
                    "scenarios": 2,
                    "messages": 2,
                    "images": 2,
                },
            },
        )
        self.write_jsonl("references.jsonl", self.references)

    def write_json(self, name, value):
        (self.dataset / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def write_jsonl(self, name, values):
        (self.dataset / name).write_text(
            "\n".join(json.dumps(value, ensure_ascii=False) for value in values) + "\n",
            encoding="utf-8",
        )

    def test_export_preserves_source_records_images_and_pending_fields(self):
        before = EXPORT.source_hashes(self.dataset)
        manifest = EXPORT.export_packet(self.dataset, self.output)
        self.assertEqual(EXPORT.source_hashes(self.dataset), before)
        self.assertEqual(manifest["human_reviewed_queries"], 0)
        self.assertFalse(manifest["blind_evaluation"])
        self.assertEqual(manifest["target_model_calls"], 0)
        self.assertEqual(manifest["questions_executed"], 0)
        self.assertEqual(manifest["references_file_sha256"], before["references.jsonl"])
        self.assertEqual(len(manifest["reference_records"]), 2)
        for split in EXPORT.SPLITS:
            review = (self.output / f"review-{split}.md").read_text(encoding="utf-8")
            evidence = (self.output / f"evidence-{split}.md").read_text(encoding="utf-8")
            self.assertIn("Original fixture question?", review)
            self.assertIn("Original ``` [literal](missing.txt)\nmessage", evidence)
            self.assertIn(
                EXPORT.fenced(self.references[EXPORT.SPLITS.index(split)], "json"), review
            )
            self.assertEqual(review.count("- 导出状态：`pending`"), 1)
            for label in ("通过", "需修改", "无法判断"):
                self.assertEqual(review.count(f"- [ ] {label}"), 1)
            self.assertEqual(
                (self.output / f"assets/{split}.png").read_bytes(),
                (self.dataset / f"assets/{split}.png").read_bytes(),
            )
        self.assertGreater(EXPORT.verify_packet(self.dataset, self.output), 0)

    def test_missing_or_cross_split_evidence_is_rejected(self):
        for evidence_id in ("missing", "heldout-message"):
            with self.subTest(evidence_id=evidence_id):
                self.references[0]["claims"][0]["supports"][0]["evidence_id"] = evidence_id
                self.write_jsonl("references.jsonl", self.references)
                with self.assertRaisesRegex(ValueError, "missing or crosses splits"):
                    EXPORT.export_packet(self.dataset, self.output)

    def test_changed_asset_and_path_traversal_are_rejected(self):
        (self.dataset / "assets/dev.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "asset hash"):
            EXPORT.export_packet(self.dataset, self.output)
        self.scenarios[0]["assets"][0]["path"] = "../outside.png"
        self.write_json("scenarios.json", {"scenarios": self.scenarios})
        with self.assertRaisesRegex(ValueError, "escapes"):
            EXPORT.export_packet(self.dataset, self.output)

    def test_existing_reviews_are_never_overwritten(self):
        self.output.mkdir()
        annotation = self.output / "review-dev.md"
        annotation.write_text("Human annotation", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not empty"):
            EXPORT.export_packet(self.dataset, self.output)
        self.assertEqual(annotation.read_text(encoding="utf-8"), "Human annotation")

    def test_nonpending_reference_is_rejected(self):
        self.references[0]["review_status"] = "reviewed"
        self.write_jsonl("references.jsonl", self.references)
        with self.assertRaisesRegex(ValueError, "pending status"):
            EXPORT.export_packet(self.dataset, self.output)

    def test_post_export_source_or_packet_mutation_is_detected(self):
        EXPORT.export_packet(self.dataset, self.output)
        original = (self.dataset / "references.jsonl").read_bytes()
        (self.dataset / "references.jsonl").write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "Dataset bytes changed"):
            EXPORT.verify_packet(self.dataset, self.output)
        (self.dataset / "references.jsonl").write_bytes(original)
        (self.output / "assets/dev.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Exported file changed"):
            EXPORT.verify_packet(self.dataset, self.output)

    def test_missing_evidence_anchor_is_detected(self):
        EXPORT.export_packet(self.dataset, self.output)
        path = self.output / "evidence-dev.md"
        original = path.read_text(encoding="utf-8")
        path.write_text(
            original.replace(f'<a id="{EXPORT.anchor("dev-message")}"></a>', ""), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "anchor"):
            EXPORT.validate_links(self.output)


if __name__ == "__main__":
    unittest.main()
