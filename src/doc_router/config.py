"""Environment-backed configuration for the document classification and routing engine."""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_openai_timeout_seconds: float = 30.0

    confidence_threshold: float = 0.85
    high_value_invoice_threshold: float = 10000.0

    routing_rules_path: Path = REPO_ROOT / "sharepoint" / "routing-rules.json"
    system_prompt_path: Path = (
        REPO_ROOT / "power-automate" / "prompts" / "classification-system.txt"
    )
    classification_schema_path: Path = (
        REPO_ROOT / "power-automate" / "prompts" / "classification-schema.json"
    )
    escalation_card_path: Path = (
        REPO_ROOT / "power-automate" / "adaptive-cards" / "escalation-review-card.json"
    )

    api_key: str = ""
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/"),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", "").strip(),
            azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
            azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
            azure_openai_timeout_seconds=float(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "30")),
            confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.85")),
            high_value_invoice_threshold=float(os.getenv("HIGH_VALUE_INVOICE_THRESHOLD", "10000")),
            routing_rules_path=Path(
                os.getenv(
                    "ROUTING_RULES_PATH",
                    str(REPO_ROOT / "sharepoint" / "routing-rules.json"),
                )
            ),
            system_prompt_path=Path(
                os.getenv(
                    "SYSTEM_PROMPT_PATH",
                    str(REPO_ROOT / "power-automate" / "prompts" / "classification-system.txt"),
                )
            ),
            classification_schema_path=Path(
                os.getenv(
                    "CLASSIFICATION_SCHEMA_PATH",
                    str(REPO_ROOT / "power-automate" / "prompts" / "classification-schema.json"),
                )
            ),
            escalation_card_path=Path(
                os.getenv(
                    "ESCALATION_CARD_PATH",
                    str(
                        REPO_ROOT
                        / "power-automate"
                        / "adaptive-cards"
                        / "escalation-review-card.json"
                    ),
                )
            ),
            api_key=os.getenv("API_KEY", "").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
