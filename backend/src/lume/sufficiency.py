"""Question-to-evidence review contract; exact quotes do not prove semantic entailment."""

import hashlib
import json
import re
from typing import Literal

from pydantic import Field, model_validator

from .schemas import Input

CONTRACT = "reviewed-excerpts-v1"
DIMENSIONS = ("fact", "unit", "scope", "status")


class SupportQuote(Input):
    source: str = Field(min_length=1, max_length=3)
    quote: str = Field(min_length=1, max_length=400)


class SupportFinding(Input):
    verdict: Literal["supported", "not_required", "unsupported", "uncertain"]
    quotes: list[SupportQuote] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def supported_has_quote(self):
        if self.verdict == "supported" and not self.quotes:
            raise ValueError("Support requires a literal source quote")
        if self.verdict == "not_required" and self.quotes:
            raise ValueError("Inapplicable dimension must not invent support")
        return self


class FactFinding(SupportFinding):
    verdict: Literal["supported", "unsupported", "uncertain"]


class SupportAssessment(Input):
    fact: FactFinding
    unit: SupportFinding
    scope: SupportFinding
    status: SupportFinding


def review_binding(question, require_image, sources):
    payload = json.dumps([question, require_image, sources], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def scope_constraints(question, sources):
    """Conservative exact-name rule for explicit hyphenated environment identifiers."""
    stages = {"prod", "production", "qa", "test", "staging", "sandbox", "integration", "dev", "uat"}
    tokens = re.findall(
        r"(?<![a-z0-9_-])[a-z0-9]+(?:-[a-z0-9]+)+(?![a-z0-9_-])", question.casefold()
    )
    required = []
    for token in dict.fromkeys(tokens):
        parts = token.split("-")
        # Require a named prefix and either a final stage or numeric revision suffix.
        if any(
            part in stages and all(re.fullmatch(r"[rv]?\d+", p) for p in parts[i + 1 :])
            for i, part in enumerate(parts)
            if i > 0
        ):
            required.append(token)
    missing = [
        t
        for t in required
        if not any(
            re.search(r"(?<![a-z0-9_-])" + re.escape(t) + r"(?![a-z0-9_-])", s["text"].casefold())
            for s in sources
        )
    ]
    return {"required": required, "missing": missing}


def quote_options(text):
    """Literal bounded spans; the generator chooses them instead of inventing a quote."""
    if len(text) <= 400:
        return [text]
    chunks = re.split(r"(?<=[。；;\n])", text)
    spans = []
    for chunk in chunks:
        if len(chunk) <= 400:
            if chunk.strip():
                spans.append(chunk)
        else:
            spans.extend(chunk[i : i + 400] for i in range(0, len(chunk), 200))
    return list(dict.fromkeys(s.strip() for s in spans if s.strip()))


def validate_assessment(raw, sources, question=""):
    """Return canonical assessment, format/quote issues and conservative acceptance."""
    try:
        assessment = SupportAssessment.model_validate(raw)
    except ValueError:
        return None, ["INVALID_REVIEW_FORMAT"], False
    texts = {s["source"]: s["text"] for s in sources}
    for name in DIMENSIONS:
        finding = getattr(assessment, name)
        if any(q.source not in texts or q.quote not in texts[q.source] for q in finding.quotes):
            return assessment.model_dump(), ["INVALID_SUPPORT_QUOTE"], False
    accepted = all(
        getattr(assessment, d).verdict in {"supported", "not_required"} for d in DIMENSIONS
    )
    accepted = accepted and not scope_constraints(question, sources)["missing"]
    return assessment.model_dump(), [], accepted
