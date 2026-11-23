"""Unit tests for SharePoint routing rules, Teams Adaptive Cards, and FastAPI endpoints."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from doc_router.classifier import classify_offline
from doc_router.config import Settings
from doc_router.main import app
from doc_router.models import IncomingEmailDocument
from doc_router.router import route_document

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "emails"


def _load_sample(name: str) -> IncomingEmailDocument:
    return IncomingEmailDocument.model_validate_json(
        (SAMPLES_DIR / name).read_text(encoding="utf-8")
    )


class TestDocumentRouter(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings()
        self.client = TestClient(app)

    def test_standard_invoice_auto_routes_to_finance_library(self) -> None:
        doc = _load_sample("01_standard_invoice.json")
        decision = route_document(doc, classify_offline(doc), self.settings)
        self.assertEqual(decision.action, "auto_route")
        self.assertEqual(decision.sharepoint.folder_path, "/RoutedDocuments/Finance/Invoices")
        self.assertEqual(decision.sharepoint.metadata["ReviewStatus"], "AutoRouted")
        self.assertIsNone(decision.teams_adaptive_card)

    def test_high_value_invoice_escalates_to_finance_teams_channel(self) -> None:
        doc = _load_sample("02_high_value_invoice.json")
        decision = route_document(doc, classify_offline(doc), self.settings)
        self.assertEqual(decision.action, "escalate_teams")
        self.assertEqual(decision.teams_channel, "Finance-Approvals")
        self.assertEqual(decision.sharepoint.folder_path, "/DocumentIntakeQuarantine/PendingReview")
        self.assertTrue(any("high_value_invoice" in r for r in decision.escalation_reasons))
        self.assertIsNotNone(decision.teams_adaptive_card)
        assert decision.teams_adaptive_card is not None
        self.assertEqual(decision.teams_adaptive_card["type"], "AdaptiveCard")

    def test_legal_nda_escalates_to_legal_review_with_hydrated_card(self) -> None:
        doc = _load_sample("03_legal_nda_confidential.json")
        decision = route_document(doc, classify_offline(doc), self.settings)
        self.assertEqual(decision.action, "escalate_teams")
        self.assertEqual(decision.teams_channel, "Legal-Review")
        card_str = str(decision.teams_adaptive_card)
        self.assertIn("Meridian_Mutual_NDA_v2_Redline.pdf", card_str)
        self.assertNotIn("${file_name}", card_str)

    def test_low_confidence_scan_escalates_to_ops(self) -> None:
        doc = _load_sample("05_low_confidence_scan.json")
        decision = route_document(doc, classify_offline(doc), self.settings)
        self.assertEqual(decision.action, "escalate_teams")
        self.assertEqual(decision.teams_channel, "Document-Triage-Ops")
        self.assertTrue(any("low_confidence" in r for r in decision.escalation_reasons))

    def test_api_endpoint_auth_and_routing(self) -> None:
        raw_doc = (SAMPLES_DIR / "01_standard_invoice.json").read_text(encoding="utf-8")
        with patch.dict(os.environ, {"API_KEY": "connector-secret", "AZURE_OPENAI_API_KEY": ""}):
            unauth = self.client.post(
                "/api/v1/classify-and-route",
                content=raw_doc,
                headers={"Content-Type": "application/json"},
            )
            ok = self.client.post(
                "/api/v1/classify-and-route",
                content=raw_doc,
                headers={"Content-Type": "application/json", "X-API-Key": "connector-secret"},
            )
        self.assertEqual(unauth.status_code, 401)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["action"], "auto_route")

    def test_health_endpoint(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok", "service": "doc-router"})


if __name__ == "__main__":
    unittest.main()
