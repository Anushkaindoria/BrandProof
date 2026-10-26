from app.audit import run_rules_audit
from app.models import ApprovedFact, Policy, Terminology


def demo_context():
    facts = [
        ApprovedFact(id=1, key="battery_capacity", product="NovaTech X1", value="5000 mAh", source_reference="brief p. 2", excerpt="Battery capacity: 5000 mAh."),
        ApprovedFact(id=2, key="water_resistance", product="NovaTech X1", value="Not officially certified", source_reference="brief p. 2", excerpt="Water resistance: Not officially certified."),
        ApprovedFact(id=3, key="warranty", product="NovaTech X1", value="1 year", source_reference="brief p. 2", excerpt="Warranty: 1 year."),
    ]
    policies = [Policy(id=4, name="Unsupported superlatives", rule_type="superlative", rule_value="best", description="Superlatives require approved evidence.", source_reference="policy p. 4")]
    terminology = [Terminology(id=5, prohibited="seamless", replacement="simple", active=True)]
    return facts, policies, terminology


def test_demo_ad_finds_conflict_and_unsupported_claims():
    facts, policies, terminology = demo_context()
    findings = run_rules_audit("Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!", facts, policies, terminology)
    keys = {finding.issue_key for finding in findings}
    assert {"battery-mismatch", "waterproof-unsupported", "unsupported-superlative"}.issubset(keys)
    battery = next(finding for finding in findings if finding.issue_key == "battery-mismatch")
    assert battery.evidence_id == 1
    assert battery.verification_status == "Contradicted"


def test_supported_numerical_claim_has_source_and_no_conflict():
    facts, policies, terminology = demo_context()
    findings = run_rules_audit("The NovaTech X1 includes a 5000 mAh battery.", facts, policies, terminology)
    assert len(findings) == 1
    assert findings[0].verification_status == "Supported"
    assert findings[0].evidence_id == 1


def test_prohibited_terminology_is_detected():
    facts, policies, terminology = demo_context()
    findings = run_rules_audit("A seamless everyday experience.", facts, policies, terminology)
    assert findings[0].issue_key == "term-5"
    assert findings[0].suggested_correction == "simple"
