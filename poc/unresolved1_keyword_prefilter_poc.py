#!/usr/bin/env python3
"""
PoC for unresolved item #1:
Whether a keyword prefilter (e.g., Aho-Corasick) may skip even Regex/Checksum.

This script demonstrates a correctness failure mode:
structured PII (e.g., Korean RRN) can exist in keyword-less text (numeric-only tables),
so "no keyword => skip regex" can miss detections.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Iterable


# Keep source ASCII-only via \u escapes.
KEYWORDS = [
    "\uc8fc\ubbfc",  # "resident"
    "\uc8fc\ubbfc\ub4f1\ub85d\ubc88\ud638",  # "resident registration number"
    "\uc804\ud654",  # "phone"
    "\uce74\ub4dc",  # "card"
    "\uc774\uba54\uc77c",  # "email"
    "\uc5f0\ub77d\ucc98",  # "contact"
]


RRN_RE = re.compile(r"\b(\d{6})[- ]?(\d{7})\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b")


def keyword_hit(text: str, keywords: Iterable[str] = KEYWORDS) -> bool:
    return any(k in text for k in keywords)


def rrn_checksum_ok(rrn_13_digits: str) -> bool:
    """
    Korean RRN checksum (13 digits):
    weights: [2,3,4,5,6,7,8,9,2,3,4,5] for the first 12 digits.
    check digit: (11 - (sum % 11)) % 10
    """
    if not (len(rrn_13_digits) == 13 and rrn_13_digits.isdigit()):
        return False
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    s = sum(int(d) * w for d, w in zip(rrn_13_digits[:12], weights))
    check = (11 - (s % 11)) % 10
    return check == int(rrn_13_digits[-1])


def generate_valid_rrn(rng: random.Random) -> str:
    # This generates a checksum-valid 13-digit string.
    # It does not try to guarantee a real-world-valid date/region code.
    first12 = "".join(str(rng.randrange(10)) for _ in range(12))
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    s = sum(int(d) * w for d, w in zip(first12, weights))
    check = (11 - (s % 11)) % 10
    return first12 + str(check)


@dataclass(frozen=True)
class Finding:
    kind: str
    value: str
    checksum_ok: bool | None = None


def scan_structured(text: str) -> list[Finding]:
    findings: list[Finding] = []

    for m in RRN_RE.finditer(text):
        rrn = (m.group(1) + m.group(2)).strip()
        findings.append(Finding(kind="RRN", value=f"{m.group(1)}-{m.group(2)}", checksum_ok=rrn_checksum_ok(rrn)))

    for m in EMAIL_RE.finditer(text):
        findings.append(Finding(kind="EMAIL", value=m.group(0), checksum_ok=None))

    for m in PHONE_RE.finditer(text):
        findings.append(Finding(kind="PHONE", value=m.group(0), checksum_ok=None))

    return findings


def strategy_skip_regex_if_no_keyword(text: str) -> list[Finding]:
    if not keyword_hit(text):
        return []
    return scan_structured(text)


def strategy_always_regex(text: str) -> list[Finding]:
    return scan_structured(text)


def main() -> None:
    rng = random.Random(42)
    rrn_digits = generate_valid_rrn(rng)

    examples = [
        # Keyword-less numeric-only lines: plausible in spreadsheets/tables.
        f"{rrn_digits}  {rrn_digits}  {rrn_digits}",
        f"01012345678 {rrn_digits} user@example.com",
        # Keyword-present line: common in narrative docs.
        f"\uc8fc\ubbfc\ub4f1\ub85d\ubc88\ud638: {rrn_digits[:6]}-{rrn_digits[6:]}\n",
    ]

    print("KEYWORDS:", ", ".join(KEYWORDS))
    print()
    for i, text in enumerate(examples, 1):
        kh = keyword_hit(text)
        s1 = strategy_skip_regex_if_no_keyword(text)
        s2 = strategy_always_regex(text)
        print(f"[example {i}] keyword_hit={kh}")
        print("text:", repr(text))
        print("skip_regex_if_no_keyword findings:", s1)
        print("always_regex findings:", s2)
        print()

    # Show the minimal correctness claim: there exists keyword-less text with valid RRNs.
    numeric_only = f"{rrn_digits} {rrn_digits}"
    assert not keyword_hit(numeric_only)
    rrn_findings = [f for f in scan_structured(numeric_only) if f.kind == "RRN" and f.checksum_ok]
    print("ASSERTION:")
    print("- keyword-less numeric-only input can contain checksum-valid RRNs:", bool(rrn_findings))


if __name__ == "__main__":
    main()
