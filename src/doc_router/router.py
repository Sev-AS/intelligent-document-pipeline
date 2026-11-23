"""SharePoint routing policy evaluator and Microsoft Teams Adaptive Card renderer."""

import json
import re
from pathlib import Path

from doc_router.config import Settings
from doc_router.models import (
    ClassificationResult,
    IncomingEmailDocument,
    RoutingDecision,
    SharePointDestination,
)


def _sanitize_filename(name: str) -> str:
    """Remove characters disallowed in SharePoint file names."""
    cleaned = re.sub(r'[~"#%&*:<>?/\\{|}]+', "_", name).strip()
    return cleaned or "document.pdf"


def _render_card_template(template_obj: object, replacements: dict[str, str]) -> object:
    """Recursively substitute `${key}` placeholders inside an Adaptive Card JSON object."""
    if isinstance(template_obj, str):
        rendered = template_obj
        for key, value in replacements.items():
            rendered = rendered.replace(f"${{{key}}}", value)
        return rendered
    if isinstance(template_obj, list):
        return [_render_card_template(item, replacements) for item in template_obj]
    if isinstance(template_obj, dict):
        return {k: _render_card_template(v, replacements) for k, v in template_obj.items()}
    return template_obj


def load_routing_rules(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def route_document(
    doc: IncomingEmailDocument,
    classification: ClassificationResult,
    settings: Settings,
) -> RoutingDecision:
    """Evaluate routing rules, sensitivity floors, and thresholds to route or escalate."""
    rules = load_routing_rules(settings.routing_rules_path)
    categories: dict[str, dict[str, object]] = rules["categories"]  # type: ignore[assignment]
    category_rule = categories.get(classification.category, categories["general"])

    escalation_reasons: list[str] = []

    if classification.confidence < settings.confidence_threshold:
        escalation_reasons.append(
            f"low_confidence:{classification.confidence:.2f}<{settings.confidence_threshold:.2f}"
        )

    if classification.sensitivity in ("confidential", "restricted"):
        escalation_reasons.append(f"sensitivity:{classification.sensitivity}")

    if bool(category_rule.get("always_escalate", False)):
        escalation_reasons.append(f"category_policy:{classification.category}")

    if (
        classification.category == "invoice"
        and classification.extracted_amount is not None
        and classification.extracted_amount >= settings.high_value_invoice_threshold
    ):
        threshold = settings.high_value_invoice_threshold
        amount = classification.extracted_amount
        escalation_reasons.append(f"high_value_invoice:{amount:,.2f}>={threshold:,.2f}")

    for flag in classification.sensitivity_flags:
        if flag not in escalation_reasons:
            escalation_reasons.append(flag)

    safe_file_name = _sanitize_filename(doc.file_name)
    needs_escalation = len(escalation_reasons) > 0

    metadata: dict[str, object] = {
        "DocCategory": classification.category,
        "ConfidenceScore": classification.confidence,
        "SensitivityLevel": classification.sensitivity,
        "ReviewStatus": "PendingHumanReview" if needs_escalation else "AutoRouted",
        "SourceMessageId": doc.source_message_id,
        "ExtractedVendor": classification.extracted_vendor,
        "ExtractedAmount": classification.extracted_amount,
    }

    if needs_escalation:
        quarantine_folder = str(rules["quarantine_library"])
        teams_channel = str(
            category_rule.get("escalation_channel") or rules["default_escalation_channel"]
        )
        card_template = json.loads(settings.escalation_card_path.read_text(encoding="utf-8"))
        quarantine_path = f"{quarantine_folder}/{safe_file_name}"
        card = _render_card_template(
            card_template,
            {
                "document_id": doc.document_id,
                "file_name": safe_file_name,
                "sender": doc.sender,
                "subject": doc.subject,
                "category": classification.category,
                "confidence_pct": f"{classification.confidence * 100:.0f}%",
                "sensitivity": classification.sensitivity.upper(),
                "escalation_reasons": ", ".join(escalation_reasons),
                "quarantine_path": quarantine_path,
                "summary": classification.summary,
            },
        )
        return RoutingDecision(
            document_id=doc.document_id,
            action="escalate_teams",
            classification=classification,
            sharepoint=SharePointDestination(
                folder_path=quarantine_folder,
                file_name=safe_file_name,
                retention_label=str(category_rule["retention_label"]),
                metadata=metadata,
            ),
            escalation_reasons=escalation_reasons,
            teams_channel=teams_channel,
            teams_adaptive_card=card,  # type: ignore[arg-type]
        )

    return RoutingDecision(
        document_id=doc.document_id,
        action="auto_route",
        classification=classification,
        sharepoint=SharePointDestination(
            folder_path=str(category_rule["sharepoint_library"]),
            file_name=safe_file_name,
            retention_label=str(category_rule["retention_label"]),
            metadata=metadata,
        ),
        escalation_reasons=[],
        teams_channel=None,
        teams_adaptive_card=None,
    )
