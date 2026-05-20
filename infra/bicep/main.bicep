targetScope = 'resourceGroup'

param location string = resourceGroup().location
param appName string = 'maw'
param environment string = 'dev'
param acrImageTag string = 'latest'

@secure()
param postgresAdminPassword string

var suffix = '${appName}-${environment}'
var acrName = take(replace('${suffix}acr', '-', ''), 50)
var logAnalyticsSharedKey = listKeys(resourceId('Microsoft.OperationalInsights/workspaces', '${suffix}-law'), '2020-08-01').primarySharedKey
var commonEnv = [
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsights.outputs.connectionString
  }
  {
    name: 'LLM_PROVIDER'
    value: 'openai'
  }
  {
    name: 'LLM_MODEL'
    value: 'gpt-4o-mini'
  }
  {
    name: 'DATABASE_URL'
    value: 'postgresql+psycopg://observatoryadmin:${postgresAdminPassword}@${postgres.outputs.fqdn}:5432/maw'
  }
  {
    name: 'CHECKPOINT_DB_URL'
    value: 'postgresql+psycopg://observatoryadmin:${postgresAdminPassword}@${postgres.outputs.fqdn}:5432/maw'
  }
  {
    name: 'OPENAI_API_KEY'
    value: ''
  }
  {
    name: 'ANTHROPIC_API_KEY'
    value: ''
  }
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: ''
  }
  {
    name: 'AZURE_OPENAI_KEY'
    value: ''
  }
  {
    name: 'AZURE_OPENAI_CHAT_DEPLOYMENT'
    value: 'gpt-4o'
  }
  {
    name: 'AZURE_OPENAI_API_VERSION'
    value: '2024-02-01'
  }
  {
    name: 'LANGFUSE_PUBLIC_KEY'
    value: ''
  }
  {
    name: 'LANGFUSE_SECRET_KEY'
    value: ''
  }
  {
    name: 'LANGFUSE_HOST'
    value: 'https://cloud.langfuse.com'
  }
]

module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: {
    location: location
    acrName: acrName
  }
}

module appInsights 'modules/appinsights.bicep' = {
  name: 'appinsights'
  params: {
    location: location
    appInsightsName: '${suffix}-ai'
    workspaceName: '${suffix}-law'
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    location: location
    serverName: '${suffix}-pg'
    adminPassword: postgresAdminPassword
  }
}

module acaEnv 'modules/aca-environment.bicep' = {
  name: 'aca-env'
  params: {
    location: location
    environmentName: '${suffix}-env'
    logAnalyticsWorkspaceId: appInsights.outputs.workspaceId
    logAnalyticsSharedKey: logAnalyticsSharedKey
  }
}

module api 'modules/aca-app.bicep' = {
  name: 'api'
  params: {
    location: location
    appName: '${suffix}-api'
    environmentId: acaEnv.outputs.id
    imageName: '${acr.outputs.loginServer}/multi-agent-workflow:${acrImageTag}'
    containerPort: 8010
    command: [
      'uvicorn'
      'api.main:app'
      '--host'
      '0.0.0.0'
      '--port'
      '8010'
    ]
    env: commonEnv
  }
}

module ui 'modules/aca-app.bicep' = {
  name: 'ui'
  params: {
    location: location
    appName: '${suffix}-ui'
    environmentId: acaEnv.outputs.id
    imageName: '${acr.outputs.loginServer}/multi-agent-workflow:${acrImageTag}'
    containerPort: 8020
    command: [
      'uvicorn'
      'app.main:app'
      '--host'
      '0.0.0.0'
      '--port'
      '8020'
    ]
    env: commonEnv
  }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    keyVaultName: '${suffix}-kv'
    managedIdentityPrincipalId: api.outputs.principalId
  }
}

output apiUrl string = 'https://${api.outputs.fqdn}'
output uiUrl string = 'https://${ui.outputs.fqdn}'
output keyVaultUri string = keyvault.outputs.uri
