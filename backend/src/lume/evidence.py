"""Render selected stored evidence, never model-authored numeric claims or copied quotes."""

from .security import DomainError

INSUFFICIENT_TEXT = "当前已读资料不足以支持本次问题，无法给出可靠结论。"


def render_evidence(task_id, selections, observations):
    if not selections:
        raise DomainError("EVIDENCE_REQUIRED", "正常答案必须选择已读原文依据")
    blocks, citations, seen = [], [], set()
    for selection in selections:
        key = (selection.observation_id, selection.message_id)
        if key in seen:
            continue
        seen.add(key)
        observation = observations.get(selection.observation_id)
        if not observation or observation.task_id != task_id:
            raise DomainError("INVALID_EVIDENCE", "依据不属于本任务")
        if observation.kind == "message_context" and selection.message_id:
            message = next(
                (
                    m
                    for m in observation.content["messages"]
                    if m["message_id"] == selection.message_id
                ),
                None,
            )
            if not message or not message.get("text", "").strip():
                raise DomainError("INVALID_EVIDENCE", "没有可展示的已读消息原文")
            heading = f"消息 {message.get('source_id', selection.message_id)}"
            text = message["text"]
        elif (
            observation.kind == "image_observation"
            and selection.message_id is None
            and observation.content.get("semantic") is True
        ):
            text = observation.content.get("text", "")
            if not text.strip():
                raise DomainError("INVALID_EVIDENCE", "图像观察为空")
            heading = "图像观察（模型识别结果，需结合原图核对）"
        else:
            raise DomainError("INVALID_EVIDENCE", "只能选择具体已读消息或实际图像观察")
        blocks.append(f"{len(blocks) + 1}. {heading}\n{text}")
        if observation.id not in citations:
            citations.append(observation.id)
    answer = "已读取的来源依据：\n\n" + "\n\n".join(blocks)
    if len(answer) > 12_000:
        raise DomainError("EVIDENCE_TOO_LARGE", "所选原文超出答案长度上限，请减少选择")
    return answer, citations
