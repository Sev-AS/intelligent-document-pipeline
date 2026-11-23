"""Unit tests for document classification, Azure OpenAI Structured Outputs, and PII guardrails."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from doc_router.classifier import classify_document, classify_offline, scan_deterministic_signals
from doc_router.config import Settings
from doc_router.models import IncomingEmailDocument

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "emails"


def _load_sample(name: str) -> IncomingEmailDocument:
    return IncomingEmailDocument.model_validate_json(
        (SAMPLES_DIR / name).read_text(encoding="utf-8")
    )


class TestDocumentClassifier(unittest.TestCase):
    def test_standard_invoice_offline_classification(self) -> None:
        doc = _load_sample("01_standard_invoice.json")
        res = classify_offline(doc)
        self.assertEqual(res.category, "invoice")
        self.assertEqual(res.sensitivity, "normal")
        self.assertGreaterEqual(res.confidence, 0.9)
        self.assertEqual(res.extracted_amount, 1458.0)

    def test_hr_onboarding_triggers_pii_restricted_floor(self) -> None:
        doc = _load_sample("04_hr_onboarding_pii.json")
        sensitivity, flags = scan_deterministic_signals(doc)
        self.assertEqual(sensitivity, "restricted")
        self.assertIn("pii:ssn_pattern", flags)
        self.assertIn("pii:bank_routing", flags)

    def test_low_ocr_confidence_caps_final_confidence(self) -> None:
        doc = _load_sample("05_low_confidence_scan.json")
        res = classify_offline(doc)
        self.assertLess(res.confidence, 0.70)
        self.assertIn("quality:low_ocr_readability", res.sensitivity_flags)

    @patch("doc_router.classifier.httpx.post")
    def test_azure_openai_guardrail_cannot_downgrade_restricted_pii(
        self, mock_post: MagicMock
    ) -> None:
        # Even if the model mistakenly labels an SSN document as "normal",
        # the deterministic guardrail layer must keep sensitivity at "restricted".
        doc = _load_sample("04_hr_onboarding_pii.json")
        llm_payload = {
            "category": "hr_document",
            "confidence": 0.96,
            "sensitivity": "normal",
            "summary": "Onboarding form.",
            "sensitivity_flags": [],
            "extracted_vendor": None,
            "extracted_amount": None,
            "currency": None,
            "reasoning": "HR form.",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(llm_payload)}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        settings = Settings(
            azure_openai_endpoint="https://demo.openai.azure.com",
            azure_openai_api_key="test-key",
        )
        res = classify_document(doc, settings)
        self.assertEqual(res.classifier_mode, "azure_openai")
        self.assertEqual(res.sensitivity, "restricted")
        self.assertIn("pii:ssn_pattern", res.sensitivity_flags)

    @patch("doc_router.classifier.httpx.post", side_effect=httpx.ConnectTimeout("timeout"))
    def test_azure_openai_failure_degrades_safely_for_escalation(
        self, _mock_post: MagicMock
    ) -> None:
        doc = _load_sample("01_standard_invoice.json")
        settings = Settings(
            azure_openai_endpoint="https://demo.openai.azure.com",
            azure_openai_api_key="test-key",
        )
        res = classify_document(doc, settings)
        self.assertLessEqual(res.confidence, 0.50)
        self.assertIn("error:azure_openai_failed", res.sensitivity_flags)


if __name__ == "__main__":
    unittest.main()
