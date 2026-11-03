"""Tamper-evident content passports.

A passport is the JSON record created when a reviewer approves a content version. It is
signed with HMAC-SHA256 using PASSPORT_SECRET, and ``verify_passport`` re-checks it on demand:

1. signature   - the passport JSON has not been edited since approval
2. content_hash - the stored text still hashes to the approved SHA-256
3. evidence_current - none of the facts/policies it depended on has changed since
4. approval_state - the content is still in the approved state

This is a process record, not a legal guarantee: anyone holding the secret can sign.
"""

import hashlib
import hmac
import json
from typing import Any

ALGORITHM = "HMAC-SHA256"
_EXCLUDED = {"signature", "signature_algorithm"}


def canonical(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key not in _EXCLUDED}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(payload: dict[str, Any], secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(payload: dict[str, Any], secret: str) -> tuple[bool, str]:
    signature = payload.get("signature")
    if not signature:
        return False, "This passport is unsigned (it was created before signing was added)."
    if hmac.compare_digest(str(signature), sign(payload, secret)):
        return True, "Signature matches the passport contents."
    return False, "Signature does not match: the passport contents were changed after approval."


def verify_passport(
    payload: dict[str, Any],
    *,
    secret: str,
    version_text_hash: str,
    record_hash: str,
    changed_dependencies: list[str],
    item_status: str,
) -> dict[str, Any]:
    signature_ok, signature_detail = verify_signature(payload, secret)
    hash_ok = payload.get("content_hash") == version_text_hash == record_hash
    evidence_ok = not changed_dependencies
    state_ok = item_status == "approved"
    checks = [
        {"name": "signature", "ok": signature_ok, "detail": signature_detail},
        {"name": "content_hash", "ok": hash_ok, "detail": "The stored text still hashes to the approved SHA-256." if hash_ok else "The stored text no longer matches the approved SHA-256 hash."},
        {"name": "evidence_current", "ok": evidence_ok, "detail": "Every fact and policy this approval relied on is unchanged." if evidence_ok else "Evidence changed since approval: " + ", ".join(changed_dependencies) + "."},
        {"name": "approval_state", "ok": state_ok, "detail": "The content is currently approved." if state_ok else f"The content is currently '{item_status}', not approved."},
    ]
    return {"valid": all(check["ok"] for check in checks), "checks": checks}
