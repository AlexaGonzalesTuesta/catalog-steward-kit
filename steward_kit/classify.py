"""Suggest PII classifications from column names and sampled values.

Suggestions are never applied automatically. A steward confirms or rejects each one.
Score = 0.35 x (name matches a PII pattern) + 0.65 x (share of sampled values that match),
so a column needs real evidence in its values, not just a suspicious name.
Free-text columns are flagged when they contain embedded emails or phone numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .catalog import Catalog, Column
from .synthetic import is_valid_vin

NAME_RULES = {
    "email": re.compile(r"(^|_)(e_?mail)(_|$)"),
    "phone": re.compile(r"(^|_)(phone|mobile|cell|tel|telephone)(_|$)"),
    "person_name": re.compile(r"(^|_)(first|last|full|given|family|customer|owner)_?name(_|$)"),
    "street_address": re.compile(r"(^|_)(street|address|addr)(_|$)"),
    "postal_code": re.compile(r"(^|_)(zip|zipcode|postal|postcode)(_|$)"),
    "vin": re.compile(r"(^|_)vin(_|$)"),
    "date_of_birth": re.compile(r"(^|_)(dob|birth|birthdate|date_of_birth)(_|$)"),
    "government_id": re.compile(r"(^|_)(ssn|social_security|passport|license_number|drivers_license)(_|$)"),
}
FREE_TEXT_NAME = re.compile(r"(^|_)(note|notes|comment|comments|narrative|remarks|message|summary|description)(_|$)")

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE = re.compile(r"^(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$")
ZIP = re.compile(r"^\d{5}(-\d{4})?$")
STREET = re.compile(r"^\d{1,6}\s+[A-Za-z0-9 .'-]+\s(St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|Ct|Court|Way|Pl|Pkwy)\.?$", re.I)
PERSON = re.compile(r"^[A-Z][a-z'-]{1,20}( [A-Z][a-z'-]{1,20}){0,2}$")
DOB = re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}$")
SSN = re.compile(r"^\d{3}-\d{2}-\d{4}$")
EMBEDDED_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")
EMBEDDED_PHONE = re.compile(r"\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")

TOLL_FREE = re.compile(r"^\D*1?\D*8(00|33|44|55|66|77|88)\D")


def personal_phones(text: str) -> list:
    """Phone numbers in text, minus toll-free numbers (800, 888, ...), which are business lines."""
    return [m.group(0) for m in EMBEDDED_PHONE.finditer(text) if not TOLL_FREE.match(m.group(0) + " ")]


def _is_personal_phone(v: str) -> bool:
    return bool(PHONE.match(v)) and not TOLL_FREE.match(v + " ")


VALUE_TESTS = {
    "email": lambda v: bool(EMAIL.match(v)),
    "phone": _is_personal_phone,
    "person_name": lambda v: bool(PERSON.match(v)),
    "street_address": lambda v: bool(STREET.match(v)),
    "postal_code": lambda v: bool(ZIP.match(v)),
    "vin": is_valid_vin,
    "date_of_birth": lambda v: bool(DOB.match(v)),
    "government_id": lambda v: bool(SSN.match(v)),
}
# Value patterns strong enough to flag a column even when its name gives no hint.
STRONG_VALUE_TYPES = ["email", "phone", "vin", "government_id"]
LABELS = {"email": "email address", "phone": "phone number", "person_name": "person name",
          "street_address": "street address", "postal_code": "postal code", "vin": "VIN linked to an owner",
          "date_of_birth": "date of birth", "government_id": "government ID", "free_text": "personal data in free text"}


@dataclass
class Suggestion:
    schema: str
    table: str
    column: str
    pii_type: str
    confidence: float
    evidence: str
    sampled: int
    examples: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.schema}.{self.table}.{self.column}"

    def to_dict(self) -> Dict:
        return {"column": self.key, "pii_type": self.pii_type, "label": LABELS[self.pii_type],
                "confidence": round(self.confidence, 2), "evidence": self.evidence, "sampled": self.sampled,
                "examples": self.examples}


def mask(value: str) -> str:
    """Show enough of a value for a steward to judge it without exposing it."""
    v = value.strip()
    v = EMBEDDED_EMAIL.sub(lambda m: m.group(0)[0] + "***@" + m.group(0).split("@")[-1], v)
    v = EMBEDDED_PHONE.sub(lambda m: "(***) ***-" + m.group(0)[-4:], v)
    if v != value.strip():
        return v[:90]
    if len(v) <= 3:
        return "*" * len(v)
    return v[:2] + "*" * min(len(v) - 4, 10) + v[-2:]


def _ratio(values: List[str], test) -> float:
    return sum(1 for v in values if test(v.strip())) / len(values) if values else 0.0


def score_column(column: Column, values: List[str]) -> Optional[Suggestion]:
    name = column.name.lower()
    best: Optional[Suggestion] = None

    def consider(pii_type: str, name_hit: bool, ratio: float, evidence: str) -> None:
        nonlocal best
        score = 0.35 * name_hit + 0.65 * ratio
        if best is None or score > best.confidence:
            examples = [mask(v) for v in values if VALUE_TESTS[pii_type](v.strip())][:2]
            best = Suggestion(column.schema, column.table, column.name, pii_type, score, evidence, len(values),
                              examples)

    for pii_type, rule in NAME_RULES.items():
        hit = bool(rule.search(name))
        if not hit and pii_type not in STRONG_VALUE_TYPES:
            continue
        ratio = _ratio(values, VALUE_TESTS[pii_type])
        if not hit and ratio < 0.6:
            continue
        pct = round(ratio * 100)
        label = LABELS[pii_type]
        article = "an" if label[0] in "aeiou" else "a"
        what = f"{pct}% of {len(values)} sampled values look like {article} {label}"
        consider(pii_type, hit, ratio, ("Column name and " if hit else "") + what)

    if FREE_TEXT_NAME.search(name) and values:
        matched = [v for v in values if EMBEDDED_EMAIL.search(v) or personal_phones(v)]
        hits = len(matched)
        if hits:
            ratio = hits / len(values)
            # Any personal data in free text is a risk, so a few hits is enough evidence.
            score = min(1.0, 0.35 + 0.65 * min(1.0, ratio * 8))
            if best is None or score > best.confidence:
                best = Suggestion(column.schema, column.table, column.name, "free_text", score,
                                  f"{hits} of {len(values)} sampled entries contain an email address or phone number",
                                  len(values), [mask(v) for v in matched[:2]])
    return best


def suggest(catalog: Catalog, columns: List[Column], cfg: Dict, sample_size: int = 300) -> List[Suggestion]:
    tag = cfg["tags"]["classification"]
    threshold = float(cfg.get("pii_suggestion_threshold", 0.5))
    out = []
    for col in columns:
        if tag in col.tags:  # already reviewed
            continue
        if not any(t in col.data_type.upper() for t in ("CHAR", "STRING", "TEXT")):
            continue
        values = catalog.sample(col.schema, col.table, col.name, sample_size)
        s = score_column(col, values)
        if s and s.confidence >= threshold:
            out.append(s)
    return sorted(out, key=lambda s: (-s.confidence, s.key))
