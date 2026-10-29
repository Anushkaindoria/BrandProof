import os
import io
import time
import json
from unittest.mock import patch, MagicMock

from PIL import Image

os.environ["DATABASE_URL"] = "sqlite:///./test_brandproof.db"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.seed import seed_database
from app.storage import LocalStorage
from app.config import settings


def setup_module():
    Base.metadata.drop_all(bind=engine)
    seed_database(reset=True)


def test_health_and_bootstrap():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        bootstrap = client.get("/api/bootstrap?role=creator")
        assert bootstrap.status_code == 200
        assert bootstrap.json()["user"]["role"] == "creator"


def test_audit_revision_and_review_flow():
    with TestClient(app) as client:
        items = client.get("/api/content").json()["items"]
        item = next(item for item in items if "NovaTech" in item["title"])
        audit = client.post(f"/api/content/{item['id']}/audit")
        assert audit.status_code == 200
        assert len(audit.json()["audit"]["findings"]) >= 3

        version = client.post(f"/api/content/{item['id']}/versions", json={"text": "Meet the NovaTech X1 with a 5000 mAh battery and a 1 year warranty."})
        assert version.status_code == 200
        clean_audit = client.post(f"/api/content/{item['id']}/audit")
        assert clean_audit.status_code == 200
        submitted = client.post(f"/api/content/{item['id']}/submit")
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "resubmitted"
        approved = client.post(f"/api/content/{item['id']}/review", json={"decision": "approve", "comment": "Evidence checked."})
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        passport = client.get(f"/api/content/{item['id']}/passport")
        assert passport.status_code == 200
        assert passport.json()["content_hash"] == approved.json()["current_version"]["content_hash"]


def test_upload_rejects_unsupported_type():
    with TestClient(app) as client:
        response = client.post("/api/content/upload", files={"file": ("unsafe.html", b"<script>alert(1)</script>", "text/html")})
        assert response.status_code == 415


def test_backend_role_authorization_and_source_approval():
    with TestClient(app) as client:
        no_role = client.post("/api/facts", json={"key": "screen_size", "value": "6.1 inches"})
        assert no_role.status_code == 401
        creator = client.post("/api/facts", headers={"X-Demo-Role": "creator"}, json={"key": "screen_size", "value": "6.1 inches"})
        assert creator.status_code == 403
        admin = client.post("/api/facts", headers={"X-Demo-Role": "admin"}, json={"key": "screen_size", "value": "6.1 inches"})
        assert admin.status_code == 200

        uploaded = client.post("/api/content/upload", files={"file": ("guidelines.txt", b"Use NovaTech X1 exactly.", "text/plain")})
        assert uploaded.status_code == 200
        documents = client.get("/api/knowledge").json()["documents"]
        document = next(item for item in documents if item["filename"] == "guidelines.txt")
        assert document["status"] == "unreviewed"
        approved = client.post(f"/api/documents/{document['id']}/approve", headers={"X-Demo-Role": "admin"})
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"


def test_claims_are_persisted_and_provider_mode_is_explicit():
    with TestClient(app) as client:
        item = client.post("/api/content", json={"title": "Claims test", "content_type": "Advertisement", "context": "NovaTech X1", "text": "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection. The best phone ever!"}).json()
        response = client.post(f"/api/content/{item['id']}/audit")
        assert response.status_code == 200
        assert len(response.json()["audit"]["claims"]) >= 3
        assert response.json()["audit"]["provider_mode"] == "rules-only"


def test_approval_requires_submitted_clean_version_and_new_version_has_no_old_passport():
    with TestClient(app) as client:
        item = client.post("/api/content", json={"title": "Clean demo", "content_type": "Advertisement", "context": "NovaTech X1", "text": "NovaTech X1 includes a 5000 mAh battery and a 1 year warranty."}).json()
        client.post(f"/api/content/{item['id']}/audit")
        client.post(f"/api/content/{item['id']}/submit")
        approved = client.post(f"/api/content/{item['id']}/review", headers={"X-Demo-Role": "reviewer"}, json={"decision": "approve", "comment": "Reviewed"})
        assert approved.status_code == 200
        new_version = client.post(f"/api/content/{item['id']}/versions", json={"text": "A changed draft."})
        assert new_version.status_code == 200
        assert client.get(f"/api/content/{item['id']}/passport").status_code == 404


def test_policy_compiler_required_phrase_finds_missing_requirement():
    with TestClient(app) as client:
        policy = client.post("/api/policies", headers={"X-Demo-Role": "admin"}, json={"name": "Demo disclaimer", "rule_type": "required_phrase", "rule_value": "Terms apply", "description": "Required disclaimer for this campaign."})
        assert policy.status_code == 200
        item = client.post("/api/content", json={"title": "Disclaimer test", "content_type": "Advertisement", "context": "NovaTech X1", "text": "A NovaTech X1 campaign without the disclaimer."}).json()
        audit = client.post(f"/api/content/{item['id']}/audit")
        assert audit.status_code == 200
        assert any(finding["issue_key"] == f"missing-required-{policy.json()['id']}" for finding in audit.json()["audit"]["findings"])


def test_policy_change_flags_approved_dependent_content():
    with TestClient(app) as client:
        policy = client.post("/api/policies", headers={"X-Demo-Role": "admin"}, json={"name": "No guarantee claims", "rule_type": "prohibited_claim", "rule_value": "guaranteed", "description": "Do not promise guaranteed outcomes."})
        assert policy.status_code == 200
        item = client.post("/api/content", json={"title": "Policy drift test", "content_type": "Advertisement", "context": "NovaTech X1", "text": "Guaranteed everyday performance."}).json()
        audit = client.post(f"/api/content/{item['id']}/audit")
        assert audit.status_code == 200
        target_findings = audit.json()["audit"]["findings"]
        assert any(finding["evidence"]["id"] == policy.json()["id"] for finding in target_findings)
        for finding in target_findings:
            resolved = client.post(f"/api/findings/{finding['id']}/resolve", json={"action": "accept", "reason": "Reviewed by creator"})
            assert resolved.status_code == 200
        assert client.post(f"/api/content/{item['id']}/submit").status_code == 200
        assert client.post(f"/api/content/{item['id']}/review", headers={"X-Demo-Role": "reviewer"}, json={"decision": "approve", "comment": "Policy dependency recorded."}).status_code == 200
        updated = client.patch(f"/api/policies/{policy.json()['id']}", headers={"X-Demo-Role": "admin"}, json={"description": "Updated policy for drift."})
        assert updated.status_code == 200
        assert updated.json()["affected_versions"] >= 1
        assert any(entry["content"]["id"] == item["id"] for entry in client.get("/api/drift").json()["items"])


def png_bytes(color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (32, 32), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_visual_asset_comparison_persists_match_and_mismatch():
    with TestClient(app) as client:
        reference = client.post("/api/assets/upload", headers={"X-Demo-Role": "admin"}, files={"file": ("logo.png", png_bytes((100, 50, 200)), "image/png")})
        assert reference.status_code == 200
        asset_id = reference.json()["id"]
        assert client.post(f"/api/assets/{asset_id}/approve", headers={"X-Demo-Role": "admin"}).status_code == 200
        match = client.post(f"/api/assets/{asset_id}/compare", files={"file": ("same.png", png_bytes((100, 50, 200)), "image/png")})
        mismatch = client.post(f"/api/assets/{asset_id}/compare", files={"file": ("different.png", png_bytes((0, 0, 0)), "image/png")})
        assert match.status_code == 200 and match.json()["verdict"] == "match"
        assert mismatch.status_code == 200 and mismatch.json()["verdict"] == "mismatch"
        assert len(client.get(f"/api/assets/{asset_id}/comparisons").json()["items"]) == 2


def test_background_audit_job_runs_and_persists_result():
    with TestClient(app) as client:
        item = client.post("/api/content", json={"title": "Async audit", "content_type": "Advertisement", "context": "NovaTech X1", "text": "NovaTech X1 has a 7000 mAh battery."}).json()
        queued = client.post(f"/api/content/{item['id']}/audit/jobs")
        assert queued.status_code == 200
        job_id = queued.json()["id"]
        status = queued.json()["status"]
        for _ in range(30):
            status_response = client.get(f"/api/audit/jobs/{job_id}")
            assert status_response.status_code == 200
            status = status_response.json()["status"]
            if status in {"completed", "failed"}:
                break
            time.sleep(0.05)
        assert status == "completed"
        assert status_response.json()["audit_run_id"] is not None
        content = client.get(f"/api/content/{item['id']}").json()
        assert content["current_version"]["audit"]["retrieval_mode"] == "lexical"
        assert content["current_version"]["audit"]["retrieved_context"]


def test_local_storage_rejects_path_traversal(tmp_path):
    storage = LocalStorage(str(tmp_path))
    try:
        storage.put("../outside.txt", b"secret")
    except ValueError:
        pass
    else:
        raise AssertionError("Storage accepted a path traversal key")


def test_health_endpoint_includes_provider_status():
    """Health endpoint returns provider mode and model when configured."""
    with TestClient(app) as client:
        # Test default (rules-only)
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "brandproof-api"
        assert "mode" in data
        assert "llm_provider" in data
        assert "llm_model" in data
        # Default is rules-only
        assert data["llm_provider"] == "rules-only"
        assert data["llm_model"] is None


def test_audit_with_llm_provider_enabled_merges_findings():
    """When LLM provider is configured, audit merges LLM findings with rules findings."""
    mock_gemini_response = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": json.dumps({
                        "findings": [{
                            "issue_key": "tone-promotional",
                            "category": "Tone",
                            "severity": "medium",
                            "claim_text": "Enjoy a 7000 mAh battery",
                            "explanation": "The tone is overly promotional for a factual claim.",
                            "verification_status": "Needs interpretation",
                            "suggested_correction": "The NovaTech X1 includes a 5000 mAh battery.",
                            "confidence": "medium",
                            "evidence_type": "fact",
                            "evidence_id": 1
                        }]
                    })
                }]
            }
        }]
    }

    with patch("app.main.call_gemini") as mock_call_gemini, \
         patch.object(settings, "llm_api_key", "test-key"), \
         patch.object(settings, "llm_provider", "gemini"):
        from app.ai import AIFinding
        mock_call_gemini.return_value = [
            AIFinding(
                issue_key="tone-promotional",
                category="Tone",
                severity="medium",
                claim_text="Enjoy a 7000 mAh battery",
                explanation="The tone is overly promotional for a factual claim.",
                verification_status="Needs interpretation",
                suggested_correction="The NovaTech X1 includes a 5000 mAh battery.",
                confidence="medium",
                evidence_type="fact",
                evidence_id=1
            )
        ]

        with TestClient(app) as client:
            # Create content with seeded demo data
            item = client.post("/api/content", json={
                "title": "LLM Audit Test",
                "content_type": "Advertisement",
                "context": "NovaTech X1",
                "text": "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection."
            }).json()

            # Run audit
            response = client.post(f"/api/content/{item['id']}/audit")
            assert response.status_code == 200

            audit_data = response.json()["audit"]
            # Provider mode should indicate gemini was used (or fallback)
            assert "provider_mode" in audit_data
            # Should have both rules findings (battery-mismatch, waterproof-unsupported)
            # and the mocked LLM finding (tone-promotional)
            finding_keys = {f["issue_key"] for f in audit_data["findings"]}
            assert "battery-mismatch" in finding_keys  # From rules
            assert "waterproof-unsupported" in finding_keys  # From rules
            assert "tone-promotional" in finding_keys  # From mocked LLM
