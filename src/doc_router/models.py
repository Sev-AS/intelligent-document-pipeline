"""Pydantic v2 contracts for incoming email attachments, classifications, and routing decisions."""

from typing import Literal

from pydantic import BaseModel, Field

DocumentCategory = Literal[
    "invoice",
    "legal_contract",
    "hr_document",
    "vendor_compliance",
    "operations",
    "general",
]
SensitivityLevel = Literal["normal", "confidential", "restricted"]


class AIBuilderExtraction(BaseModel):
    """Structured fields and OCR text produced by Azure AI Builder Document Processing."""

    ocr_text: str = Field(default="", description="Full OCR text extracted from the attachment.")
    page_count: int = Field(default=1, ge=0)
    ocr_confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    vendor_name: str | None = None
    invoice_total: float | None = None
    currency: str | None = None
    document_date: str | None = None


class IncomingEmailDocument(BaseModel):
    """Normalized email attachment event received from Power Automate (Office 365 Outlook)."""

    document_id: str = Field(min_length=2, max_length=120)
    source_message_id: str = Field(min_length=2, max_length=200)
    sender: str = Field(min_length=3, max_length=200)
    subject: str = Field(default="", max_length=300)
    body_excerpt: str = Field(default="", max_length=2000)
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(default="application/pdf")
    extraction: AIBuilderExtraction


class ClassificationResult(BaseModel):
    """Classification output produced by Azure OpenAI + deterministic guardrail layer."""

    category: DocumentCategory
    confidence: float = Field(ge=0.0, le=1.0)
    sensitivity: SensitivityLevel
    summary: str
    sensitivity_flags: list[str] = Field(default_factory=list)
    extracted_vendor: str | None = None
    extracted_amount: float | None = None
    currency: str | None = None
    reasoning: str = ""
    classifier_mode: Literal["azure_openai", "offline_heuristic"] = "azure_openai"


class SharePointDestination(BaseModel):
    """Target SharePoint folder, retention label, and list item metadata columns."""

    folder_path: str
    file_name: str
    retention_label: str
    metadata: dict[str, object]


class RoutingDecision(BaseModel):
    """Final action returned to Power Automate: auto-route or quarantine + Teams escalation."""

    document_id: str
    action: Literal["auto_route", "escalate_teams"]
    classification: ClassificationResult
    sharepoint: SharePointDestination
    escalation_reasons: list[str] = Field(default_factory=list)
    teams_channel: str | None = None
    teams_adaptive_card: dict[str, object] | None = None
