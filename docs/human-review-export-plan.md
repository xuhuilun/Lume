# Human review export plan

## Authorized scope

Export the existing 48 dataset-v1 questions, draft references, evidence messages,
and 12 image assets into a Markdown packet for human review. This is a mechanical
format conversion, not an answer-quality assessment. The existing development
and held-out split is preserved for traceability; this packet is not a blind
test. No model, application, retrieval, or evaluation execution is involved.

## Implementation

1. Add a Python standard-library-only exporter at
   `scripts/export_human_review.py`. Read only files under the explicit
   `evaluation/dataset-v1` input directory; never read environment credentials or
   any private conversation source.
2. Preserve original question, draft answer, evidence ID, and evidence text.
   Produce separate development and held-out Markdown packets, with per-question
   reviewer, date, decision, and proposed-correction fields. Include available
   image links and the source-provided synthetic-image description.
3. Create `outputs/reference-human-review/index.md` and
   `outputs/reference-human-review/filling-guide.md` outside the Lume repository,
   plus a structured `manifest.json`. Copy image bytes without image processing.
4. Add structural tests and perform export checks: question coverage, split
   counts, evidence resolution, Markdown links, identical image hashes,
   unchanged input hashes, and pending human-review counts.

## Invariants and completion criteria

- All 48 questions remain pending; completed human reviews remain zero.
- No source dataset, reference, qrel, scenario, or review-state file is changed.
- Original reference hashes are recorded in the manifest for traceability.
- Every exported evidence ID resolves to its original source message.
- Every local evidence/image link in the packet resolves inside the packet.
- No semantic relabeling, PDF generation, dependency installation, or Git commit
  is performed by this export task.

## Execution result

The packet was exported to `../outputs/reference-human-review/` relative to the
Lume repository. It contains 19 files: two question-review Markdown files, two
evidence appendices, an index, a filling guide, one manifest, and 12 unchanged
image assets. The question split is 16 development items and 32 held-out items.
The appendices cover all 72 source messages.

Validation completed:

- Seven Python unittest cases passed using invented structural fixtures only.
- All 48 question sections contain reviewer, date, pending status, the three
  unselected decisions, and correction fields.
- All 1,025 authored local links and evidence anchors resolve.
- The 20 source-file hashes are unchanged; all 12 copied image hashes match.
- All 48 reference records remain pending and human-reviewed count remains 0.
- The reference JSONL SHA-256 is
  `18e1994fe5fc2b7e6d8805b4303d33b5652e2e3aee8c8db1c7d5bf537f8c9264`.
- No target-model call, question execution, semantic label decision, dataset
  mutation, dependency installation, PDF output, commit, or merge was performed.

Reproduce the structural checks from the Lume repository:

```sh
python3 -B -m unittest scripts/test_export_human_review.py
python3 -B scripts/export_human_review.py --dataset evaluation/dataset-v1 --output ../outputs/reference-human-review --check
```

Export into a new, empty directory with the same command without `--check`.
The exporter refuses to overwrite a nonempty directory, protecting manual
annotations. `--check` validates the original export snapshot; expected edits
made by a human reviewer will change packet hashes without changing the source
reference snapshot. The manifest explicitly marks this packet as non-blind and
records both the full reference-file hash and hashes of canonical JSON records.
