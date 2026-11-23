# Governance & Security

This pipeline handles financial, legal, and HR documents arriving by email, so security controls are treated as first-class requirements rather than afterthoughts.

## Data Residency & Model Privacy

- **Azure OpenAI inside your tenant:** Unlike public consumer endpoints, Azure OpenAI processes document payloads within your chosen Azure region and does not use customer prompts or completions to train foundation models.
- **Zero real documents in Git:** All files under `samples/emails/` are 100% synthetic (example domains `.example`, placeholder SSN `000-11-2222`, fictitious companies).

## Identity & Secrets Management

- **Managed Identity first:** `power-automate/flows/email-document-router.json` authenticates against Azure OpenAI using `ManagedServiceIdentity` (`https://cognitiveservices.azure.com`) rather than hardcoding static keys inside flow JSON.
- **Key Vault with RBAC:** `infra/main.bicep` provisions Azure Key Vault with RBAC authorization and 90-day soft delete enabled.
- **API authentication:** When `doc-router` is hosted as a container/connector, `X-API-Key` is validated via `secrets.compare_digest` (constant-time comparison).

## Sensitive Document Containment

- **Quarantine before routing:** Sensitive (`confidential`, `restricted`), low-confidence, or high-value documents are never dropped directly into broad-access SharePoint folders. They land in `/DocumentIntakeQuarantine/PendingReview` with restricted permissions until a human approves or rejects them from Teams.
- **Audit trail:** Every human approval, category override, and rejection writes an immutable record to the `DocumentRoutingAudit` SharePoint list with `ReviewerUPN`, `Decision`, `TargetCategory`, and `ReviewerNotes`.
- **SharePoint filename sanitization:** Special characters rejected by SharePoint (`~ " # % & * : < > ? / \ { | }`) are stripped before upload to prevent flow failures.
