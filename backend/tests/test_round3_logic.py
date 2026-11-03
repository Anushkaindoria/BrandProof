"""Round 3 logic tests: audit engine, correction engine, knowledge extraction, passport signing.

These use plain stand-in records, so they need no database and no network.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

from app.audit import run_rules_audit, sentence_spans
from app.corrections import apply_changes, build_rewrite
from app.extraction import candidates_from_gemini, extract_with_rules, locate_quote
from app.passport import sign, verify_passport, verify_signature


def fact(id, key, value, product="NovaTech X1"):
    return NS(id=id, key=key, product=product, value=value, source_reference="brief p. 2", excerpt=f"{key}: {value}", active=True)


FACTS = [
    fact(1, "battery_capacity", "5000 mAh"),
    fact(2, "water_resistance", "Not officially certified"),
    fact(3, "warranty", "1 year"),
    fact(4, "screen_size", "6.1 inches"),
]
SUPERLATIVE = NS(id=10, name="Unsupported superlatives", rule_type="superlative", rule_value="best|greatest|#1", description="Needs proof.", source_reference="policy p. 4", active=True)
NO_GUARANTEE = NS(id=11, name="No guarantee", rule_type="prohibited_claim", rule_value="guaranteed", description="No guarantees.", source_reference="policy p. 5", active=True)
DISCLAIMER = NS(id=12, name="Disclaimer", rule_type="required_phrase", rule_value="Terms apply", description="", source_reference="policy p. 6", active=True)
TERMS = [NS(id=20, prohibited="seamless", replacement="simple", active=True)]
DEMO_AD = "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!"


def keys(text, policies=(SUPERLATIVE,), terms=TERMS):
    return {finding.issue_key for finding in run_rules_audit(text, FACTS, list(policies), terms)}


# --- audit engine ---------------------------------------------------------


def test_demo_ad_still_produces_the_three_expected_findings():
    assert {"battery-mismatch", "waterproof-unsupported", "unsupported-superlative"} <= keys(DEMO_AD)


def test_admin_added_numeric_fact_is_enforced():
    assert "screen-size-mismatch" in keys("A bright 6.7-inch display.")
    assert "screen-size-supported" in keys("A bright 6.1-inch display.")


def test_unrelated_years_are_not_a_warranty_mismatch():
    assert "warranty-mismatch" not in keys("Includes 5 years of software updates.")
    assert "warranty-mismatch" in keys("Comes with a 2 year warranty.")


def test_decimal_numbers_do_not_split_sentences():
    spans = sentence_spans("A 6.1 inches screen. Another sentence!")
    assert len(spans) == 2


def test_honest_negation_is_not_flagged_but_later_claim_is():
    assert "waterproof-unsupported" not in keys("Water resistance is not officially certified.")
    assert "waterproof-unsupported" not in keys("The phone is not waterproof.")
    assert "waterproof-unsupported" in keys("No rating is claimed. It is waterproof though.")


def test_findings_carry_a_clean_replacement_not_instruction_text():
    findings = {f.issue_key: f for f in run_rules_audit(DEMO_AD, FACTS, [SUPERLATIVE], TERMS)}
    assert findings["battery-mismatch"].replacement == "5000 mAh"
    assert not findings["waterproof-unsupported"].suggested_correction.startswith("Replace")


# --- correction engine ----------------------------------------------------


def test_rewrite_of_demo_ad_passes_rule_verification():
    result = build_rewrite(DEMO_AD, FACTS, [SUPERLATIVE], TERMS)
    assert result["verification"]["passed"] is True
    assert "5000 mAh" in result["rewritten_text"]
    assert "7000" not in result["rewritten_text"] and "waterproof" not in result["rewritten_text"].lower()
    assert all(change["reason"] for change in result["changes"])


def test_rewrite_handles_prohibited_claim_terminology_and_required_phrase():
    text = "Guaranteed everyday performance, seamless."
    result = build_rewrite(text, FACTS, [NO_GUARANTEE, DISCLAIMER], TERMS)
    assert result["verification"]["passed"] is True
    assert "simple" in result["rewritten_text"] and "Terms apply" in result["rewritten_text"]
    assert result["rewritten_text"].startswith("Everyday performance, simple.")


def test_ai_edit_that_adds_an_unapproved_number_is_dropped():
    ai = [
        {"issue_key": "ok", "claim_text": "Great battery life", "suggested_correction": "Dependable battery life", "explanation": "Hype."},
        {"issue_key": "bad", "claim_text": "Amazing speed", "suggested_correction": "a 9000 mAh powerhouse", "explanation": "Hype."},
        {"issue_key": "gone", "claim_text": "text that is not in the draft", "suggested_correction": "x", "explanation": "x"},
    ]
    result = build_rewrite("Great battery life. Amazing speed.", FACTS, [], [], ai)
    assert result["rewritten_text"] == "Dependable battery life. Amazing speed."
    assert result["dropped_ai_changes"] == 1
    assert result["method"] == "gemini+rules"


def test_apply_changes_is_position_safe_with_multiple_edits():
    result = build_rewrite("It has 7000 mAh and a 2 year warranty.", FACTS, [], [])
    assert result["rewritten_text"] == "It has 5000 mAh and a 1 year warranty."
    assert apply_changes(result["original_text"], []) == result["original_text"]


# --- knowledge extraction -------------------------------------------------

GUIDE = """[Page 1]
NovaTech X1 Brand Guide
[Page 2]
Battery capacity: 5000 mAh.
Charging speed: 65 W
Never describe NovaTech X1 as waterproof.
Avoid “seamless”; use “simple” instead.
All ads must include the disclaimer "Terms apply".
Avoid unsupported superlatives.
Note: please read this carefully.
"""


def test_rules_extractor_finds_facts_terms_and_policies_with_pages():
    items = extract_with_rules(GUIDE, "NovaTech X1")
    by_type = {}
    for item in items:
        by_type.setdefault(item.item_type, []).append(item)
    assert {i.payload["key"] for i in by_type["fact"]} == {"battery_capacity", "charging_speed"}
    assert by_type["term"][0].payload == {"prohibited": "seamless", "replacement": "simple"}
    assert {i.payload["rule_type"] for i in by_type["policy"]} >= {"prohibited_claim", "required_disclaimer", "superlative"}
    assert all(i.page_reference == "Page 2" for i in items)
    assert not any(i.payload.get("key") == "note" for i in by_type["fact"])


def test_gemini_proposals_are_dropped_unless_quote_and_value_are_grounded():
    raw = {
        "facts": [
            {"key": "Battery Capacity", "value": "5000 mAh", "quote": "Battery capacity: 5000 mAh."},
            {"key": "battery_life", "value": "48 hours", "quote": "Battery capacity: 5000 mAh."},
            {"key": "warranty", "value": "1 year", "quote": "This sentence is not in the document."},
        ],
        "policies": [
            {"name": "bad type", "rule_type": "nonsense", "rule_value": "x", "quote": "Never describe NovaTech X1 as waterproof."},
            {"name": "bad value", "rule_type": "prohibited_claim", "rule_value": "magic", "quote": "Never describe NovaTech X1 as waterproof."},
        ],
    }
    candidates, dropped = candidates_from_gemini(raw, GUIDE, "NovaTech X1")
    assert [(c.item_type, c.payload["key"]) for c in candidates] == [("fact", "battery_capacity")]
    assert dropped == 4
    assert candidates[0].page_reference == "Page 2"


def test_quote_matching_tolerates_whitespace_and_curly_quotes():
    assert locate_quote(GUIDE, "battery   capacity: 5000 MAh.") >= 0
    assert locate_quote(GUIDE, 'Avoid "seamless"; use "simple" instead.') >= 0
    assert locate_quote(GUIDE, "nothing like this") == -1


# --- passport -------------------------------------------------------------


def make_passport():
    passport = {"content_id": 1, "version_id": 2, "content_hash": "abc", "fact_versions": [{"id": 1, "version": 1}], "reviewer": "Jordan"}
    passport["signature_algorithm"] = "HMAC-SHA256"
    passport["signature"] = sign(passport, "secret")
    return passport


def test_signed_passport_verifies_and_tampering_is_detected():
    passport = make_passport()
    assert verify_signature(passport, "secret")[0] is True
    assert verify_signature(passport, "other-secret")[0] is False
    tampered = {**passport, "reviewer": "Someone Else"}
    assert verify_signature(tampered, "secret")[0] is False
    assert verify_signature({k: v for k, v in passport.items() if k != "signature"}, "secret")[0] is False


def test_passport_verification_reports_each_failure_reason():
    passport = make_passport()
    good = verify_passport(passport, secret="secret", version_text_hash="abc", record_hash="abc", changed_dependencies=[], item_status="approved")
    assert good["valid"] is True
    bad = verify_passport(passport, secret="secret", version_text_hash="zzz", record_hash="abc", changed_dependencies=["battery_capacity v1→v2"], item_status="needs_revalidation")
    failed = {check["name"] for check in bad["checks"] if not check["ok"]}
    assert failed == {"content_hash", "evidence_current", "approval_state"}


# --- evaluation set regression guard --------------------------------------


def test_evaluation_set_baseline_has_no_false_positives_and_full_easy_recall():
    path = Path(__file__).resolve().parents[2] / "eval" / "run_eval.py"
    spec = importlib.util.spec_from_file_location("run_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    facts, policies, terms = module.load_context()
    claims = json.loads((path.parent / "claims.json").read_text())["claims"]
    rows, _ = module.evaluate(claims, facts, policies, terms, use_gemini=False)
    assert len(claims) >= 50
    overall = module.metrics(rows)
    easy = module.metrics([row for row in rows if not row["hard"]])
    assert overall["false_positive_rate"] == 0
    assert easy["recall"] == 1 and easy["precision"] == 1


def test_accepting_only_some_changes_applies_only_those_and_reports_what_remains():
    full = build_rewrite(DEMO_AD, FACTS, [SUPERLATIVE], TERMS)
    battery = next(c for c in full["changes"] if c["issue_key"] == "battery-mismatch")
    partial = build_rewrite(DEMO_AD, FACTS, [SUPERLATIVE], TERMS, accepted_ids={battery["id"]})
    assert "5000 mAh" in partial["rewritten_text"] and "waterproof" in partial["rewritten_text"].lower()
    assert partial["verification"]["passed"] is False
    assert {item["issue_key"] for item in partial["verification"]["remaining"]} == {"waterproof-unsupported", "unsupported-superlative"}
    assert build_rewrite(DEMO_AD, FACTS, [SUPERLATIVE], TERMS, accepted_ids=set())["rewritten_text"] == DEMO_AD
