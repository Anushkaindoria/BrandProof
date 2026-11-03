"""Brand knowledge extraction: documents in, *proposed* facts, terms and policies out.

Nothing produced here is evidence yet. Every candidate carries a verbatim quote and a page
reference, quotes are verified against the document text, and an administrator must approve
each item before it becomes an approved fact, terminology rule or policy.

Two extractors feed the same pipeline:
- a deterministic rules extractor (key: value lines, "avoid X, use Y", "never describe ... as X",
  "must include ..."), which works offline and in tests;
- Gemini (see ai.extract_knowledge), whose output is validated field by field. Any item whose
  quote is not found in the document, or whose value is not supported by its quote, is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLICY_TYPES = {"prohibited_claim", "prohibited_term", "required_phrase", "required_disclaimer", "superlative"}
PAGE_RE = re.compile(r"\[Page (\d+)\]")
STOP_KEYS = {"note", "notes", "example", "examples", "important", "warning", "tip", "summary", "contact", "page", "date", "time", "version", "title", "author", "subject", "see", "rule", "rules", "step"}
_QUOTE_MAP = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", " ": " ", "–": "-", "—": "-"})


@dataclass
class Candidate:
    item_type: str  # fact | term | policy
    payload: dict[str, Any]
    quote: str
    page_reference: str
    method: str  # rules | gemini


def extract_text(filename: str, raw: bytes) -> tuple[str, int]:
    """Plain text (with [Page N] markers for PDFs) and the page count."""
    if Path(filename).suffix.lower() == ".pdf":
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(raw))
        text = "\n".join(f"[Page {index + 1}]\n{page.extract_text() or ''}" for index, page in enumerate(reader.pages))
        return text, len(reader.pages)
    return raw.decode("utf-8"), 0


def norm(text: str) -> str:
    """Character-for-character normalisation, so offsets stay valid."""
    return text.translate(_QUOTE_MAP)


def slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:120]


def locate_quote(text: str, quote: str) -> int:
    """Offset of the quote in the text (whitespace/quote-style tolerant), or -1."""
    cleaned = norm(quote).strip()
    words = cleaned.split()
    if not words or len(cleaned) < 6:
        return -1
    pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(pattern, norm(text), re.IGNORECASE)
    return match.start() if match else -1


def page_at(text: str, offset: int) -> str:
    page = ""
    for match in PAGE_RE.finditer(text):
        if match.start() > offset:
            break
        page = f"Page {match.group(1)}"
    return page


def _sentence_around(text: str, start: int, end: int) -> str:
    newline = text.rfind("\n", 0, start)
    period = text.rfind(". ", 0, start)
    begin = max(newline + 1, period + 2 if period >= 0 else 0)
    stops = [index for index in (text.find("\n", end), text.find(". ", end)) if index >= 0]
    if not stops:
        finish = len(text)
    else:
        nearest = min(stops)
        finish = nearest + 1 if text.startswith(". ", nearest) else nearest
    return text[begin:finish].strip()[:300]


FACT_LINE_RE = re.compile(r"^\s*(?:[-*•]\s*)?([A-Za-z][A-Za-z0-9 /\-]{1,40}?)\s*:\s+(.{1,120}?)\s*$")
TERM_PATTERNS = [
    re.compile(r"(?:avoid|never use|do not use|don't use|do not say|don't say|never say)\s+[\"']?(?P<p>[^\"',.;:()]{2,40}?)[\"']?\s*(?:,|;|:|-|\.)?\s*(?:use|say|write|prefer|replace(?: it)? with)\s+[\"']?(?P<r>[^\"'.;:()]{2,60}?)[\"']?(?:\s+instead(?:\s+of\s+[^.;\n]*)?)?\s*(?:[.;]|$|\n)", re.IGNORECASE),
    re.compile(r"use\s+[\"'](?P<r>[^\"']{2,60})[\"']\s+(?:instead of|rather than|not)\s+[\"'](?P<p>[^\"']{2,40})[\"']", re.IGNORECASE),
    re.compile(r"^\s*[\"']?(?P<p>[A-Za-z][\w \-]{1,40}?)[\"']?\s*(?:->|=>|→)\s*[\"']?(?P<r>[^\"'\n]{1,60}?)[\"']?\s*$", re.MULTILINE),
]
PROHIBITED_CLAIM_RE = re.compile(r"(?:never|do not|don't|must not|should not)\s+(?:claim|call|describe|market|advertise|state|say)\s+[^.\n]{0,60}?\b(?:is|are|as)\s+[\"']?(?P<v>[A-Za-z][A-Za-z\- ]{2,30}?)[\"']?(?=\s*(?:[.,;]|\s+(?:unless|without|when|if|because)\b|$|\n))", re.IGNORECASE)
PROHIBITED_TERM_RE = re.compile(r"(?:never|do not|don't|must not|should not)\s+use\s+(?:the\s+)?(?:word|term|phrase)s?\s+[\"'](?P<v>[^\"']{2,60})[\"']", re.IGNORECASE)
REQUIRED_RE = re.compile(r"(?:must|should|always|shall)\s+(?:include|display|carry|contain|add|show)\s+(?:the\s+|a\s+)?(?P<kind>phrase|disclaimer|text|line|statement)?:?\s*[\"'](?P<v>[^\"']{3,120})[\"']", re.IGNORECASE)
SUPERLATIVE_RE = re.compile(r"(?:avoid|do not use|don't use|never use|no)\s+(?:unsupported\s+)?superlatives?", re.IGNORECASE)


def _looks_like_fact_value(value: str) -> bool:
    return bool(re.search(r"\d", value)) or bool(re.match(r"(not|no|yes|none|certified)\b", value, re.IGNORECASE))


def extract_with_rules(text: str, default_product: str = "") -> list[Candidate]:
    source = norm(text)
    found: list[Candidate] = []

    for line in re.finditer(r"^.*$", source, re.MULTILINE):
        raw = line.group(0)
        if raw.lstrip().startswith("[Page"):
            continue
        match = FACT_LINE_RE.match(raw)
        if not match:
            continue
        key = slug_key(match.group(1))
        value = match.group(2).strip().rstrip(".").strip()
        if len(key) < 2 or key in STOP_KEYS or len(match.group(1).split()) > 5 or len(value) > 100 or not _looks_like_fact_value(value):
            continue
        found.append(Candidate("fact", {"key": key, "product": default_product, "value": value}, raw.strip()[:300], page_at(source, line.start()), "rules"))

    for pattern in TERM_PATTERNS:
        for match in pattern.finditer(source):
            prohibited, replacement = match.group("p").strip(), match.group("r").strip()
            if not prohibited or not replacement or prohibited.lower() == replacement.lower():
                continue
            found.append(Candidate("term", {"prohibited": prohibited, "replacement": replacement}, _sentence_around(source, match.start(), match.end()), page_at(source, match.start()), "rules"))

    def add_policy(match: re.Match[str], rule_type: str, value: str, name: str) -> None:
        quote = _sentence_around(source, match.start(), match.end())
        found.append(Candidate("policy", {"name": name[:160], "rule_type": rule_type, "rule_value": value[:255], "description": quote}, quote, page_at(source, match.start()), "rules"))

    for match in PROHIBITED_CLAIM_RE.finditer(source):
        value = match.group("v").strip()
        add_policy(match, "prohibited_claim", value, f"No unsupported '{value}' claims")
    for match in PROHIBITED_TERM_RE.finditer(source):
        value = match.group("v").strip()
        add_policy(match, "prohibited_term", value, f"Avoid the term '{value}'")
    for match in REQUIRED_RE.finditer(source):
        value = match.group("v").strip()
        kind = "required_disclaimer" if (match.group("kind") or "").lower() == "disclaimer" else "required_phrase"
        add_policy(match, kind, value, f"Required phrase: {value}"[:160])
    for match in SUPERLATIVE_RE.finditer(source):
        add_policy(match, "superlative", "best|greatest|#1", "Unsupported superlatives require proof")
    return merge_candidates(found, [])


def identity(candidate: Candidate) -> tuple[str, str, str]:
    payload = candidate.payload
    if candidate.item_type == "fact":
        return ("fact", str(payload.get("key", "")).lower(), str(payload.get("value", "")).lower())
    if candidate.item_type == "term":
        return ("term", str(payload.get("prohibited", "")).lower(), "")
    return ("policy", str(payload.get("rule_type", "")), str(payload.get("rule_value", "")).lower())


def merge_candidates(primary: list[Candidate], secondary: list[Candidate]) -> list[Candidate]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[Candidate] = []
    for candidate in primary + secondary:
        marker = identity(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(candidate)
    return merged


def _value_supported(value: str, quote: str) -> bool:
    """A proposed value must really be stated in its quote, so numbers cannot be invented."""
    value_n, quote_n = norm(value).lower(), norm(quote).lower()
    if value_n in quote_n:
        return True
    numbers = re.findall(r"\d+(?:[.,]\d+)?", value_n)
    if numbers:
        return set(numbers) <= set(re.findall(r"\d+(?:[.,]\d+)?", quote_n))
    tokens = [token for token in re.findall(r"[a-z0-9]+", value_n) if len(token) > 2]
    return bool(tokens) and sum(token in quote_n for token in tokens) / len(tokens) >= 0.6


def _items(raw: Any) -> list[dict[str, Any]]:
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def candidates_from_gemini(raw: dict[str, Any], text: str, default_product: str = "") -> tuple[list[Candidate], int]:
    """Validate Gemini's proposals. Returns (verified candidates, number dropped)."""
    out: list[Candidate] = []
    dropped = 0

    def grounded(item: dict[str, Any]) -> tuple[str, str] | None:
        quote = str(item.get("quote") or "").strip()
        offset = locate_quote(text, quote) if quote else -1
        if offset < 0:
            return None
        return quote[:300], page_at(norm(text), offset)

    for item in _items(raw.get("facts")):
        key, value = slug_key(str(item.get("key") or "")), str(item.get("value") or "").strip()
        proof = grounded(item)
        if len(key) < 2 or not value or len(value) > 255 or not proof or not _value_supported(value, proof[0]):
            dropped += 1
            continue
        product = str(item.get("product") or default_product or "").strip()[:120]
        out.append(Candidate("fact", {"key": key, "product": product, "value": value}, proof[0], proof[1], "gemini"))

    for item in _items(raw.get("terms")):
        prohibited, replacement = str(item.get("prohibited") or "").strip(), str(item.get("replacement") or "").strip()
        proof = grounded(item)
        if not prohibited or not replacement or len(prohibited) > 120 or len(replacement) > 160 or prohibited.lower() == replacement.lower() or not proof or prohibited.lower() not in norm(proof[0]).lower():
            dropped += 1
            continue
        out.append(Candidate("term", {"prohibited": prohibited, "replacement": replacement}, proof[0], proof[1], "gemini"))

    for item in _items(raw.get("policies")):
        rule_type, name, value = str(item.get("rule_type") or ""), str(item.get("name") or "").strip(), str(item.get("rule_value") or "").strip()
        proof = grounded(item)
        if rule_type not in POLICY_TYPES or len(name) < 2 or not value or len(value) > 255 or not proof:
            dropped += 1
            continue
        if rule_type != "superlative" and not any(part.strip().lower() in norm(proof[0]).lower() for part in value.split("|") if part.strip()):
            dropped += 1
            continue
        out.append(Candidate("policy", {"name": name[:160], "rule_type": rule_type, "rule_value": value, "description": str(item.get("description") or proof[0])[:500]}, proof[0], proof[1], "gemini"))
    return merge_candidates(out, []), dropped
