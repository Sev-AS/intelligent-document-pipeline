"""Document classification via Azure OpenAI Structured Outputs plus deterministic guardrails."""

import json
import logging
import re

import httpx

from doc_router.config import Settings
from doc_router.models import (
    ClassificationResult,
    DocumentCategory,
    IncomingEmailDocument,
    SensitivityLevel,
)

logger = logging.getLogger("doc_router.classifier")

SENSITIVITY_ORDER: dict[SensitivityLevel, int] = {
    "normal": 0,
    "confidential": 1,
    "restricted": 2,
}

PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pii:ssn_pattern", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "pii:bank_routing",
        re.compile(r"\b(iban|routing number|account number|direct deposit)\b", re.I),
    ),
    (
        "pii:passport_or_id",
        re.compile(r"\b(passport no|national id|social security)\b", re.I),
    ),
)

CONFIDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "policy:nda_or_legal",
        re.compile(r"\b(non-disclosure|nda|indemnification|litigation|subpoena)\b", re.I),
    ),
    (
        "policy:confidential_marking",
        re.compile(r"\b(strictly confidential|attorney-client|privileged)\b", re.I),
    ),
    (
        "policy:hr_sensitive",
        re.compile(r"\b(payroll|salary|termination|disciplinary|medical leave)\b", re.I),
    ),
)


def _max_sensitivity(a: SensitivityLevel, b: SensitivityLevel) -> SensitivityLevel:
    return a if SENSITIVITY_ORDER[a] >= SENSITIVITY_ORDER[b] else b


def scan_deterministic_signals(
    doc: IncomingEmailDocument,
) -> tuple[SensitivityLevel, list[str]]:
    """Run regex-based compliance & PII checks independently of the LLM."""
    combined = "\n".join(
        [doc.subject, doc.body_excerpt, doc.file_name, doc.extraction.ocr_text]
    )
    flags: list[str] = []
    floor_sensitivity: SensitivityLevel = "normal"

    for label, pattern in PII_PATTERNS:
        if pattern.search(combined):
            flags.append(label)
            floor_sensitivity = _max_sensitivity(floor_sensitivity, "restricted")

    for label, pattern in CONFIDENTIAL_PATTERNS:
        if pattern.search(combined):
            flags.append(label)
            floor_sensitivity = _max_sensitivity(floor_sensitivity, "confidential")

    if len(doc.extraction.ocr_text.strip()) < 25 or doc.extraction.ocr_confidence < 0.70:
        flags.append("quality:low_ocr_readability")

    return floor_sensitivity, flags


def _apply_guardrails(
    result: ClassificationResult,
    doc: IncomingEmailDocument,
) -> ClassificationResult:
    """Enforce deterministic sensitivity floors and preserve AI Builder numeric extractions."""
    floor_sensitivity, guardrail_flags = scan_deterministic_signals(doc)
    merged_flags = list(dict.fromkeys([*result.sensitivity_flags, *guardrail_flags]))
    final_sensitivity = _max_sensitivity(result.sensitivity, floor_sensitivity)

    confidence = result.confidence
    if "quality:low_ocr_readability" in guardrail_flags:
        confidence = min(confidence, 0.65)

    return result.model_copy(
        update={
            "confidence": round(confidence, 3),
            "sensitivity": final_sensitivity,
            "sensitivity_flags": merged_flags,
            "extracted_vendor": result.extracted_vendor or doc.extraction.vendor_name,
            "extracted_amount": (
                result.extracted_amount
                if result.extracted_amount is not None
                else doc.extraction.invoice_total
            ),
            "currency": result.currency or doc.extraction.currency,
        }
    )


def classify_offline(doc: IncomingEmailDocument) -> ClassificationResult:
    """Deterministic local classifier used for zero-cost testing when Azure OpenAI is unset."""
    text = f"{doc.subject} {doc.body_excerpt} {doc.file_name} {doc.extraction.ocr_text}".lower()

    category: DocumentCategory = "general"
    confidence = 0.72
    sensitivity: SensitivityLevel = "normal"
    reasoning = "Classified using offline keyword heuristics."

    legal_terms = (
        "nda",
        "non-disclosure",
        "master services agreement",
        "contract",
        "indemnification",
    )
    hr_terms = ("w-4", "onboarding", "payroll", "direct deposit", "offer letter", "resume")
    compliance_terms = (
        "certificate of insurance",
        "coi",
        "w-9",
        "iso 9001",
        "tax certificate",
    )
    ops_terms = ("bill of lading", "packing slip", "delivery receipt", "purchase order")

    if any(k in text for k in legal_terms):
        category = "legal_contract"
        confidence = 0.94
        sensitivity = "confidential"
        reasoning = "Contains legal agreement and confidentiality clause terminology."
    elif any(k in text for k in hr_terms):
        category = "hr_document"
        confidence = 0.93
        sensitivity = "restricted"
        reasoning = "Contains HR onboarding or employee personal record indicators."
    elif any(k in text for k in compliance_terms):
        category = "vendor_compliance"
        confidence = 0.92
        sensitivity = "normal"
        reasoning = "Matches vendor compliance or insurance certificate fields."
    elif any(k in text for k in ("invoice", "amount due", "net 30", "bill to")) or (
        doc.extraction.invoice_total is not None
    ):
        category = "invoice"
        confidence = 0.95
        sensitivity = "normal"
        reasoning = "Contains standard vendor invoice terms and billing totals."
    elif any(k in text for k in ops_terms):
        category = "operations"
        confidence = 0.91
        sensitivity = "normal"
        reasoning = "Matches operational logistics and delivery documentation."

    if len(doc.extraction.ocr_text.strip()) < 25 or doc.extraction.ocr_confidence < 0.70:
        confidence = min(confidence, 0.58)
        reasoning = "OCR output is too short or noisy for reliable automatic routing."

    vendor_label = doc.extraction.vendor_name or doc.sender
    amount_note = (
        f" for {doc.extraction.currency or 'USD'} {doc.extraction.invoice_total:,.2f}"
        if doc.extraction.invoice_total is not None
        else ""
    )
    cat_title = category.replace("_", " ").title()
    summary = f"{cat_title} from {vendor_label} ({doc.file_name}){amount_note}."

    raw = ClassificationResult(
        category=category,
        confidence=confidence,
        sensitivity=sensitivity,
        summary=summary[:280],
        sensitivity_flags=[],
        extracted_vendor=doc.extraction.vendor_name,
        extracted_amount=doc.extraction.invoice_total,
        currency=doc.extraction.currency,
        reasoning=reasoning,
        classifier_mode="offline_heuristic",
    )
    return _apply_guardrails(raw, doc)


def classify_with_azure_openai(
    doc: IncomingEmailDocument,
    settings: Settings,
) -> ClassificationResult:
    """Call Azure OpenAI Chat Completions with Structured Outputs (`json_schema`)."""
    system_prompt = settings.system_prompt_path.read_text(encoding="utf-8")
    schema = json.loads(settings.classification_schema_path.read_text(encoding="utf-8"))

    user_content = (
        f"Sender: {doc.sender}\n"
        f"Subject: {doc.subject}\n"
        f"File Name: {doc.file_name}\n"
        f"Email Excerpt: {doc.body_excerpt}\n"
        f"AI Builder OCR Confidence: {doc.extraction.ocr_confidence}\n"
        f"AI Builder Vendor: {doc.extraction.vendor_name}\n"
        f"AI Builder Amount: {doc.extraction.invoice_total} {doc.extraction.currency or ''}\n"
        f"OCR Text:\n{doc.extraction.ocr_text[:6000]}"
    )

    url = (
        f"{settings.azure_openai_endpoint}/openai/deployments/"
        f"{settings.azure_openai_deployment}/chat/completions"
        f"?api-version={settings.azure_openai_api_version}"
    )
    payload = {
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "document_classification",
                "strict": True,
                "schema": schema,
            },
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }

    response = httpx.post(
        url,
        headers={
            "api-key": settings.azure_openai_api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=settings.azure_openai_timeout_seconds,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = ClassificationResult.model_validate(
        {**json.loads(content), "classifier_mode": "azure_openai"}
    )
    return _apply_guardrails(parsed, doc)


def classify_document(
    doc: IncomingEmailDocument,
    settings: Settings,
) -> ClassificationResult:
    """Classify via Azure OpenAI when configured, or fall back to offline heuristics."""
    if settings.azure_openai_endpoint and settings.azure_openai_api_key:
        try:
            return classify_with_azure_openai(doc, settings)
        except Exception as exc:
            logger.exception("Azure OpenAI classification failed; escalating safely: %s", exc)
            fallback = classify_offline(doc)
            return fallback.model_copy(
                update={
                    "confidence": min(fallback.confidence, 0.50),
                    "sensitivity_flags": list(
                        dict.fromkeys([*fallback.sensitivity_flags, "error:azure_openai_failed"])
                    ),
                    "reasoning": (
                        f"Azure OpenAI call failed ({type(exc).__name__}); queued for review."
                    ),
                }
            )
    return classify_offline(doc)
