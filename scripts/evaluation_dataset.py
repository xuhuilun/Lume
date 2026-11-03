"""Build/check the draft synthetic evidence bundle without calling models or databases."""

import argparse
import base64
import hashlib
import json
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lume.config import Settings
from lume.schemas import MessageInput, TaskInput
from lume.storage import ImageStore
from PIL import Image, ImageDraw, ImageFont
from PIL import __version__ as pillow_version

CATEGORIES = ("fact", "context", "visual", "unanswerable")
COLORS = {"blue": ("#2563eb", "蓝色"), "orange": ("#ea580c", "橙色"), "purple": ("#7c3aed", "紫色")}
QUERY_FIELDS = {
    "id",
    "question",
    "scope_scenarios",
    "require_image",
}
EXPECTED_SPLITS = {"dev": 16, "heldout": 32}
EXCLUDED = ("E_CONN_42", "pool_size", "v1.8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def read_rows(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_path(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "unsafe asset/manifest path")
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()), "asset path escapes bundle")
    return resolved


def render_panel(scenario, path):
    """Raster fixture truth is authored metadata, not a model's visual prediction."""
    image = Image.new("RGB", (960, 520), "#f3f4f6")
    draw = ImageDraw.Draw(image)

    def font(size):
        return ImageFont.load_default(size=size)

    draw.text(
        (40, 28), "SYNTHETIC FIXTURE / NOT A PRODUCTION CAPTURE", font=font(22), fill="#374151"
    )
    draw.text((40, 75), scenario["title"], font=font(36), fill="#111827")
    draw.text((40, 125), scenario["environment"], font=font(23), fill="#4b5563")
    panel = scenario["panel"]
    cx = 105 if panel["side"] == "left" else 395
    other = next(color for color in COLORS if color != panel["color"])
    for box, label, marker_x, color in [
        ((60, 185, 440, 410), panel["label"], cx, panel["color"]),
        ((520, 185, 900, 410), "OTHER", 855 if cx == 105 else 565, other),
    ]:
        draw.rounded_rectangle(box, radius=16, fill="white", outline="#9ca3af", width=2)
        draw.text((box[0] + 24, 215), label, font=font(32), fill="#111827")
        draw.ellipse((marker_x - 25, 290, marker_x + 25, 340), fill=COLORS[color][0])
    draw.text(
        (40, 465),
        "Fixture only. Marker color/position must be read from the image.",
        font=font(20),
        fill="#4b5563",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return {
        "card_bbox_xyxy": [60, 185, 440, 410],
        "marker_bbox_xyxy": [cx - 25, 290, cx + 26, 341],
        "marker_center_xy": [cx, 315],
        "color": panel["color"],
        "rgb_hex": COLORS[panel["color"]][0],
        "side": panel["side"],
    }


def build(source, root):
    require(
        source["human_review_status"] == "pending" and source["human_reviewed_queries"] == 0,
        "this v1 builder only creates pending draft labels",
    )
    root.mkdir(parents=True, exist_ok=True)
    dump(root / "source.json", source)
    scenarios, references, queries = [], [], []
    serials = Counter()
    for ordinal, item in enumerate(source["scenarios"]):
        sid, split = item["id"], item["split"]
        asset_id = sid + "-panel"
        asset_path = "assets/" + asset_id + ".png"
        truth = render_panel(item, root / asset_path)
        messages = []
        for index, content in enumerate(item["messages"]):
            at = datetime(2026, 11, 3, 1, tzinfo=UTC) + timedelta(minutes=ordinal * 30 + index)
            messages.append(
                {
                    "source_id": f"{sid}-m{index}",
                    "text": content,
                    "sent_at": at.isoformat(),
                    "author": "合成·" + ["值班", "建议", "核查", "验证", "维护", "旧环境"][index],
                    "reply_to": f"{sid}-m{index - 1}" if 0 < index < 5 else None,
                    "images": [{"asset_id": asset_id}] if index == 4 else [],
                }
            )
        scenarios.append(
            {
                "id": sid,
                "family": item["family"],
                "split": split,
                "title": item["title"],
                "messages": messages,
                "assets": [
                    {
                        "id": asset_id,
                        "message_source_id": sid + "-m4",
                        "path": asset_path,
                        "filename": "panel.png",
                        "sha256": digest(root / asset_path),
                    }
                ],
            }
        )
        for category in CATEGORIES:
            serials[split] += 1
            qid = f"q-{split}-{serials[split]:03d}"
            scope = [s["id"] for s in source["scenarios"] if s["split"] == split]
            missing = item["unanswerable_reference"]
            if category == "unanswerable" and missing["reason_kind"] == "scope_exclusion":
                scope.remove(sid)
            queries.append(
                {
                    "id": qid,
                    "question": item["questions"][category],
                    "scope_scenarios": scope,
                    "require_image": category == "visual",
                }
            )
            claims, evidence_set, visual = [], [], []
            if category == "fact":
                evidence_set = [sid + "-m3"]
                claims = [
                    {
                        "text": item["fact_reference"]["claim"],
                        "supports": [
                            {
                                "evidence_id": sid + "-m3",
                                "excerpt": item["fact_reference"]["excerpt"],
                            }
                        ],
                    }
                ]
            elif category == "context":
                evidence_set = [f"{sid}-m{i}" for i in range(4)]
                claims = [
                    {
                        "text": messages[i]["text"],
                        "supports": [
                            {
                                "evidence_id": messages[i]["source_id"],
                                "excerpt": messages[i]["text"],
                            }
                        ],
                    }
                    for i in range(4)
                ]
            elif category == "visual":
                evidence_set = [asset_id]
                visual = [{"evidence_id": asset_id, "label": item["panel"]["label"], **truth}]
                claims = [
                    {
                        "text": f"{item['panel']['label']}卡片圆点为{COLORS[truth['color']][1]}。",
                        "supports": [{"evidence_id": asset_id}],
                    },
                    {
                        "text": "圆点位于卡片"
                        + ("左端。" if truth["side"] == "left" else "右端。"),
                        "supports": [{"evidence_id": asset_id}],
                    },
                ]
            references.append(
                {
                    "query_id": qid,
                    "scenario_id": sid,
                    "split": split,
                    "category": category,
                    "answerable": category != "unanswerable",
                    "expected_state": "insufficient" if category == "unanswerable" else "completed",
                    "claims": claims,
                    "minimal_evidence_sets": [evidence_set] if evidence_set else [],
                    "visual_assertions": visual,
                    "insufficient_reason": missing["reason"] if not evidence_set else None,
                    "reason_kind": missing["reason_kind"] if not evidence_set else None,
                    "forbidden_evidence_ids": [sid + "-m3"]
                    if category == "unanswerable" and missing["reason_kind"] == "scope_exclusion"
                    else [],
                    "review_status": "pending",
                }
            )
    dump(root / "scenarios.json", {"scenarios": scenarios})
    refmap = {r["query_id"]: r for r in references}
    for split in EXPECTED_SPLITS:
        jsonl(
            root / f"queries-{split}.jsonl",
            [q for q in queries if refmap[q["id"]]["split"] == split],
        )
    jsonl(root / "references.jsonl", references)
    write_qrels(root, scenarios, references)
    write_review(root, scenarios, queries, references)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != "manifest.json")
    dump(
        root / "manifest.json",
        {
            "dataset_id": source["dataset_id"],
            "date": source["date"],
            "baseline_commit": source["baseline_commit"],
            "human_review_status": "pending",
            "human_reviewed_queries": 0,
            "target_model_calls_during_build": 0,
            "counts": {
                "scenarios": 12,
                "messages": 72,
                "images": 12,
                "queries": 48,
                "splits": EXPECTED_SPLITS,
                "answerable": 36,
                "unanswerable": 12,
            },
            "generator": {"pillow": pillow_version, "image_size": [960, 520]},
            "files": {p.relative_to(root).as_posix(): digest(p) for p in files},
        },
    )


def qrels_rows(scenarios, references):
    image_parents = {a["id"]: a["message_source_id"] for s in scenarios for a in s["assets"]}
    rows = []
    for reference in references:
        # This draft uses one nominated minimum set; message qrels do not score image inspection.
        ids = {
            image_parents.get(e, e) for group in reference["minimal_evidence_sets"] for e in group
        }
        rows.extend((reference["query_id"], "0", eid, "1") for eid in sorted(ids))
    return rows


def write_qrels(root, scenarios, references):
    (root / "qrels.tsv").write_text(
        "".join("\t".join(row) + "\n" for row in qrels_rows(scenarios, references)),
        encoding="utf-8",
    )


def write_review(root, scenarios, queries, references):
    qmap = {q["id"]: q for q in queries}
    grouped = {(r["scenario_id"], r["category"]): r for r in references}
    lines = [
        "# 合成参考证据审阅册",
        "",
        "日期：2026-11-03。12情景、72消息、12图、48题；dev=16，heldout=32。",
        "",
        "全部为助手编制的合成资料与标签草稿；人工复核0题。保留集不是秘密盲测，本阶段没有模型实验或质量分数。",
        "",
        "每题需核对题意、参考事实、证据充分性、替代证据、不可回答依据及范围。最小集合内部为AND，集合之间为OR。",
        "",
        "事实正确性、引用支持性和图像实际核查分别检查。未标正的其他资料为未穷尽判断，不直接认定为负例。",
        "",
        "人工复核状态均待完成；请记录复核者、日期与修改理由，正式实验前另行冻结修订版本。",
        "",
    ]
    for s in scenarios:
        lines.extend([f"## {s['id']} / {s['split']} / {s['family']}", ""])
        for message in s["messages"]:
            lines.extend(
                [
                    f"**{message['source_id']}**（回复：{message['reply_to'] or '无'}）",
                    "",
                    message["text"],
                    "",
                ]
            )
        lines.extend([f"![{s['title']}](" + s["assets"][0]["path"] + ")", ""])
        for category in CATEGORIES:
            r = grouped[(s["id"], category)]
            qid = r["query_id"]
            q = qmap[qid]
            lines.extend(
                [
                    f"### {qid}",
                    "",
                    q["question"],
                    "",
                    f"类别：{category}；核图要求：{q['require_image']}；预期状态：{r['expected_state']}。",
                    "允许范围：" + ", ".join(q["scope_scenarios"]) + "。",
                    "",
                ]
            )
            if r["claims"]:
                for claim in r["claims"]:
                    lines.append(
                        "- 参考事实："
                        + claim["text"]
                        + " 支持："
                        + ", ".join(p["evidence_id"] for p in claim["supports"])
                    )
                lines.extend(
                    [
                        "",
                        "拟定最小证据集合："
                        + json.dumps(r["minimal_evidence_sets"], ensure_ascii=False),
                        "",
                    ]
                )
            else:
                lines.extend(["不可回答依据：" + r["insufficient_reason"], ""])
            for visual in r["visual_assertions"]:
                lines.extend(
                    [
                        "图片真值（作者参数，待视觉复核）："
                        + json.dumps(visual, ensure_ascii=False),
                        "",
                    ]
                )
            lines.extend(
                [
                    "- [ ] 题意、等价答案与必要限定已复核",
                    "- [ ] 证据充分性、替代证据或不可回答原因已复核",
                    "- [ ] 若涉及图片，已对照原图检查颜色、位置与区域",
                    "",
                    "复核者 / 日期 / 修改理由：待填写。",
                    "",
                ]
            )
    (root / "review.md").write_text("\n".join(lines), encoding="utf-8")


def check(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    require(actual == set(manifest["files"]), "manifest file set mismatch")
    for name, expected in manifest["files"].items():
        require(digest(local_path(root, name)) == expected, "manifest digest mismatch: " + name)
    source = json.loads((root / "source.json").read_text(encoding="utf-8"))
    require(
        all(manifest[key] == source[key] for key in ["dataset_id", "date", "baseline_commit"]),
        "dataset provenance metadata mismatch",
    )
    require(
        manifest["human_review_status"] == source["human_review_status"] == "pending"
        and manifest["human_reviewed_queries"] == source["human_reviewed_queries"] == 0,
        "draft review status must remain pending with zero human-reviewed queries",
    )
    require(manifest["target_model_calls_during_build"] == 0, "builder must not call target models")
    scenarios = json.loads((root / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    queries = [q for split in EXPECTED_SPLITS for q in read_rows(root / f"queries-{split}.jsonl")]
    refs = read_rows(root / "references.jsonl")
    smap = {s["id"]: s for s in scenarios}
    require(len(smap) == len(scenarios) == 12, "scenario identities/count mismatch")
    families = {
        split: {s["family"] for s in scenarios if s["split"] == split} for split in EXPECTED_SPLITS
    }
    require(not families["dev"].intersection(families["heldout"]), "scenario family split leakage")
    source_map = {s["id"]: s for s in source["scenarios"]}
    require(set(source_map) == set(smap), "author/source scenario identities mismatch")
    for s in scenarios:
        require(s["split"] == source_map[s["id"]]["split"], "scenario/source split mismatch")
        require(s["family"] == source_map[s["id"]]["family"], "scenario/source family mismatch")
        require(
            [m["text"] for m in s["messages"]] == source_map[s["id"]]["messages"],
            "message/source text mismatch",
        )
        require(
            len(s["messages"]) == 6 and len(s["assets"]) == 1, "scenario object counts mismatch"
        )
    messages = {m["source_id"]: (s["id"], m) for s in scenarios for m in s["messages"]}
    assets = {a["id"]: (s["id"], a) for s in scenarios for a in s["assets"]}
    require(len(messages) == 72 and len(assets) == 12, "message/asset identities mismatch")
    require(not set(messages).intersection(assets), "message and image evidence identities overlap")
    attachments = [i["asset_id"] for _, m in messages.values() for i in m["images"]]
    require(Counter(attachments) == {aid: 1 for aid in assets}, "asset attachment count mismatch")
    for sid, message in messages.values():
        require(
            not message["reply_to"]
            or message["reply_to"] in messages
            and messages[message["reply_to"]][0] == sid,
            "reply target outside scenario",
        )
        for image in message["images"]:
            require(
                image["asset_id"] in assets and assets[image["asset_id"]][0] == sid,
                "image attachment outside scenario",
            )
    for sid, asset in assets.values():
        require(
            asset["message_source_id"] in messages
            and messages[asset["message_source_id"]][0] == sid,
            "image parent outside scenario",
        )
        path = local_path(root, asset["path"])
        require(
            {"asset_id": asset["id"]} in messages[asset["message_source_id"]][1]["images"],
            "image parent is not its attachment owner",
        )
        require(digest(path) == asset["sha256"], "asset digest mismatch")
        with Image.open(path) as image:
            require(
                image.format == "PNG" and image.size == (960, 520), "invalid image dimensions/type"
            )
    qmap = {q["id"]: q for q in queries}
    rmap = {r["query_id"]: r for r in refs}
    require(
        len(qmap) == len(queries) == len(rmap) == len(refs) == 48 and set(qmap) == set(rmap),
        "query/reference identities mismatch",
    )
    require(
        len({(r["scenario_id"], r["category"]) for r in refs}) == 48,
        "scenario/category reference identities overlap",
    )
    for split, count in EXPECTED_SPLITS.items():
        rows = read_rows(root / f"queries-{split}.jsonl")
        require(
            len(rows) == count and all(rmap[q["id"]]["split"] == split for q in rows),
            "query split mismatch",
        )
        require(
            Counter(rmap[q["id"]]["category"] for q in rows) == {c: count // 4 for c in CATEGORIES},
            "category balance mismatch",
        )
    for q in queries:
        require(set(q) == QUERY_FIELDS, "query contains label or unknown fields")
        r = rmap[q["id"]]
        require(
            r["category"] in CATEGORIES
            and q["id"].startswith("q-" + r["split"] + "-")
            and q["id"].rsplit("-", 1)[1].isdigit(),
            "query category/identity mismatch",
        )
        require(
            r["scenario_id"] in smap and r["split"] == smap[r["scenario_id"]]["split"],
            "query scenario split mismatch",
        )
        require(
            q["question"] == source_map[r["scenario_id"]]["questions"][r["category"]],
            "question/source text mismatch",
        )
        require(
            q["scope_scenarios"] and len(set(q["scope_scenarios"])) == len(q["scope_scenarios"]),
            "invalid scope list",
        )
        require(
            all(s in smap and smap[s]["split"] == r["split"] for s in q["scope_scenarios"]),
            "cross-split query scope",
        )
        require(q["require_image"] is (r["category"] == "visual"), "image requirement mismatch")
        task_payload(q, {sid: "space-" + sid for sid in smap})
        require(r["review_status"] == "pending", "reference review status must remain pending")
        expected = r["category"] != "unanswerable"
        require(
            r["answerable"] is expected
            and r["expected_state"] == ("completed" if expected else "insufficient"),
            "answerability/state mismatch",
        )
        require(
            bool(r["claims"]) is expected and bool(r["minimal_evidence_sets"]) is expected,
            "unanswerable reference contains gold claims/evidence",
        )
        if not expected:
            require(
                r["insufficient_reason"]
                and r["reason_kind"] in {"missing_record", "scope_exclusion"},
                "missing unanswerable reason",
            )
            require(
                bool(r["forbidden_evidence_ids"]) is (r["reason_kind"] == "scope_exclusion"),
                "scope exclusion must name out-of-scope reference evidence",
            )
        for group in r["minimal_evidence_sets"]:
            require(group and len(group) == len(set(group)), "invalid minimum evidence set")
            for eid in group:
                owner = messages.get(eid) or assets.get(eid)
                require(
                    owner and owner[0] in q["scope_scenarios"], "gold evidence outside query scope"
                )
            require(
                all(
                    any(s["evidence_id"] in group for s in claim["supports"])
                    for claim in r["claims"]
                ),
                "minimum evidence set does not cover all reference claims",
            )
        for eid in r["forbidden_evidence_ids"]:
            require(
                eid in messages
                and messages[eid][0] not in q["scope_scenarios"]
                and r["reason_kind"] == "scope_exclusion",
                "invalid forbidden evidence",
            )
        for claim in r["claims"]:
            require(claim["text"] and claim["supports"], "unsupported empty claim")
            for support in claim["supports"]:
                eid = support["evidence_id"]
                require(
                    any(eid in g for g in r["minimal_evidence_sets"]),
                    "claim support outside minimum evidence",
                )
                if eid in messages:
                    require(
                        support.get("excerpt") and support["excerpt"] in messages[eid][1]["text"],
                        "evidence excerpt mismatch",
                    )
                else:
                    require(eid in assets, "unknown image evidence")
        authored = source_map[r["scenario_id"]]
        if r["category"] == "fact":
            require(
                len(r["claims"]) == 1
                and r["claims"][0]["text"] == authored["fact_reference"]["claim"],
                "fact reference differs from author source",
            )
        if r["category"] == "context":
            require(
                [c["text"] for c in r["claims"]] == authored["messages"][:4],
                "context references differ from author source",
            )
        require(
            bool(r["visual_assertions"]) is (r["category"] == "visual"),
            "visual annotation mismatch",
        )
        for visual in r["visual_assertions"]:
            sid, asset = assets[visual["evidence_id"]]
            panel = source_map[sid]["panel"]
            require(
                all(visual[k] == panel[k] for k in ["color", "side", "label"]),
                "visual truth differs from authored specification",
            )
            require(visual["rgb_hex"] == COLORS[visual["color"]][0], "visual RGB truth mismatch")
            x, y = visual["marker_center_xy"]
            x1, y1, x2, y2 = visual["marker_bbox_xyxy"]
            cx1, cy1, cx2, cy2 = visual["card_bbox_xyxy"]
            require(
                0 <= cx1 <= x1 <= x < x2 <= cx2 <= 960 and 0 <= cy1 <= y1 <= y < y2 <= cy2 <= 520,
                "visual region out of bounds",
            )
            require(
                (x < (cx1 + cx2) / 2) == (visual["side"] == "left"), "visual side geometry mismatch"
            )
            with Image.open(local_path(root, asset["path"])) as image:
                require(
                    image.convert("RGB").getpixel((x, y))
                    == tuple(bytes.fromhex(visual["rgb_hex"][1:])),
                    "visual marker pixel mismatch",
                )
    expected_qrels = "".join("\t".join(r) + "\n" for r in qrels_rows(scenarios, refs))
    require(
        (root / "qrels.tsv").read_text(encoding="utf-8") == expected_qrels, "qrels mapping mismatch"
    )
    for content in [
        json.dumps(scenarios, ensure_ascii=False),
        json.dumps(queries, ensure_ascii=False),
        json.dumps(refs, ensure_ascii=False),
    ]:
        require(
            not any(token.lower() in content.lower() for token in EXCLUDED),
            "historical debugging fixture leaked into dataset",
        )
    with tempfile.TemporaryDirectory(prefix="lume-dataset-check-") as directory:
        store = ImageStore(Settings(_env_file=None, data_dir=Path(directory)))
        for _sid, message in messages.values():
            packet = {**message, "images": []}
            for image in message["images"]:
                asset = assets[image["asset_id"]][1]
                data = local_path(root, asset["path"]).read_bytes()
                store.put(data)
                packet["images"].append(
                    {"filename": asset["filename"], "base64": base64.b64encode(data).decode()}
                )
            MessageInput.model_validate(packet)
    counts = {
        "scenarios": len(scenarios),
        "messages": len(messages),
        "images": len(assets),
        "queries": len(queries),
        "splits": dict(Counter(r["split"] for r in refs)),
        "answerable": sum(r["answerable"] for r in refs),
        "unanswerable": sum(not r["answerable"] for r in refs),
    }
    require(manifest["counts"] == counts, "manifest declared counts do not match actual data")
    return {
        "dataset_id": manifest["dataset_id"],
        **counts,
        "human_review_status": "pending",
        "human_reviewed_queries": 0,
        "structural_validation": "passed",
        "message_input_checks": 72,
        "this_check_calls_models": False,
        "quality_scores_computed": False,
    }


def task_payload(query, space_ids):
    """Only these three request fields cross into the application/Agent boundary."""
    require(set(query) == QUERY_FIELDS, "query contains label or unknown fields")
    require(
        all(s in space_ids for s in query["scope_scenarios"]), "runtime scope mapping incomplete"
    )
    payload = {
        "question": query["question"],
        "space_ids": [space_ids[s] for s in query["scope_scenarios"]],
        "require_image": query["require_image"],
    }
    TaskInput.model_validate(payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("--source", type=Path, required=True)
    builder.add_argument("--output", type=Path, required=True)
    checker = commands.add_parser("check")
    checker.add_argument("--dataset", type=Path, required=True)
    checker.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        source = json.loads(args.source.read_text(encoding="utf-8"))
        build(source, args.output)
        result = check(args.output)
    else:
        result = check(args.dataset)
        if args.report:
            dump(args.report, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
