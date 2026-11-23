@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Short environment suffix (dev, stage, prod)')
@allowed(['dev', 'stage', 'prod'])
param environment string = 'dev'

@description('Base prefix used to name Azure resources')
@minLength(3)
@maxLength(16)
param projectPrefix string = 'docpipe'

@description('Azure OpenAI model name to deploy for structured classification')
param openAiModelName string = 'gpt-4o-mini'

@description('Azure OpenAI model version')
param openAiModelVersion string = '2024-07-18'

@description('Deployment capacity in thousands of tokens per minute (TPM)')
param openAiCapacity int = 30

var suffix = uniqueString(resourceGroup().id, projectPrefix, environment)
var openAiAccountName = '${projectPrefix}-oai-${environment}-${take(suffix, 6)}'
var keyVaultName = '${projectPrefix}-kv-${environment}-${take(suffix, 6)}'
var appInsightsName = '${projectPrefix}-ai-${environment}'
var logAnalyticsName = '${projectPrefix}-law-${environment}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: openAiAccountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: openAiAccountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
}

resource classificationDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openAiAccount
  name: openAiModelName
  sku: {
    name: 'Standard'
    capacity: openAiCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAiModelName
      version: openAiModelVersion
    }
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    sku: {
      family: 'A'
      name: 'standard'
    }
  }
}

output openAiEndpoint string = openAiAccount.properties.endpoint
output openAiDeploymentName string = classificationDeployment.name
output keyVaultUri string = keyVault.properties.vaultUri
output appInsightsConnectionString string = appInsights.properties.ConnectionString
