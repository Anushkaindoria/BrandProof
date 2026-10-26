import os

os.environ["DATABASE_URL"] = "sqlite:///./test_brandproof.db"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.seed import seed_database


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
