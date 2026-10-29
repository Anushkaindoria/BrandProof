"""Unit tests for the Gemini AI adapter (ai.py)."""

import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

import pytest

from app.ai import AIProviderError, call_gemini, AIFinding
from app.models import ApprovedFact, Policy
from app.config import settings


class TestCallGemini:
    """Tests for the call_gemini function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.facts = [
            ApprovedFact(id=1, key="battery_capacity", product="NovaTech X1", value="5000 mAh", source_reference="brief p. 2", excerpt="Battery capacity: 5000 mAh."),
            ApprovedFact(id=2, key="water_resistance", product="NovaTech X1", value="Not officially certified", source_reference="brief p. 2", excerpt="Water resistance: Not officially certified."),
        ]
        self.policies = [
            Policy(id=3, name="No unsupported waterproof claims", rule_type="prohibited_claim", rule_value="waterproof", description="Do not describe as waterproof.", source_reference="policy p. 4"),
        ]
        self.text = "Meet the NovaTech X1! Enjoy a 7000 mAh battery and completely waterproof protection."

    def test_missing_api_key_returns_empty_list(self):
        """When LLM_API_KEY is not set, call_gemini returns empty list."""
        with patch.object(settings, "llm_api_key", None):
            with patch.object(settings, "llm_provider", "gemini"):
                result = call_gemini(self.text, self.facts, self.policies)
                assert result == []

    def test_empty_api_key_returns_empty_list(self):
        """When LLM_API_KEY is empty string, call_gemini returns empty list."""
        with patch.object(settings, "llm_api_key", ""):
            with patch.object(settings, "llm_provider", "gemini"):
                result = call_gemini(self.text, self.facts, self.policies)
                assert result == []

    def test_valid_response_returns_parsed_findings(self):
        """Valid Gemini response returns list of AIFinding objects."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "findings": [{
                                "issue_key": "tone-mismatch",
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

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch.object(settings, "llm_model", "gemini-2.0-flash"):
                    with patch("urllib.request.urlopen") as mock_urlopen:
                        mock_response_obj = MagicMock()
                        mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                        mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                        mock_response_obj.__exit__ = MagicMock(return_value=None)
                        mock_urlopen.return_value = mock_response_obj

                        result = call_gemini(self.text, self.facts, self.policies)

                        assert len(result) == 1
                        assert isinstance(result[0], AIFinding)
                        assert result[0].issue_key == "tone-mismatch"
                        assert result[0].category == "Tone"
                        assert result[0].evidence_id == 1
                        assert result[0].evidence_type == "fact"

    def test_timeout_raises_ai_provider_error(self):
        """Timeout during request raises AIProviderError."""
        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen", side_effect=TimeoutError("Request timed out")):
                    with pytest.raises(AIProviderError) as exc_info:
                        call_gemini(self.text, self.facts, self.policies)
                    assert "timed out" in str(exc_info.value).lower()

    def test_http_error_raises_ai_provider_error(self):
        """HTTP error during request raises AIProviderError."""
        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen", side_effect=HTTPError("url", 500, "Internal Server Error", {}, None)):
                    with pytest.raises(AIProviderError) as exc_info:
                        call_gemini(self.text, self.facts, self.policies)
                    assert "500" in str(exc_info.value)

    def test_url_error_raises_ai_provider_error(self):
        """URL error (network issue) raises AIProviderError."""
        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
                    with pytest.raises(AIProviderError) as exc_info:
                        call_gemini(self.text, self.facts, self.policies)
                    assert "connection refused" in str(exc_info.value).lower()

    def test_malformed_json_response_raises_ai_provider_error(self):
        """Malformed JSON in response raises AIProviderError."""
        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = b"not valid json"
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    with pytest.raises(AIProviderError) as exc_info:
                        call_gemini(self.text, self.facts, self.policies)
                    assert "provider request failed" in str(exc_info.value).lower()

    def test_missing_candidates_key_raises_ai_provider_error(self):
        """Response missing candidates key raises AIProviderError."""
        mock_response = {"invalid": "structure"}

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    with pytest.raises(AIProviderError) as exc_info:
                        call_gemini(self.text, self.facts, self.policies)
                    assert "invalid structured output" in str(exc_info.value).lower()

    def test_invalid_evidence_id_is_sanitized(self):
        """Evidence ID not in allowed set is stripped and verification status downgraded."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "findings": [{
                                "issue_key": "tone-mismatch",
                                "category": "Tone",
                                "severity": "medium",
                                "claim_text": "Some claim",
                                "explanation": "Explanation",
                                "verification_status": "Supported",
                                "suggested_correction": "Correction",
                                "confidence": "high",
                                "evidence_type": "fact",
                                "evidence_id": 999  # Not in our facts/policies
                            }]
                        })
                    }]
                }
            }]
        }

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    result = call_gemini(self.text, self.facts, self.policies)

                    assert len(result) == 1
                    assert result[0].evidence_id is None
                    assert result[0].evidence_type is None
                    assert result[0].verification_status == "Insufficient evidence"
                    assert result[0].confidence == "low"

    def test_invalid_evidence_type_is_sanitized(self):
        """Evidence type not in allowed set is stripped."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "findings": [{
                                "issue_key": "tone-mismatch",
                                "category": "Tone",
                                "severity": "medium",
                                "claim_text": "Some claim",
                                "explanation": "Explanation",
                                "verification_status": "Supported",
                                "suggested_correction": "Correction",
                                "confidence": "high",
                                "evidence_type": "invalid_type",
                                "evidence_id": 1
                            }]
                        })
                    }]
                }
            }]
        }

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    result = call_gemini(self.text, self.facts, self.policies)

                    assert len(result) == 1
                    assert result[0].evidence_id is None
                    assert result[0].evidence_type is None

    def test_markdown_code_block_in_response_is_handled(self):
        """Response wrapped in markdown code blocks is parsed correctly."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "```json\n" + json.dumps({
                            "findings": [{
                                "issue_key": "tone-mismatch",
                                "category": "Tone",
                                "severity": "medium",
                                "claim_text": "Some claim",
                                "explanation": "Explanation",
                                "verification_status": "Needs interpretation",
                                "suggested_correction": "Correction",
                                "confidence": "medium",
                                "evidence_type": None,
                                "evidence_id": None
                            }]
                        }) + "\n```"
                    }]
                }
            }]
        }

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    result = call_gemini(self.text, self.facts, self.policies)

                    assert len(result) == 1
                    assert result[0].issue_key == "tone-mismatch"

    def test_multiple_findings_returned(self):
        """Multiple findings in response are all returned."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "findings": [
                                {"issue_key": "finding-1", "category": "Tone", "severity": "low", "claim_text": "Claim 1", "explanation": "Exp 1", "verification_status": "Supported", "suggested_correction": "", "confidence": "high", "evidence_type": None, "evidence_id": None},
                                {"issue_key": "finding-2", "category": "Accessibility", "severity": "medium", "claim_text": "Claim 2", "explanation": "Exp 2", "verification_status": "Insufficient evidence", "suggested_correction": "Fix", "confidence": "medium", "evidence_type": None, "evidence_id": None}
                            ]
                        })
                    }]
                }
            }]
        }

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    result = call_gemini(self.text, self.facts, self.policies)

                    assert len(result) == 2
                    assert result[0].issue_key == "finding-1"
                    assert result[1].issue_key == "finding-2"

    def test_findings_key_as_object_wrapper(self):
        """Response with findings wrapped in object is handled."""
        mock_response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "findings": [{
                                "issue_key": "wrapped-finding",
                                "category": "Tone",
                                "severity": "low",
                                "claim_text": "Claim",
                                "explanation": "Exp",
                                "verification_status": "Supported",
                                "suggested_correction": "",
                                "confidence": "high",
                                "evidence_type": None,
                                "evidence_id": None
                            }]
                        })
                    }]
                }
            }]
        }

        with patch.object(settings, "llm_api_key", "test-key-123"):
            with patch.object(settings, "llm_provider", "gemini"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    mock_response_obj = MagicMock()
                    mock_response_obj.read.return_value = json.dumps(mock_response).encode()
                    mock_response_obj.__enter__ = MagicMock(return_value=mock_response_obj)
                    mock_response_obj.__exit__ = MagicMock(return_value=None)
                    mock_urlopen.return_value = mock_response_obj

                    result = call_gemini(self.text, self.facts, self.policies)

                    assert len(result) == 1
                    assert result[0].issue_key == "wrapped-finding"