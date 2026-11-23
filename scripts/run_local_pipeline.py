#!/usr/bin/env python3
"""Run all synthetic email attachments through the classification and routing pipeline locally."""

import argparse
import json
import sys
from pathlib import Path

from doc_router.classifier import classify_document
from doc_router.config import Settings
from doc_router.models import IncomingEmailDocument
from doc_router.router import route_document


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate the email document triage pipeline on sample JSON attachments."
    )
    parser.add_argument(
        "--samples-dir",
        default="samples/emails",
        help="Directory containing sample IncomingEmailDocument JSON files.",
    )
    parser.add_argument(
        "--dump-cards",
        action="store_true",
        help="Print rendered Teams Adaptive Card JSON for escalated documents.",
    )
    args = parser.parse_args()

    samples_dir = Path(args.samples_dir)
    files = sorted(samples_dir.glob("*.json"))
    if not files:
        print(f"No sample JSON files found in {samples_dir}", file=sys.stderr)
        return 1

    settings = Settings.from_env()
    mode = "Azure OpenAI" if settings.azure_openai_api_key else "Offline Heuristic Simulator"
    print(f"Running Intelligent Document Pipeline ({mode}) on {len(files)} sample documents...\n")

    auto_count = 0
    escalated_count = 0

    for path in files:
        doc = IncomingEmailDocument.model_validate_json(path.read_text(encoding="utf-8"))
        classification = classify_document(doc, settings)
        decision = route_document(doc, classification, settings)

        if decision.action == "auto_route":
            auto_count += 1
            dest = f"{decision.sharepoint.folder_path}/{decision.sharepoint.file_name}"
            print(f"[AUTO-ROUTE]  {doc.file_name}")
            print(
                f"              category={classification.category} "
                f"confidence={classification.confidence:.2f} "
                f"sensitivity={classification.sensitivity}"
            )
            label = decision.sharepoint.retention_label
            print(f"              -> SharePoint: {dest} (label: {label})")
        else:
            escalated_count += 1
            dest = f"{decision.sharepoint.folder_path}/{decision.sharepoint.file_name}"
            print(f"[ESCALATED]   {doc.file_name}")
            print(
                f"              category={classification.category} "
                f"confidence={classification.confidence:.2f} "
                f"sensitivity={classification.sensitivity}"
            )
            print(f"              -> Quarantine: {dest}")
            print(f"              -> Teams Channel: #{decision.teams_channel}")
            print(f"              -> Reasons: {', '.join(decision.escalation_reasons)}")
            if args.dump_cards and decision.teams_adaptive_card:
                print(json.dumps(decision.teams_adaptive_card, indent=2))
        print()

    print(f"Summary: {auto_count} auto-routed to SharePoint, {escalated_count} escalated to Teams.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
