# Deployment Guide (Azure + Microsoft 365)

Follow these steps to deploy the pipeline into your own Azure subscription and Microsoft 365 tenant.

---

## 1. Provision Azure Infrastructure (Bicep)

Copy `infra/parameters.example.json` to `infra/parameters.json` (git-ignored), adjust region/prefix, and deploy:

```bash
az group create --name rg-doc-pipeline-dev --location eastus2

az deployment group create \
  --resource-group rg-doc-pipeline-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters.json
```

Note the outputs: `openAiEndpoint`, `openAiDeploymentName`, and `keyVaultUri`.

---

## 2. Provision SharePoint Libraries & Columns

Apply `sharepoint/site-schema.json` to your target SharePoint site using PnP PowerShell or Microsoft 365 CLI:

```powershell
# Example using PnP.PowerShell
Connect-PnPOnline -Url "https://contoso.sharepoint.com/sites/DocumentOperations" -Interactive
$script = Get-Content -Path "./sharepoint/site-schema.json" -Raw
Add-PnPSiteScript -Title "Document Pipeline Schema" -Content $script
```

Configure restricted permissions on **DocumentIntakeQuarantine** so only Operations, Legal, HR, and Finance reviewers can view staged files.

---

## 3. Configure Azure AI Builder

1. Open [Power Automate](https://make.powerautomate.com) → **AI hub → AI models**.
2. Use the prebuilt **Extract information from invoices** / **Recognize text in an image or a PDF document** model (or train a custom Document Processing model if your organization receives specialized forms).
3. Bind the model inside the `AI_Builder_Extract_Document_Text` step.

---

## 4. Import Power Automate Flows

1. Import `power-automate/flows/email-document-router.json` and `power-automate/flows/teams-approval-callback.json` into a Power Platform Solution.
2. Bind the Connection References:
   - Office 365 Outlook (shared intake mailbox)
   - AI Builder
   - SharePoint Online
   - Microsoft Teams
3. Set the flow environment variables (`sharepointSiteUrl`, `azureOpenAiEndpoint`, `azureOpenAiDeployment`, `confidenceThreshold`, `highValueInvoiceThreshold`, and Teams IDs).
4. Paste `power-automate/adaptive-cards/escalation-review-card.json` into the Teams **Post adaptive card and wait for a response** action (or wire the HTTP callback URL to `teams-approval-callback.json`).
5. Copy the system prompt from `power-automate/prompts/classification-system.txt` into the Azure OpenAI HTTP action.

---

## 5. Optional: Run `doc-router` as a Custom Connector

If you prefer keeping the deterministic PII/routing engine outside Power Automate expressions:

```bash
cp .env.example .env
# Fill AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and API_KEY
docker compose up --build -d
```

Then import `http://<host>:8000/openapi.json` into Power Automate as a Custom Connector (or deploy the container image to Azure Container Apps).
