#!/usr/bin/env python3
"""
PoC for unresolved item #7:
When to introduce a rule definition format (code-defined vs JSON/YAML schema).

This PoC demonstrates:
- A minimal "enum-only" JSON rule schema (no expressions)
- Signature verification of a rule bundle (Ed25519)
- Runtime rule update (v1 vs v2) without code changes
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


# ASCII-only via \u escapes.
KW_RRN = ["\uc8fc\ubbfc\ub4f1\ub85d\ubc88\ud638", "\uc8fc\ubbfc"]
KW_PHONE = ["\uc804\ud654", "\uc5f0\ub77d\ucc98"]


ALLOWED_KINDS = {"RRN", "PHONE", "EMAIL"}
ALLOWED_VALIDATORS = {"RRN_CHECKSUM"}


def canonical_json_bytes(obj: Any) -> bytes:
    # Stable bytes for signing/verifying.
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def rrn_checksum_ok(rrn_13_digits: str) -> bool:
    if not (len(rrn_13_digits) == 13 and rrn_13_digits.isdigit()):
        return False
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    s = sum(int(d) * w for d, w in zip(rrn_13_digits[:12], weights))
    check = (11 - (s % 11)) % 10
    return check == int(rrn_13_digits[-1])


def sign_bundle(priv: Ed25519PrivateKey, bundle_obj: Any) -> bytes:
    return priv.sign(canonical_json_bytes(bundle_obj))


def verify_bundle(pub: Ed25519PublicKey, bundle_obj: Any, sig: bytes) -> None:
    pub.verify(sig, canonical_json_bytes(bundle_obj))


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str
    regex: re.Pattern[str]
    validators: list[str]
    window_chars: int
    positive_keywords: list[str]
    negative_keywords: list[str]


def load_rules(bundle_obj: dict[str, Any]) -> list[Rule]:
    if not isinstance(bundle_obj, dict):
        raise ValueError("bundle must be an object")
    if "rules" not in bundle_obj or not isinstance(bundle_obj["rules"], list):
        raise ValueError("bundle.rules must be a list")

    out: list[Rule] = []
    for i, r in enumerate(bundle_obj["rules"]):
        if not isinstance(r, dict):
            raise ValueError(f"rule[{i}] must be an object")
        rid = r.get("id")
        kind = r.get("kind")
        regex_s = r.get("regex")
        validators = r.get("validators", [])
        ctx = r.get("context", {})
        window_chars = ctx.get("window_chars", 0)
        pos = ctx.get("positive_keywords", [])
        neg = ctx.get("negative_keywords", [])

        if not isinstance(rid, str) or not rid:
            raise ValueError(f"rule[{i}].id required")
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"rule[{i}].kind invalid: {kind!r}")
        if not isinstance(regex_s, str) or not regex_s:
            raise ValueError(f"rule[{i}].regex required")
        if not isinstance(validators, list) or any(v not in ALLOWED_VALIDATORS for v in validators):
            raise ValueError(f"rule[{i}].validators invalid: {validators!r}")
        if not isinstance(window_chars, int) or window_chars < 0 or window_chars > 400:
            raise ValueError(f"rule[{i}].context.window_chars invalid: {window_chars!r}")
        if not (isinstance(pos, list) and all(isinstance(x, str) for x in pos)):
            raise ValueError(f"rule[{i}].context.positive_keywords invalid")
        if not (isinstance(neg, list) and all(isinstance(x, str) for x in neg)):
            raise ValueError(f"rule[{i}].context.negative_keywords invalid")

        out.append(
            Rule(
                id=rid,
                kind=kind,
                regex=re.compile(regex_s),
                validators=list(validators),
                window_chars=window_chars,
                positive_keywords=pos,
                negative_keywords=neg,
            )
        )
    return out


@dataclass(frozen=True)
class Finding:
    rule_id: str
    kind: str
    value: str
    verdict: str  # CONFIRMED | SUSPECT | DISMISSED
    positive_hits: list[str]
    negative_hits: list[str]


def scan_text(text: str, rules: list[Rule]) -> list[Finding]:
    findings: list[Finding] = []

    for rule in rules:
        for m in rule.regex.finditer(text):
            value = m.group(0)
            start, end = m.span()

            # Context window.
            win = rule.window_chars
            left = max(0, start - win)
            right = min(len(text), end + win)
            ctx = text[left:right]
            pos_hits = [k for k in rule.positive_keywords if k and (k in ctx)]
            neg_hits = [k for k in rule.negative_keywords if k and (k in ctx)]

            verdict = "SUSPECT"
            if "RRN_CHECKSUM" in rule.validators and rule.kind == "RRN":
                digits = re.sub(r"[^0-9]", "", value)
                verdict = "CONFIRMED" if rrn_checksum_ok(digits) else "DISMISSED"
            else:
                # For PoC: treat keyword presence as a weak signal (still "SUSPECT").
                verdict = "SUSPECT"

            findings.append(
                Finding(
                    rule_id=rule.id,
                    kind=rule.kind,
                    value=value,
                    verdict=verdict,
                    positive_hits=pos_hits,
                    negative_hits=neg_hits,
                )
            )

    return findings


def main() -> None:
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()

    bundle_v1 = {
        "version": 1,
        "rules": [
            {
                "id": "rrn_v1",
                "kind": "RRN",
                "regex": r"\b\d{6}[- ]?\d{7}\b",
                "validators": ["RRN_CHECKSUM"],
                "context": {"window_chars": 40, "positive_keywords": KW_RRN, "negative_keywords": []},
            },
            {
                "id": "phone_mobile_v1",
                "kind": "PHONE",
                "regex": r"\b01[016789][ -]?\d{3,4}[ -]?\d{4}\b",
                "validators": [],
                "context": {"window_chars": 40, "positive_keywords": KW_PHONE, "negative_keywords": []},
            },
        ],
    }

    bundle_v2 = {
        **bundle_v1,
        "version": 2,
        "rules": [
            bundle_v1["rules"][0],
            {
                # Change: include VoIP prefix 070 (policy/rule update without code)
                "id": "phone_mobile_or_voip_v2",
                "kind": "PHONE",
                "regex": r"\b(?:01[016789]|070)[ -]?\d{3,4}[ -]?\d{4}\b",
                "validators": [],
                "context": {"window_chars": 40, "positive_keywords": KW_PHONE, "negative_keywords": []},
            },
        ],
    }

    sig_v1 = sign_bundle(sk, bundle_v1)
    sig_v2 = sign_bundle(sk, bundle_v2)

    # Verify signature before "apply policy bundle".
    verify_bundle(pk, bundle_v1, sig_v1)
    verify_bundle(pk, bundle_v2, sig_v2)

    rules_v1 = load_rules(bundle_v1)
    rules_v2 = load_rules(bundle_v2)

    sample_rrn = "104332-1819601"  # synthetic checksum-valid (from unresolved #1 PoC)
    sample = (
        f"numeric_only: {sample_rrn}\\n"
        f"mobile: 010-1234-5678\\n"
        f"voip: 070-1234-5678\\n"
    )

    f1 = scan_text(sample, rules_v1)
    f2 = scan_text(sample, rules_v2)

    print("bundle_v1_findings:")
    for f in f1:
        print(" ", f)
    print()

    print("bundle_v2_findings:")
    for f in f2:
        print(" ", f)
    print()

    # Tamper test: change regex in v1 but keep old signature -> verify must fail.
    tampered = json.loads(json.dumps(bundle_v1))
    tampered["rules"][1]["regex"] = r"\b010\d+\b"
    try:
        verify_bundle(pk, tampered, sig_v1)
        print("tamper_verify=UNEXPECTED_OK")
    except Exception:
        print("tamper_verify=FAIL_OK")


if __name__ == "__main__":
    main()

