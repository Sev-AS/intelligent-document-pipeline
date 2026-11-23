"""FastAPI service usable as a Power Automate Custom Connector or local test server."""

import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, status

from doc_router.classifier import classify_document
from doc_router.config import Settings
from doc_router.models import IncomingEmailDocument, RoutingDecision
from doc_router.router import route_document

settings = Settings.from_env()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Intelligent Document Pipeline Router",
    description=(
        "Classification, compliance guardrails, SharePoint routing, and Microsoft Teams "
        "Adaptive Card generation for automated email document intake."
    ),
    version="1.0.0",
)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    current = Settings.from_env()
    if not current.api_key:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, current.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
        )


@app.get("/health", tags=["Monitoring"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "doc-router"}


@app.post(
    "/api/v1/classify-and-route",
    response_model=RoutingDecision,
    tags=["Document Pipeline"],
    dependencies=[Depends(verify_api_key)],
)
def classify_and_route(document: IncomingEmailDocument) -> RoutingDecision:
    """Classify an AI Builder extracted email attachment and return its SharePoint/Teams action."""
    current = Settings.from_env()
    classification = classify_document(document, current)
    return route_document(document, classification, current)
