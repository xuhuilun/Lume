#!/usr/bin/env python3
"""Mechanically export the synthetic draft labels into a human review packet."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote

SPLITS = ("dev", "heldout")
LINK_PATTERN = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_sha256(record):
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def contained_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes the permitted directory: {relative}")
    return path


def source_hashes(root):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    return {
        path.relative_to(root).as_posix(): sha256(contained_path(root, path.relative_to(root)))
        for path in files
    }


def read_json(root, filename):
    return json.loads(contained_path(root, filename).read_text(encoding="utf-8"))


def read_jsonl(root, filename):
    return [
        json.loads(line)
        for line in contained_path(root, filename).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def fenced(value, language="text"):
    """Preserve original text even when it contains Markdown delimiters."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    runs = [len(match.group()) for match in re.finditer(r"`+", text)]
    fence = "`" * max(3, max(runs, default=0) + 1)
    return f"{fence}{language}\n{text}\n{fence}\n"


def anchor(value):
    return "evidence-" + value.encode("utf-8").hex()


def evidence_link(evidence_id, split):
    return f"[{evidence_id}](evidence-{split}.md#{anchor(evidence_id)})"


def evidence_ids(reference):
    ids = []
    for claim in reference["claims"]:
        ids.extend(support["evidence_id"] for support in claim["supports"])
    for evidence_set in reference["minimal_evidence_sets"]:
        ids.extend(evidence_set)
    ids.extend(item["evidence_id"] for item in reference["visual_assertions"])
    ids.extend(reference["forbidden_evidence_ids"])
    return list(dict.fromkeys(ids))


def load_dataset(root):
    source = read_json(root, "source.json")
    original_manifest = read_json(root, "manifest.json")
    scenarios = read_json(root, "scenarios.json")["scenarios"]
    queries = {split: read_jsonl(root, f"queries-{split}.jsonl") for split in SPLITS}
    references = read_jsonl(root, "references.jsonl")
    reference_map = {row["query_id"]: row for row in references}
    scenario_map = {row["id"]: row for row in scenarios}
    source_scenarios = {row["id"]: row for row in source["scenarios"]}
    evidence = {}
    assets = {}
    for scenario in scenarios:
        for message in scenario["messages"]:
            if message["source_id"] in evidence:
                raise ValueError("Duplicate evidence ID")
            evidence[message["source_id"]] = (scenario, message)
        for asset in scenario["assets"]:
            if asset["id"] in evidence:
                raise ValueError("Duplicate evidence ID")
            evidence[asset["id"]] = (scenario, asset)
            assets[asset["id"]] = asset

    query_ids = [query["id"] for split in SPLITS for query in queries[split]]
    if len(set(query_ids)) != len(query_ids) or len(reference_map) != len(references):
        raise ValueError("Duplicate query or reference ID")
    if set(query_ids) != set(reference_map):
        raise ValueError("Queries and references do not match exactly")
    if len(scenario_map) != len(scenarios) or set(scenario_map) != set(source_scenarios):
        raise ValueError("Scenario IDs do not match the source")
    for metadata in (source, original_manifest):
        if metadata["human_review_status"] != "pending" or metadata["human_reviewed_queries"] != 0:
            raise ValueError("The exporter requires an entirely pending, unreviewed source")
    for split, split_queries in queries.items():
        for query in split_queries:
            reference = reference_map[query["id"]]
            if reference["split"] != split or reference["review_status"] != "pending":
                raise ValueError("Reference split or pending status is inconsistent")
            if scenario_map[reference["scenario_id"]]["split"] != split:
                raise ValueError("Reference scenario belongs to another split")
            if any(scenario_map[sid]["split"] != split for sid in query["scope_scenarios"]):
                raise ValueError("Query candidate scope crosses splits")
            for eid in evidence_ids(reference):
                if eid not in evidence or evidence[eid][0]["split"] != split:
                    raise ValueError("A reference evidence ID is missing or crosses splits")
    for scenario in scenarios:
        for message in scenario["messages"]:
            if message["reply_to"] is not None and message["reply_to"] not in evidence:
                raise ValueError("Unresolved reply evidence ID")
            if any(image["asset_id"] not in assets for image in message["images"]):
                raise ValueError("Unresolved message image ID")
        for asset in scenario["assets"]:
            if asset["message_source_id"] not in evidence:
                raise ValueError("Unresolved image source message")
            if sha256(contained_path(root, asset["path"])) != asset["sha256"]:
                raise ValueError("Image bytes do not match the source asset hash")
    counts = {
        "queries": len(query_ids),
        "splits": {split: len(rows) for split, rows in queries.items()},
        "scenarios": len(scenarios),
        "messages": sum(len(scenario["messages"]) for scenario in scenarios),
        "images": len(assets),
    }
    if any(original_manifest["counts"][key] != value for key, value in counts.items()):
        raise ValueError("Source manifest counts do not match the records")
    return source, scenarios, source_scenarios, queries, reference_map, evidence, assets, counts


def render_evidence(split, scenarios, source_scenarios):
    lines = [f"# {split} 原始证据附录\n", "此处按原始字段展示合成数据，不作标签判断。\n"]
    for scenario in scenarios:
        if scenario["split"] != split:
            continue
        lines.extend(
            [
                f'<a id="{anchor(scenario["id"])}"></a>\n',
                f"## 场景 `{scenario['id']}`\n",
                fenced({key: scenario[key] for key in ("id", "family", "split", "title")}, "json"),
            ]
        )
        for message in scenario["messages"]:
            mid = message["source_id"]
            lines.extend([f'<a id="{anchor(mid)}"></a>\n', f"### 消息 `{mid}`\n"])
            metadata = {key: value for key, value in message.items() if key != "text"}
            lines.extend([fenced(metadata, "json"), "原文：\n", fenced(message["text"])])
            if message["reply_to"]:
                lines.append(f"回复原文：{evidence_link(message['reply_to'], split)}\n")
            for image in message["images"]:
                lines.append(f"关联图片：{evidence_link(image['asset_id'], split)}\n")
        for asset in scenario["assets"]:
            aid = asset["id"]
            lines.extend(
                [
                    f'<a id="{anchor(aid)}"></a>\n',
                    f"### 图片 `{aid}`\n",
                    fenced(asset, "json"),
                    f"来源消息：{evidence_link(asset['message_source_id'], split)}\n",
                    f"[打开原图]({asset['path']})\n",
                    f"![合成图片 {aid}]({asset['path']})\n",
                    "合成说明：以下为 source.json 的 panel 字段原文；未新增图像解释。\n",
                    fenced(source_scenarios[scenario["id"]]["panel"], "json"),
                ]
            )
    return "\n".join(lines)


def render_review(split, queries, references, evidence, source_scenarios):
    scenario_map = {scenario["id"]: scenario for scenario, _ in evidence.values()}
    lines = [
        f"# {split} 人工标签审阅清单\n",
        f"共 {len(queries)} 题。所有条目的导出状态为 `pending`，已完成人审为 0。\n",
        "这是含草稿答案、原始标签和来源场景的人工复核包，不是盲测。"
        "请先阅读 [填写说明](filling-guide.md)。机器导出不代表参考答案已通过审核。\n",
    ]
    for number, query in enumerate(queries, 1):
        reference = references[query["id"]]
        scenario = scenario_map[reference["scenario_id"]]
        lines.extend(
            [
                f'<a id="query-{query["id"]}"></a>\n',
                f"## {number}. `{query['id']}`\n",
                "### 问题原文\n",
                fenced(query["question"]),
                "问题原始元数据：\n",
                fenced({key: value for key, value in query.items() if key != "question"}, "json"),
                "### 草稿答案与支持标注\n",
            ]
        )
        if not reference["claims"]:
            lines.append("原始参考未列出答案断言；下列不可回答说明和标签仍是待人审草稿。\n")
        for index, claim in enumerate(reference["claims"], 1):
            lines.extend([f"断言 {index} 原文：\n", fenced(claim["text"])])
            for support in claim["supports"]:
                lines.append(f"支持证据：{evidence_link(support['evidence_id'], split)}\n")
                if "excerpt" in support:
                    lines.extend(["草稿摘录原文：\n", fenced(support["excerpt"])])
        if reference["insufficient_reason"] is not None:
            lines.extend(["不可回答说明原文：\n", fenced(reference["insufficient_reason"])])
        lines.extend(
            [
                "原始参考记录（包括最小证据集、禁止引用项和视觉标注，原值保留）：\n",
                fenced(reference, "json"),
            ]
        )
        lines.append("### 标注涉及的证据原文\n")
        ids = evidence_ids(reference)
        if not ids:
            lines.append("原始参考未列出证据 ID；请结合下方完整候选场景人工检查。\n")
        for eid in ids:
            _, item = evidence[eid]
            lines.append(f"证据 ID：{evidence_link(eid, split)}\n")
            if "text" in item:
                lines.append(fenced(item["text"]))
            else:
                lines.append(f"[打开原始图片]({item['path']})\n")
        lines.extend(
            [
                "### 完整候选范围与上下文\n",
                "以下链接保留问题的原始候选场景范围。请同时检查回复链、冲突消息及"
                "未被草稿引用的消息；链接未表达相关性判断。\n",
            ]
        )
        for sid in query["scope_scenarios"]:
            lines.append(f"- [{sid}](evidence-{split}.md#{anchor(sid)})")
        lines.extend(["\n本题原始参考所属场景的全部消息：\n"])
        for message in scenario["messages"]:
            lines.append(f"- {evidence_link(message['source_id'], split)}")
        lines.append("\n### 图片与合成说明\n")
        for asset in scenario["assets"]:
            lines.extend(
                [
                    f"图片 ID：{evidence_link(asset['id'], split)}；[原图]({asset['path']})\n",
                    f"![合成图片 {asset['id']}]({asset['path']})\n",
                ]
            )
        lines.extend(
            [
                "source.json 中的合成 panel 配置原文：\n",
                fenced(source_scenarios[scenario["id"]]["panel"], "json"),
                "### 人工填写\n",
                "- 导出状态：`pending`\n- 复核者：________________\n- 复核日期：________________\n"
                "- [ ] 通过\n- [ ] 需修改\n- [ ] 无法判断\n",
                "修改建议（答案 / 可回答性 / 证据 ID / 摘录 / 视觉标注 / 原因）：\n",
                "<!-- 请在此填写；未填写或未勾选不构成人审完成。 -->\n\n",
                "建议更正值及对应证据原文（如适用）：\n",
                "<!-- 请在此填写。 -->\n\n---\n",
            ]
        )
    return "\n".join(lines)


def validate_links(output):
    checked = 0
    for markdown in output.glob("*.md"):
        text = markdown.read_text(encoding="utf-8")
        # Original questions and messages are fenced data, not authored links.
        prose = re.sub(r"(?ms)^(`{3,})[^\n]*\n.*?^\1\s*$", "", text)
        for destination in LINK_PATTERN.findall(prose):
            if "://" in destination:
                continue
            relative, _, fragment = unquote(destination).partition("#")
            target = contained_path(output, relative) if relative else markdown
            if not target.is_file():
                raise ValueError(f"Missing packet link target in {markdown.name}")
            if fragment and f'<a id="{fragment}"></a>' not in target.read_text(encoding="utf-8"):
                raise ValueError(f"Missing packet evidence anchor in {markdown.name}")
            checked += 1
    return checked


def verify_packet(dataset, output):
    manifest = read_json(output, "manifest.json")
    if source_hashes(dataset) != manifest["source_files_sha256"]:
        raise ValueError("Dataset bytes changed after export")
    if manifest["human_reviewed_queries"] != 0 or manifest["human_review_status"] != "pending":
        raise ValueError("Exported human-review state is inconsistent")
    for relative, digest in manifest["packet_files_sha256"].items():
        if sha256(contained_path(output, relative)) != digest:
            raise ValueError(f"Exported file changed: {relative}")
    return validate_links(output)


def export_packet(dataset, output):
    dataset, output = dataset.resolve(), output.resolve()
    if output == dataset or output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise ValueError("Output must be separate from the source dataset")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output is not empty; preserve any existing human annotations")
    before = source_hashes(dataset)
    source, scenarios, source_scenarios, queries, references, evidence, assets, counts = (
        load_dataset(dataset)
    )
    output.mkdir(parents=True, exist_ok=True)
    for asset in assets.values():
        target = contained_path(output, asset["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(contained_path(dataset, asset["path"]), target)
    for split in SPLITS:
        (output / f"review-{split}.md").write_text(
            render_review(split, queries[split], references, evidence, source_scenarios),
            encoding="utf-8",
        )
        (output / f"evidence-{split}.md").write_text(
            render_evidence(split, scenarios, source_scenarios), encoding="utf-8"
        )
    (output / "index.md").write_text(
        "# 人工标签审阅包\n\n"
        "此包仅将 dataset-v1 的问题、合成消息、图片与草稿参考转为可填写 Markdown。"
        "没有调用目标模型、运行问题、评价答案或更新原数据集。"
        "包含参考答案与场景信息，因此不是盲测。\n\n"
        f"共 {counts['queries']} 题、{counts['messages']} 条消息、{counts['images']} 张图片。"
        "导出状态全部 pending，已完成人审为 0。\n\n"
        f"- [dev 逐题审阅包（{counts['splits']['dev']} 题）](review-dev.md)\n"
        f"- [heldout 逐题审阅包（{counts['splits']['heldout']} 题）](review-heldout.md)\n"
        "- [dev 证据原文附录](evidence-dev.md)\n"
        "- [heldout 证据原文附录](evidence-heldout.md)\n"
        "- [填写说明](filling-guide.md)\n- [哈希与结构化清单](manifest.json)\n\n"
        "原始来源声明：\n\n" + fenced(source["provenance"]),
        encoding="utf-8",
    )
    (output / "filling-guide.md").write_text(
        "# 人工标签审阅填写说明\n\n"
        "1. 按原始 dev / heldout 划分打开对应的逐题包。此包公开草稿和来源，"
        "该划分不构成盲测。若需后续盲测，应另行制定隔离流程。\n"
        "2. 每题先读问题、完整候选范围及消息原文，再核对草稿答案、可回答性、"
        "支持证据、摘录、最小证据集、禁止引用项和视觉标注。禁止引用项同样"
        "作为原标签展示，并非导出程序新作的判断。\n"
        "3. 点击证据 ID 可到本包的原文附录。图片来自源数据集，逐字节复制；"
        "合成说明只展示源 provenance 与 panel 字段，不增加图像解读。\n"
        "4. 在每题末尾填复核者和日期，并只勾选“通过 / 需修改 / 无法判断”"
        "中的一项。需修改时写明建议更正值、对应证据 ID 和原文；无法判断时"
        "说明缺少的信息或分歧。未填写不得计为已完成人审。\n"
        "5. 请保留原问题、草稿和证据原文，在人工填写区记录意见。"
        "本包不自动回写数据集、不更新 review_status，也不将勾选转换为正式标签；"
        "正式采纳需要单独的复核与数据集更新步骤。\n"
        "6. manifest.json 记录的是导出时快照：全部 pending、人审 0。"
        "人工填写后包文件哈希会变化，这是审阅记录的正常变化；源参考文件的"
        "SHA-256 和逐条规范 JSON SHA-256 仍可追溯原始草稿。\n\n"
        "[返回索引](index.md)\n",
        encoding="utf-8",
    )
    if source_hashes(dataset) != before:
        raise ValueError("Source dataset changed during export")
    manifest = {
        "schema_version": 1,
        "dataset_id": source["dataset_id"],
        "operation": "mechanical-format-conversion",
        "blind_evaluation": False,
        "target_model_calls": 0,
        "questions_executed": 0,
        "human_review_status": "pending",
        "human_reviewed_queries": 0,
        "counts": counts,
        "references_file_sha256": before["references.jsonl"],
        "reference_record_hash_format": (
            "UTF-8 JSON; sorted keys; compact separators; ensure_ascii=False"
        ),
        "reference_records": {
            qid: {
                "sha256": record_sha256(record),
                "split": record["split"],
                "review_status": "pending",
            }
            for qid, record in references.items()
        },
        "source_files_sha256": before,
        "packet_files_sha256": source_hashes(output),
        "validated_local_links": 0,
        "image_copy_method": "byte-for-byte; no image decoding or transformation",
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest["validated_local_links"] = validate_links(output)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verify_packet(dataset, output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Verify an existing, unedited export")
    args = parser.parse_args()
    if args.check:
        print(json.dumps({"validated_local_links": verify_packet(args.dataset, args.output)}))
    else:
        manifest = export_packet(args.dataset, args.output)
        print(
            json.dumps(
                {
                    "counts": manifest["counts"],
                    "validated_local_links": manifest["validated_local_links"],
                }
            )
        )


if __name__ == "__main__":
    main()
