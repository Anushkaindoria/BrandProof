"""Round 3 API tests: governance gates, correction engine, knowledge extraction, passport verification."""

import json
import os
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///./test_brandproof.db"

from fastapi.testclient import TestClient

from app.ai import AIFinding
from app.config import settings
from app.db import Base, SessionLocal, engine, ensure_columns
from app.main import app
from app.models import ApprovalRecord
from app.seed import seed_database

ADMIN = {"X-Demo-Role": "admin"}
REVIEWER = {"X-Demo-Role": "reviewer"}
CREATOR = {"X-Demo-Role": "creator"}
BAD_AD = "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!"


def setup_module():
    Base.metadata.drop_all(bind=engine)
    seed_database(reset=True)


def new_item(client, title, text):
    return client.post("/api/content", json={"title": title, "content_type": "Advertisement", "context": "NovaTech X1", "text": text}).json()


def approve_clean(client, title, text):
    item = new_item(client, title, text)
    client.post(f"/api/content/{item['id']}/audit")
    assert client.post(f"/api/content/{item['id']}/submit").status_code == 200
    approved = client.post(f"/api/content/{item['id']}/review", headers=REVIEWER, json={"decision": "approve", "comment": "ok"})
    assert approved.status_code == 200
    return item


# --- governance gates -------------------------------------------------------


def test_creator_cannot_dismiss_high_severity_finding_but_reviewer_can():
    with TestClient(app) as client:
        item = new_item(client, "Dismiss gate", BAD_AD)
        findings = client.post(f"/api/content/{item['id']}/audit").json()["audit"]["findings"]
        high = next(f for f in findings if f["severity"] == "high")
        blocked = client.post(f"/api/findings/{high['id']}/resolve", headers=CREATOR, json={"action": "dismiss", "reason": "ignore"})
        assert blocked.status_code == 403
        allowed = client.post(f"/api/findings/{high['id']}/resolve", headers=REVIEWER, json={"action": "dismiss", "reason": "Reviewed with legal"})
        assert allowed.status_code == 200
        assert "reviewer" in allowed.json()["resolved_by"]
        # a medium finding can still be resolved by the creator
        medium = next(f for f in findings if f["severity"] == "medium")
        assert client.post(f"/api/findings/{medium['id']}/resolve", headers=CREATOR, json={"action": "accept", "reason": "ok"}).status_code == 200


def test_submit_requires_an_audit_and_no_open_findings():
    with TestClient(app) as client:
        item = new_item(client, "Unaudited", "NovaTech X1 includes a 5000 mAh battery.")
        assert client.post(f"/api/content/{item['id']}/submit").status_code == 409
        bad = new_item(client, "Bad submit", BAD_AD)
        client.post(f"/api/content/{bad['id']}/audit")
        assert client.post(f"/api/content/{bad['id']}/submit").status_code == 409


def test_created_by_uses_the_acting_user_not_a_hardcoded_name():
    with TestClient(app) as client:
        item = new_item(client, "Author", "NovaTech X1.")
        assert item["current_version"]["created_by"] == "Maya Chen"


def test_deactivating_a_fact_flags_approved_dependent_content():
    with TestClient(app) as client:
        fact = client.post("/api/facts", headers=ADMIN, json={"key": "colour_count", "value": "3 colours"}).json()
        item = approve_clean(client, "Colours", "NovaTech X1 comes in 3 colours.")
        flagged = client.get(f"/api/content/{item['id']}").json()
        assert flagged["status"] == "approved"
        response = client.post(f"/api/facts/{fact['id']}/deactivate", headers=ADMIN)
        assert response.status_code == 200 and response.json()["affected_versions"] >= 1
        assert client.get(f"/api/content/{item['id']}").json()["status"] == "needs_revalidation"


def test_reaudit_does_not_duplicate_dependencies():
    with TestClient(app) as client:
        item = new_item(client, "Reaudit", BAD_AD)
        for _ in range(3):
            client.post(f"/api/content/{item['id']}/audit")
        from app.models import Dependency
        with SessionLocal() as db:
            rows = db.query(Dependency).filter(Dependency.content_version_id == item["current_version"]["id"]).all()
            assert len({(r.dependency_type, r.dependency_id) for r in rows}) == len(rows)


# --- smart correction engine ------------------------------------------------


def test_rewrite_endpoint_proposes_explained_changes_that_pass_verification():
    with TestClient(app) as client:
        item = new_item(client, "Rewrite", BAD_AD)
        client.post(f"/api/content/{item['id']}/audit")
        response = client.post(f"/api/content/{item['id']}/rewrite", headers=CREATOR, json={})
        assert response.status_code == 200
        data = response.json()
        assert data["verification"]["passed"] is True
        assert len(data["changes"]) >= 3 and all(change["reason"] for change in data["changes"])
        assert "5000 mAh" in data["rewritten_text"]
        # nothing is saved by proposing a rewrite
        assert client.get(f"/api/content/{item['id']}").json()["current_version"]["text"] == BAD_AD


def test_rewrite_of_unsaved_text_and_role_gate():
    with TestClient(app) as client:
        item = new_item(client, "Rewrite unsaved", "NovaTech X1.")
        data = client.post(f"/api/content/{item['id']}/rewrite", headers=CREATOR, json={"text": "A 7000 mAh battery."}).json()
        assert data["rewritten_text"] == "A 5000 mAh battery."
        assert client.post(f"/api/content/{item['id']}/rewrite", headers=REVIEWER, json={}).status_code == 403


# --- Gemini auditor ---------------------------------------------------------


def test_ai_findings_are_tagged_and_flow_into_rewrite_after_rule_verification():
    ai = [AIFinding(issue_key="tone-hype", category="Tone", severity="medium", claim_text="Absolutely thrilling", explanation="Over-promotional tone.", verification_status="Needs interpretation", suggested_correction="Reliable", confidence="medium")]
    with patch("app.main.call_gemini", return_value=ai), patch.object(settings, "llm_api_key", "test-key"), patch.object(settings, "llm_provider", "gemini"), TestClient(app) as client:
        item = new_item(client, "AI tone", "Absolutely thrilling battery. NovaTech X1 has 5000 mAh.")
        audit = client.post(f"/api/content/{item['id']}/audit").json()["audit"]
        tone = next(f for f in audit["findings"] if f["issue_key"] == "tone-hype")
        assert tone["origin"] == "ai" and audit["provider_mode"] == "gemini"
        rewrite = client.post(f"/api/content/{item['id']}/rewrite", headers=CREATOR, json={}).json()
        assert rewrite["method"] == "gemini+rules" and "Reliable battery" in rewrite["rewritten_text"]


def test_provider_failure_falls_back_to_rules_and_says_so():
    from app.ai import AIProviderError

    with patch("app.main.call_gemini", side_effect=AIProviderError("gemini provider request failed: HTTP Error 503")), patch.object(settings, "llm_api_key", "test-key"), patch.object(settings, "llm_provider", "gemini"), TestClient(app) as client:
        item = new_item(client, "Fallback", BAD_AD)
        audit = client.post(f"/api/content/{item['id']}/audit").json()["audit"]
        assert audit["provider_mode"] == "gemini-error-fallback" and "503" in audit["provider_error"]
        assert {"battery-mismatch", "waterproof-unsupported"} <= {f["issue_key"] for f in audit["findings"]}


def test_ai_connection_test_is_admin_only_and_reports_rules_only_without_a_key():
    with TestClient(app) as client:
        assert client.post("/api/ai/test", headers=CREATOR).status_code == 403
        result = client.post("/api/ai/test", headers=ADMIN).json()
        assert result["ok"] is False and result["provider"] == "rules-only"


# --- knowledge extraction ---------------------------------------------------

GUIDE = b"""Charging speed: 65 W
Never describe NovaTech X1 as unbreakable.
Avoid "frictionless"; use "easy" instead.
"""


def upload_guide(client, name="guide.txt", body=GUIDE):
    assert client.post("/api/content/upload", headers=ADMIN, files={"file": (name, body, "text/plain")}).status_code == 200
    return next(d for d in client.get("/api/knowledge").json()["documents"] if d["filename"] == name)


def test_extraction_proposes_but_only_approval_creates_evidence():
    with TestClient(app) as client:
        document = upload_guide(client)
        assert client.post(f"/api/documents/{document['id']}/extract", headers=CREATOR).status_code == 403
        result = client.post(f"/api/documents/{document['id']}/extract", headers=ADMIN).json()
        kinds = {item["item_type"] for item in result["items"]}
        assert {"fact", "term", "policy"} <= kinds
        fact = next(i for i in result["items"] if i["item_type"] == "fact")
        assert fact["quote"] and "65 W" in fact["quote"]
        # nothing is evidence yet
        assert all(f["key"] != "charging_speed" for f in client.get("/api/knowledge").json()["facts"])
        assert client.post(f"/api/proposals/{fact['id']}/approve", headers=CREATOR, json={}).status_code == 403
        approved = client.post(f"/api/proposals/{fact['id']}/approve", headers=ADMIN, json={})
        assert approved.status_code == 200
        facts = {f["key"]: f for f in client.get("/api/knowledge").json()["facts"]}
        assert facts["charging_speed"]["value"] == "65 W" and "guide.txt" in facts["charging_speed"]["source_reference"]
        assert client.post(f"/api/proposals/{fact['id']}/approve", headers=ADMIN, json={}).status_code == 409
        # the approved fact is now enforced by the audit
        item = new_item(client, "Charging", "Charges at 120 W.")
        findings = client.post(f"/api/content/{item['id']}/audit").json()["audit"]["findings"]
        assert any(f["issue_key"] == "charging-speed-mismatch" for f in findings)


def test_reject_and_admin_edit_before_approval():
    with TestClient(app) as client:
        document = upload_guide(client, "guide2.txt", b"Standby time: 300 hours\nAvoid \"clunky\"; use \"sturdy\" instead.\n")
        items = client.post(f"/api/documents/{document['id']}/extract", headers=ADMIN).json()["items"]
        term = next(i for i in items if i["item_type"] == "term")
        rejected = client.post(f"/api/proposals/{term['id']}/reject", headers=ADMIN)
        assert rejected.json()["status"] == "rejected"
        fact = next(i for i in items if i["item_type"] == "fact")
        edited = client.post(f"/api/proposals/{fact['id']}/approve", headers=ADMIN, json={"payload": {"value": "310 hours"}})
        assert edited.status_code == 200
        assert next(f for f in client.get("/api/knowledge").json()["facts"] if f["key"] == "standby_time")["value"] == "310 hours"
        assert all(t["prohibited"] != "clunky" for t in client.get("/api/knowledge").json()["terminology"])


def test_gemini_extraction_drops_ungrounded_items():
    raw = {"facts": [{"key": "ip_rating", "value": "IP68", "quote": "Rated IP68 for dust and water."}, {"key": "invented", "value": "99 hours", "quote": "No such sentence exists."}]}
    with patch("app.main.extract_knowledge", return_value=raw), patch.object(settings, "llm_api_key", "test-key"), patch.object(settings, "llm_provider", "gemini"), TestClient(app) as client:
        document = upload_guide(client, "guide3.txt", b"The phone is Rated IP68 for dust and water.\n")
        result = client.post(f"/api/documents/{document['id']}/extract", headers=ADMIN).json()
        assert result["method"] == "gemini+rules" and result["stats"]["unverified_dropped"] == 1
        assert {i["payload"].get("key") for i in result["items"] if i["item_type"] == "fact"} == {"ip_rating"}


def test_extraction_skips_facts_already_approved():
    with TestClient(app) as client:
        document = upload_guide(client, "guide4.txt", b"Battery capacity: 5000 mAh.\n")
        result = client.post(f"/api/documents/{document['id']}/extract", headers=ADMIN).json()
        assert result["stats"]["already_known"] >= 1 and result["items"] == []


# --- passport ---------------------------------------------------------------


def test_signed_passport_verifies_then_detects_evidence_change_and_tampering():
    with TestClient(app) as client:
        fact = client.post("/api/facts", headers=ADMIN, json={"key": "case_colours", "value": "4 colours"}).json()
        item = approve_clean(client, "Passport", "NovaTech X1 comes in 4 colours.")
        passport = client.get(f"/api/content/{item['id']}/passport").json()
        assert passport["signature"] and passport["signature_algorithm"] == "HMAC-SHA256"
        assert client.get(f"/api/content/{item['id']}/passport/verify").json()["valid"] is True

        # tamper with the stored passport
        with SessionLocal() as db:
            record = db.query(ApprovalRecord).filter(ApprovalRecord.content_version_id == item["current_version"]["id"]).one()
            body = json.loads(record.passport_json)
            body["reviewer"] = "Forged Reviewer"
            record.passport_json = json.dumps(body)
            db.commit()
        broken = client.get(f"/api/content/{item['id']}/passport/verify").json()
        assert broken["valid"] is False and next(c for c in broken["checks"] if c["name"] == "signature")["ok"] is False

        # evidence drift is reported even for an untampered passport
        second = approve_clean(client, "Passport two", "NovaTech X1 comes in 4 colours.")
        client.patch(f"/api/facts/{fact['id']}", headers=ADMIN, json={"value": "5 colours"})
        verdict = client.get(f"/api/content/{second['id']}/passport/verify").json()
        assert verdict["valid"] is False and next(c for c in verdict["checks"] if c["name"] == "evidence_current")["ok"] is False


# --- startup migration ------------------------------------------------------


def test_ensure_columns_adds_missing_columns_without_losing_data(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text

    import app.db as db_module

    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as connection:
        connection.execute(text("CREATE TABLE findings (id INTEGER PRIMARY KEY, audit_run_id INTEGER, issue_key VARCHAR(80), category VARCHAR(60), severity VARCHAR(30), claim_text TEXT, explanation TEXT, verification_status VARCHAR(40), suggested_correction TEXT, confidence VARCHAR(30), resolution_status VARCHAR(30), resolution_reason TEXT, evidence_type VARCHAR(30), evidence_id INTEGER, evidence_label VARCHAR(255), evidence_excerpt TEXT, source_reference VARCHAR(120))"))
        connection.execute(text("INSERT INTO findings (id, issue_key) VALUES (1, 'keep-me')"))
    monkeypatch.setattr(db_module, "engine", old)
    added = ensure_columns()
    assert "findings.origin" in added and "findings.resolved_by" in added
    with old.connect() as connection:
        row = connection.execute(text("SELECT issue_key, origin, resolved_by FROM findings")).one()
    assert tuple(row) == ("keep-me", "rules", "")
